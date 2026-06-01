"""Matplotlib-only plot writers with explicit fallback artifacts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quant4.services.multifractal.core.types import MFDFAResult


def write_multifractal_plots(
    result: MFDFAResult,
    output_dir: Path,
    prefix: str = "mf",
) -> list[str]:
    """Write core MF-DFA plots or placeholder artifacts.

    Example:
        `paths = write_multifractal_plots(result, Path("plots"))`
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot
    except ImportError:
        return [_write_placeholder(output_dir, prefix)]
    plotters = [
        ("fluctuation", lambda path: _plot_fluctuation(result, pyplot, path)),
        ("hq", lambda path: _plot_hq(result, pyplot, path)),
        ("tau", lambda path: _plot_tau(result, pyplot, path)),
        ("spectrum", lambda path: _plot_spectrum(result, pyplot, path)),
    ]
    return [
        _write_plot(output_dir, prefix, name, plotter)
        for name, plotter in plotters
    ]


def _write_plot(
    output_dir: Path,
    prefix: str,
    name: str,
    plotter: Callable[[Path], None],
) -> str:
    path = output_dir / f"{prefix}_{name}.png"
    plotter(path)
    return str(path)


def _write_placeholder(output_dir: Path, prefix: str) -> str:
    path = output_dir / f"{prefix}_plots_unavailable.txt"
    path.write_text("matplotlib missing; plot generation skipped", encoding="utf-8")
    return str(path)


def _plot_fluctuation(result: MFDFAResult, pyplot: object, path: Path) -> None:
    figure = pyplot.figure()
    for label, points in result.fluctuation_functions.items():
        if label in {"-2", "0", "2"}:
            pyplot.plot([x for x, _y in points], [y for _x, y in points], label=label)
    pyplot.legend()
    pyplot.title("MF-DFA fluctuation functions")
    _save_and_close(figure, pyplot, path)


def _plot_hq(result: MFDFAResult, pyplot: object, path: Path) -> None:
    figure = pyplot.figure()
    items = sorted((float(key), value) for key, value in result.spectrum.hq.items())
    pyplot.plot([key for key, _value in items], [value for _key, value in items])
    pyplot.title("Generalized Hurst exponents")
    _save_and_close(figure, pyplot, path)


def _plot_tau(result: MFDFAResult, pyplot: object, path: Path) -> None:
    figure = pyplot.figure()
    items = sorted((float(key), value) for key, value in result.spectrum.tau.items())
    pyplot.plot([key for key, _value in items], [value for _key, value in items])
    pyplot.title("Mass exponent tau(q)")
    _save_and_close(figure, pyplot, path)


def _plot_spectrum(result: MFDFAResult, pyplot: object, path: Path) -> None:
    figure = pyplot.figure()
    pyplot.plot(result.spectrum.alpha, result.spectrum.f_alpha)
    pyplot.title("Multifractal spectrum")
    _save_and_close(figure, pyplot, path)


def _save_and_close(figure: object, pyplot: object, path: Path) -> None:
    figure.savefig(path, bbox_inches="tight")
    pyplot.close(figure)
