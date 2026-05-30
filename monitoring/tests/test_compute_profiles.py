"""Tests for compute profiles, routing, limits, and array helpers."""

import json
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from monitoring.compute.array_api import (
    as_float_array,
    batched_matmul,
    get_array_backend,
    rolling_window_view,
    safe_corrcoef,
    safe_diff,
    safe_log,
    safe_mean,
    safe_std,
)
from monitoring.compute.capabilities import (
    ComputeCapabilities,
    detect_compute_capabilities,
)
from monitoring.compute.limits import apply_resource_limits, estimate_job_size
from monitoring.compute.native import detect_native_status
from monitoring.compute.profiles import COMPUTE_PROFILES, get_compute_profile
from monitoring.compute.routing import select_backend, validate_task_allowed
from monitoring.dashboard_models import ComputeProfileConfig, ComputeProfileTypeSetting
from monitoring.orchestration.profile_config import sync_profile_type_settings


class ComputeProfileRegistryTests(SimpleTestCase):
    """Profile registry and task policy regression tests."""

    def test_required_profiles_exist(self) -> None:
        """All required profiles are registered by stable name."""
        expected = {
            "local_cpu_low",
            "local_mx350_queue",
            "local_rtx4060ti",
            "cloud_student",
            "cloud_serverless_on_demand",
        }

        self.assertEqual(set(COMPUTE_PROFILES), expected)

    def test_local_cpu_tasks_match_policy(self) -> None:
        """The weak local profile permits simple work and denies heavy work."""
        profile = get_compute_profile("local_cpu_low")

        self.assertIn("ingestion", profile.allowed_tasks)
        self.assertIn("large_mfdfa_batched", profile.denied_tasks)

    def test_denied_task_raises_clear_error(self) -> None:
        """Denied tasks fail before backend selection."""
        with self.assertRaisesMessage(ValueError, "Task 'train_mamba' denied"):
            validate_task_allowed("train_mamba", "local_cpu_low")


class ComputeProfileTypeSettingTests(TestCase):
    """DB-backed profile type setting regression tests."""

    def test_profile_type_seeds_create_required_slugs(self) -> None:
        """Profile type settings are seeded from built-in profiles."""
        settings = sync_profile_type_settings()

        slugs = {setting.slug for setting in settings}

        self.assertIn("local_cpu_low", slugs)
        self.assertIn("cloud_serverless_on_demand", slugs)

    def test_profile_type_field_accepts_custom_slug(self) -> None:
        """Profile config slugs are editable strings, not fixed choices."""
        field = ComputeProfileConfig._meta.get_field("profile_type")
        profile = ComputeProfileConfig.objects.create(
            name="custom profile",
            profile_type="custom_light",
        )

        self.assertFalse(field.choices)
        self.assertEqual(profile.profile_type, "custom_light")

    def test_get_compute_profile_resolves_custom_db_setting(self) -> None:
        """Runtime profile lookup can resolve custom DB-backed slugs."""
        ComputeProfileTypeSetting.objects.create(
            slug="custom_light",
            label="Custom light",
            allowed_tasks_json=["ingestion"],
            denied_tasks_json=["train_mamba"],
        )

        profile = get_compute_profile("custom_light")

        self.assertEqual(profile.name, "custom_light")
        self.assertIn("ingestion", profile.allowed_tasks)


class ComputeLimitTests(SimpleTestCase):
    """Resource limit and estimate regression tests."""

    def test_mx350_limits_are_aggressive(self) -> None:
        """The MX350 profile clamps requested batch, window, and VRAM."""
        limited = apply_resource_limits(
            {"batch_size": 999, "window": 999, "max_vram_gb": 99},
            "local_mx350_queue",
        )

        self.assertEqual(limited["batch_size"], 32)
        self.assertEqual(limited["window"], 256)
        self.assertEqual(limited["max_vram_gb"], 1.5)

    def test_cloud_execution_requires_manifest_and_budget(self) -> None:
        """Cloud execution cannot proceed without guard fields."""
        with self.assertRaisesMessage(ValueError, "manifest_path and max_cost_usd"):
            apply_resource_limits({"execute": True}, "cloud_student")

    def test_job_estimate_uses_profile_caps(self) -> None:
        """Size estimates clamp batch and window by profile policy."""
        estimate = estimate_job_size(100, 4, 999, 999, "local_cpu_low")

        self.assertEqual(estimate.window, 512)
        self.assertEqual(estimate.batch_size, 256)
        self.assertGreater(estimate.estimated_bytes, 0)


