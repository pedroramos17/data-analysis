"""Quant multifractal Phase 14 reporting tests."""

from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


class QuantMultifractalReportingTests(SimpleTestCase):
    """Reports and plots should be local, cautious, and reproducible."""

    def test_markdown_report_contains_required_sections(self) -> None:
        """Markdown report includes config, method, warnings, and cautions."""
        from quant.services.multifractal.reports.multifractal_report import (
            build_multifractal_research_report,
        )

        report = build_multifractal_research_report("SPY", "dataset_1", _series())
        markdown = report.to_markdown()

        self.assertIn("Data Summary", markdown)
        self.assertIn("MF-DFA Summary", markdown)
        self.assertIn("Interpretation Cautions", markdown)
        self.assertIn("dataset_1", markdown)

    def test_report_json_is_serializable_and_non_predictive(self) -> None:
        """JSON report preserves the no-performance-claim boundary."""
        from quant.services.multifractal.reports.multifractal_report import (
            build_multifractal_research_report,
        )

        payload = build_multifractal_research_report(
            "SPY",
            "dataset_1",
            _series(),
        ).to_json_dict()

        self.assertFalse(payload["claims_predictive_performance"])
        self.assertIn("q_grid", payload["config"])

    def test_plot_writer_creates_local_artifacts(self) -> None:
        """Plot writer creates PNGs or explicit placeholder artifacts."""
        from quant.services.multifractal.core.mfdfa import run_mfdfa
        from quant.services.multifractal.plots.multifractal_plots import (
            write_multifractal_plots,
        )

        with TemporaryDirectory() as directory:
            paths = write_multifractal_plots(run_mfdfa(_series()), Path(directory))

        self.assertGreaterEqual(len(paths), 1)
        self.assertTrue(all(Path(path).name.startswith("mf_") for path in paths))

    def test_fluctuation_plot_points_are_log_scaled(self) -> None:
        """MF-DFA fluctuation plot points expose log-log coordinates."""
        from quant.services.multifractal.core.mfdfa import run_mfdfa
        from quant.services.multifractal.plots.multifractal_plots import (
            fluctuation_plot_points,
        )

        result = run_mfdfa(_series())
        first_scale, first_value = result.fluctuation_functions["2"][0]
        first_x, first_y = fluctuation_plot_points(result, "2")[0]

        self.assertAlmostEqual(first_x, math.log(first_scale))
        self.assertAlmostEqual(first_y, math.log(first_value))


def _series() -> list[float]:
    return [0.01, -0.02, 0.015, -0.005] * 16
