"""Quant multifractal Phase 13 CLI smoke tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase


class QuantMultifractalCLITests(SimpleTestCase):
    """Management commands should run locally without hidden network access."""

    def test_import_bars_and_compute_returns_commands(self) -> None:
        """CSV import and return generation write local Parquet datasets."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = _write_csv(root / "bars.csv")
            bars_out = StringIO()
            returns_out = StringIO()

            call_command(
                "quant_import_bars",
                "--csv",
                str(csv_path),
                "--symbol",
                "SPY",
                "--output-root",
                str(root / "bars"),
                stdout=bars_out,
            )
            call_command(
                "quant_compute_returns",
                "--bars-root",
                str(root / "bars"),
                "--output-root",
                str(root / "returns"),
                stdout=returns_out,
            )

        self.assertIn("bars_written=3", bars_out.getvalue())
        self.assertIn("returns_written=2", returns_out.getvalue())

    def test_mfdfa_command_outputs_summary(self) -> None:
        """MF-DFA command prints a JSON summary."""
        output = StringIO()

        call_command("quant_mfdfa", "--series", _series(), stdout=output)

        self.assertIn('"method": "mfdfa"', output.getvalue())

    def test_diagnostics_features_and_regime_commands_smoke(self) -> None:
        """Diagnostics, feature, and regime commands print local JSON payloads."""
        diagnostics_out = StringIO()
        features_out = StringIO()
        regime_out = StringIO()

        call_command(
            "quant_mf_diagnostics",
            "--series",
            _series(),
            stdout=diagnostics_out,
        )
        call_command(
            "quant_mf_features",
            "--series",
            _series(),
            "--symbol",
            "SPY",
            "--window-id",
            "w0",
            stdout=features_out,
        )
        call_command("quant_mf_regime", "--series", _series(), stdout=regime_out)

        self.assertIn('"attribution"', diagnostics_out.getvalue())
        self.assertIn('"config_hash"', features_out.getvalue())
        self.assertIn('"labels"', regime_out.getvalue())

    def test_risk_portfolio_and_report_commands_smoke(self) -> None:
        """Risk, portfolio, and report commands expose honest local outputs."""
        risk_out = StringIO()
        portfolio_out = StringIO()
        report_out = StringIO()

        call_command("quant_mf_risk", "--series", _series(), stdout=risk_out)
        call_command(
            "quant_mf_portfolio",
            "--symbols",
            "AAA,BBB",
            "--variances",
            "0.02,0.04",
            stdout=portfolio_out,
        )
        call_command("quant_mf_report", "--symbol", "SPY", stdout=report_out)

        self.assertIn('"risk_score"', risk_out.getvalue())
        self.assertIn('"claims_factor_validity": false', portfolio_out.getvalue())
        self.assertIn("Multifractal Research Report", report_out.getvalue())


def _write_csv(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low,close,volume",
                "2026-01-01T00:00:00Z,100,101,99,100,10",
                "2026-01-02T00:00:00Z,100,102,99,101,11",
                "2026-01-03T00:00:00Z,101,103,100,102,12",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _series() -> str:
    values = [0.01, -0.02, 0.015, -0.005] * 16
    return ",".join(str(value) for value in values)
