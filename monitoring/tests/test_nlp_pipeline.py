"""Tests for the offline NLP pipeline entrypoints."""

from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from monitoring.models import NlpRunMetric
from monitoring.nlp.pipeline import run_pipeline


class NlpPipelineTests(TestCase):
    """Regression tests for module, command, and metric paths."""

    def test_run_pipeline_returns_expected_json_shape(self) -> None:
        """The shared service returns every requested top-level field."""
        payload = run_pipeline(
            "OpenAI reports secure growth after a breach. #AI", "all"
        )

        self.assertIn("entities", payload)
        self.assertIn("topics", payload)
        self.assertIn("sentiment", payload)
        self.assertIn("keywords", payload)
        self.assertIn("hashtags", payload)
        self.assertIn("embeddings", payload)
        self.assertIn("summary", payload)
        self.assertGreaterEqual(payload["cost"]["total_ms"], 0)

    def test_module_cli_outputs_json(self) -> None:
        """The module CLI supports `python -m monitoring.nlp.pipeline`."""
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "monitoring.nlp.pipeline",
                "--text",
                "OpenAI reports secure growth. #AI",
                "--tasks",
                "all",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertIn("keywords", payload)
        self.assertIn("cost", payload)

    def test_management_command_outputs_json_and_saves_metric(self) -> None:
        """The Django command persists cost metrics for comparisons."""
        output = StringIO()

        call_command(
            "nlp_pipeline",
            text="OpenAI reports secure growth. #AI",
            tasks="all",
            stdout=output,
        )

        payload = json.loads(output.getvalue())
        self.assertIn("sentiment", payload)
        self.assertEqual(NlpRunMetric.objects.count(), 1)
        self.assertGreaterEqual(NlpRunMetric.objects.get().total_ms, 0)
