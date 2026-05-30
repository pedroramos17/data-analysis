"""Security regression tests for the portable cloud job runner."""

from pathlib import Path

from django.test import SimpleTestCase

from examples.run_cloud_job import validate_cloud_runner_command


class CloudRunnerCommandValidationTests(SimpleTestCase):
    """Command allowlist tests for provider-neutral job execution."""

    def test_manage_command_is_allowed(self) -> None:
        """Generated manage.py cloud commands remain executable."""
        args = validate_cloud_runner_command(
            "python manage.py inspect_compute --profile local_cpu_low"
        )

        self.assertEqual(Path(args[1]).name, "manage.py")
        self.assertEqual(args[2], "inspect_compute")

    def test_experiment_smoke_script_is_allowed(self) -> None:
        """Experiment smoke templates are allowed without shell execution."""
        args = validate_cloud_runner_command(
            "python experiments/mamba/train_smoke.py --config config.json"
        )

        self.assertEqual(args[1], "experiments/mamba/train_smoke.py")
        self.assertIn("--config", args)

    def test_shell_operator_is_rejected(self) -> None:
        """Manifest commands cannot inject a shell pipeline."""
        with self.assertRaisesMessage(ValueError, "shell operator"):
            validate_cloud_runner_command("python manage.py inspect_compute | cat")

    def test_unknown_python_script_is_rejected(self) -> None:
        """Only known management and experiment entrypoints are runnable."""
        with self.assertRaisesMessage(ValueError, "expected python manage.py"):
            validate_cloud_runner_command("python scripts/unknown.py")
