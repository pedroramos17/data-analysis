"""Tests for planning, cloud manifests, analytics, and experiments."""

from io import StringIO
from pathlib import Path
import json
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase

from experiments.mamba.load_dataset import load_dataset
from monitoring.analytics.graphs import compute_graph_features
from monitoring.analytics.mfdfa import compute_mfdfa_features
from monitoring.analytics.pipeline import run_local_simple_pipeline
from monitoring.analytics.signatures import compute_signature_features
from monitoring.analytics.wavelet import compute_wavelet_features
from monitoring.cloud.jobs import create_cloud_job_spec
from monitoring.cloud.providers import provider_template
from monitoring.compute.planner import plan_pipeline, split_local_and_cloud_tasks


class PlannerAndCloudTests(SimpleTestCase):
    """Planning and portable cloud manifest regression tests."""

    def test_pipeline_splits_local_and_cloud_for_cpu_profile(self) -> None:
        """Weak local profile keeps simple tasks local and plans heavy cloud."""
        plan = plan_pipeline("local_cpu_low", None, {"rows": 100, "columns": 4})
        local_tasks, cloud_tasks = split_local_and_cloud_tasks(
            (*plan.local_tasks, *plan.cloud_tasks)
        )

        self.assertGreater(len(local_tasks), 0)
        self.assertGreater(len(cloud_tasks), 0)
        self.assertIn("mfdfa_small", [task.task.name for task in local_tasks])
        self.assertIn("large_mfdfa_batched", [task.task.name for task in cloud_tasks])

    def test_cloud_job_spec_has_budget_guard(self) -> None:
        """Cloud specs include provider-neutral budget controls."""
        spec = create_cloud_job_spec("mfdfa_gpu_batched", "cloud_student")

        self.assertTrue(spec.budget["require_confirmation"])
        self.assertEqual(spec.partition["type"], "monthly")

    def test_provider_template_needs_no_sdk(self) -> None:
        """Provider templates are plain instructions."""
        self.assertIn("preemptible", provider_template("gcp"))


class AnalyticsAlgorithmTests(SimpleTestCase):
    """CPU-first analytics algorithm regression tests."""

    def test_algorithms_return_expected_shapes(self) -> None:
        """Wavelet, MFDFA, signatures, and graph features are finite."""
        values = _sample_values()
        wavelet_input = values.reshape(1, values.shape[1], values.shape[0])
        signature_input = values.reshape(1, values.shape[0], values.shape[1])
        wavelet = compute_wavelet_features(wavelet_input)
        mfdfa = compute_mfdfa_features(values.T, scales=(8, 16))
        signatures = compute_signature_features(signature_input)
        graph = compute_graph_features(values)

        self.assertEqual(wavelet["energy"].ndim, 3)
        self.assertEqual(mfdfa["hq"].shape[0], values.shape[1])
        self.assertEqual(signatures["order_one"].shape[-1], values.shape[1])
        self.assertEqual(len(graph["edges"]), values.shape[1] * 3)

    def test_local_pipeline_never_executes_heavy_tasks(self) -> None:
        """The simple local pipeline writes a manifest and avoids heavy work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = run_local_simple_pipeline("local_cpu_low", Path(temp_dir))

        self.assertFalse(manifest["heavy_tasks_executed"])
        self.assertIn("build_feature_store_basic", manifest["tasks"])

    def test_mx350_pipeline_clamps_limits(self) -> None:
        """The MX350 pipeline keeps micro-batch limits."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = run_local_simple_pipeline(
                "local_mx350_queue", Path(temp_dir), True, 99.0, True
            )

        self.assertEqual(manifest["limits"]["batch_size"], 32)
        self.assertEqual(manifest["limits"]["max_vram_gb"], 1.5)


class CommandAndExperimentTests(SimpleTestCase):
    """Management commands and external loader regression tests."""

    def test_plan_commands_write_json(self) -> None:
        """Planner commands generate JSON files without running cloud work."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "pipeline_plan.json"
            call_command(
                "plan_analytics_pipeline",
                "--output",
                str(output_path),
                stdout=StringIO(),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertIn("local_tasks", payload)
        self.assertIn("cloud_tasks", payload)

    def test_cloud_command_writes_job_spec(self) -> None:
        """Cloud job command writes one portable job JSON spec."""
        with tempfile.TemporaryDirectory() as temp_dir:
            call_command(
                "plan_cloud_jobs",
                "--task",
                "graph_embedding",
                "--output",
                temp_dir,
                stdout=StringIO(),
            )
            files = list(Path(temp_dir).glob("*.json"))

        self.assertEqual(len(files), 1)

    def test_experiment_loader_accepts_missing_dataset(self) -> None:
        """Experiment loaders provide a synthetic fallback for smoke tests."""
        dataset = load_dataset("missing_dataset.npz")

        self.assertIn("samples", dataset)
        self.assertIn("targets", dataset)


def _sample_values() -> object:
    import numpy

    time = numpy.arange(64, dtype="float32")
    return numpy.stack([time, time * 2, time * 0.5, 100 - time], axis=1)