class ComputeRoutingTests(SimpleTestCase):
    """Backend routing fallback regression tests."""

    def test_auto_backend_falls_back_to_cpu_without_gpu(self) -> None:
        """GPU-capable profiles use CPU when CUDA is not available."""
        selected = select_backend(
            "gpu_smoke_test",
            profile="local_mx350_queue",
            capabilities=_capabilities_without_gpu(),
        )

        self.assertEqual(selected.name, "cpu")
        self.assertTrue(selected.used_fallback)

    def test_cloud_profile_selects_manifest_backend(self) -> None:
        """Cloud profiles route advanced work to portable manifests."""
        selected = select_backend(
            "advanced_dtcwt",
            profile="cloud_student",
            capabilities=_capabilities_without_gpu(),
        )

        self.assertEqual(selected.name, "cloud_manifest")

    def test_detection_returns_without_optional_packages(self) -> None:
        """Capability detection does not require GPU packages."""
        capabilities = detect_compute_capabilities()

        self.assertGreaterEqual(capabilities.cpu_count, 1)
        self.assertIsInstance(capabilities.torch_available, bool)


class ArrayApiTests(SimpleTestCase):
    """NumPy fallback array helper regression tests."""

    def test_numpy_backend_is_default_for_cpu_profile(self) -> None:
        """The low-end local profile resolves to NumPy."""
        backend = get_array_backend(profile="local_cpu_low")

        self.assertEqual(backend.name, "numpy")

    def test_array_helpers_return_expected_shapes(self) -> None:
        """Core array helpers preserve predictable output shapes."""
        array = as_float_array([[1, 2, 3], [2, 3, 4]])
        windows = rolling_window_view(array, 2)
        product = batched_matmul([[[1.0]]], [[[2.0]]])

        self.assertEqual(array.shape, (2, 3))
        self.assertEqual(windows.shape, (2, 2, 2))
        self.assertEqual(product.shape, (1, 1, 1))

    def test_safe_numeric_helpers_return_finite_values(self) -> None:
        """Safe helpers avoid NaN and infinite outputs in common paths."""
        logged = safe_log([0.0, 1.0])
        corr = safe_corrcoef([[1, 1], [1, 1]])

        self.assertEqual(safe_diff([1, 3, 6]).shape, (2,))
        self.assertEqual(float(safe_mean([1.0, 2.0])), 1.5)
        self.assertGreaterEqual(float(safe_std([1.0, 2.0])), 0.0)
        self.assertTrue(bool((logged == logged).all()))
        self.assertTrue(bool((corr == corr).all()))


class NativeAndCommandTests(SimpleTestCase):
    """Native fallback and management command regression tests."""

    def test_native_status_never_requires_library(self) -> None:
        """Native status reports fallback state instead of failing."""
        status = detect_native_status()

        self.assertIsInstance(status.available, bool)
        self.assertIsInstance(status.warning, str)

    def test_inspect_compute_outputs_json(self) -> None:
        """The inspect command prints a valid JSON payload."""
        stdout = StringIO()

        call_command("inspect_compute", "--profile", "local_cpu_low", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["profile"]["name"], "local_cpu_low")
        self.assertIn("capabilities", payload)

    def test_inspect_compute_outputs_native_status(self) -> None:
        """The native flag adds optional native status to JSON."""
        stdout = StringIO()

        call_command(
            "inspect_compute",
            "--profile",
            "local_mx350_queue",
            "--native",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())

        self.assertIn("native", payload)


def _capabilities_without_gpu() -> ComputeCapabilities:
    return ComputeCapabilities(
        python_version="3.12.0",
        os_name="test-os",
        cpu_count=2,
        ram_gb=4.0,
        pyarrow_available=True,
        pyarrow_version="15",
        numpy_available=True,
        numpy_version="1",
        torch_available=False,
        torch_version="",
        cuda_available=False,
        cuda_device_name="",
        total_vram_gb=None,
        cupy_available=False,
        cupy_version="",
        numba_available=False,
        numba_version="",
        c_compiler_available=False,
        c_compiler_path="",
    )
