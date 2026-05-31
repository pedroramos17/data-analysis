"""Partitioned Parquet storage for Quant4 multifractal datasets."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quant4.services.multifractal.data.contracts import (
    BAR_SCHEMA_VERSION,
    RETURN_SCHEMA_VERSION,
    DatasetWriteResult,
    OHLCVBar,
    ReturnRecord,
    bar_to_row,
    return_to_row,
    row_to_bar,
    row_to_return,
)


def write_bars_parquet(
    bars: Iterable[OHLCVBar],
    root_path: Path,
) -> DatasetWriteResult:
    """Write OHLCV bars as partitioned Parquet files.

    Example:
        `write_bars_parquet(bars, Path("data/bars"))`
    """
    grouped = _group_bars(list(bars))
    paths = [
        _write_bar_partition(root_path, key, rows)
        for key, rows in grouped.items()
    ]
    return DatasetWriteResult(
        str(root_path),
        sorted(paths),
        _row_count(grouped),
        BAR_SCHEMA_VERSION,
    )


def read_bars_parquet(
    root_path: str,
    symbol: str | None = None,
    timeframe: str | None = None,
    asset_class: str | None = None,
) -> list[OHLCVBar]:
    """Read partitioned OHLCV Parquet bars.

    Example:
        `bars = read_bars_parquet("data/bars", symbol="SPY")`
    """
    rows = [_read_rows(path) for path in Path(root_path).glob("**/*.parquet")]
    bars = [row_to_bar(row) for batch in rows for row in batch]
    return sorted(_filter_bars(bars, symbol, timeframe, asset_class), key=_bar_sort_key)


def write_returns_parquet(
    returns: Iterable[ReturnRecord],
    root_path: Path,
) -> DatasetWriteResult:
    """Write derived returns as partitioned Parquet files.

    Example:
        `write_returns_parquet(records, Path("data/returns"))`
    """
    grouped = _group_returns(list(returns))
    paths = [
        _write_return_partition(root_path, key, rows)
        for key, rows in grouped.items()
    ]
    return DatasetWriteResult(
        str(root_path),
        sorted(paths),
        _row_count(grouped),
        RETURN_SCHEMA_VERSION,
    )


def read_returns_parquet(
    root_path: str,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[ReturnRecord]:
    """Read partitioned return Parquet records.

    Example:
        `returns = read_returns_parquet("data/returns")`
    """
    rows = [_read_rows(path) for path in Path(root_path).glob("**/*.parquet")]
    records = [row_to_return(row) for batch in rows for row in batch]
    return sorted(_filter_returns(records, symbol, timeframe), key=_return_sort_key)


def _group_bars(bars: list[OHLCVBar]) -> dict[tuple[str, str, str], list[OHLCVBar]]:
    grouped: dict[tuple[str, str, str], list[OHLCVBar]] = {}
    for bar in bars:
        key = (_partition_value(bar.asset_class), bar.timeframe, bar.symbol)
        grouped.setdefault(key, []).append(bar)
    return grouped


def _group_returns(
    returns: list[ReturnRecord],
) -> dict[tuple[str, str], list[ReturnRecord]]:
    grouped: dict[tuple[str, str], list[ReturnRecord]] = {}
    for record in returns:
        grouped.setdefault((record.timeframe, record.symbol), []).append(record)
    return grouped


def _write_bar_partition(
    root_path: Path,
    key: tuple[str, str, str],
    bars: list[OHLCVBar],
) -> str:
    asset_class, timeframe, symbol = key
    path = _bar_partition_path(root_path, asset_class, timeframe, symbol)
    _write_rows([bar_to_row(bar) for bar in bars], path)
    return str(path)


def _write_return_partition(
    root_path: Path,
    key: tuple[str, str],
    records: list[ReturnRecord],
) -> str:
    timeframe, symbol = key
    path = _return_partition_path(root_path, timeframe, symbol)
    _write_rows([return_to_row(record) for record in records], path)
    return str(path)


def _bar_partition_path(
    root_path: Path,
    asset_class: str,
    timeframe: str,
    symbol: str,
) -> Path:
    return (
        root_path
        / f"asset_class={_safe_token(asset_class)}"
        / f"timeframe={_safe_token(timeframe)}"
        / f"symbol={_safe_token(symbol)}"
        / "part-000.parquet"
    )


def _return_partition_path(root_path: Path, timeframe: str, symbol: str) -> Path:
    return (
        root_path
        / f"timeframe={_safe_token(timeframe)}"
        / f"symbol={_safe_token(symbol)}"
        / "part-000.parquet"
    )


def _write_rows(rows: list[dict[str, object]], output_path: Path) -> None:
    pyarrow, parquet = _arrow_modules()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(pyarrow.Table.from_pylist(rows), output_path)


def _read_rows(path: Path) -> list[dict[str, object]]:
    _pyarrow, parquet = _arrow_modules()
    return list(parquet.ParquetFile(path).read().to_pylist())


def _filter_bars(
    bars: list[OHLCVBar],
    symbol: str | None,
    timeframe: str | None,
    asset_class: str | None,
) -> list[OHLCVBar]:
    return [
        bar
        for bar in bars
        if _matches(bar.symbol, symbol)
        and _matches(bar.timeframe, timeframe)
        and _matches(bar.asset_class, asset_class)
    ]


def _filter_returns(
    records: list[ReturnRecord],
    symbol: str | None,
    timeframe: str | None,
) -> list[ReturnRecord]:
    return [
        record
        for record in records
        if _matches(record.symbol, symbol) and _matches(record.timeframe, timeframe)
    ]


def _arrow_modules() -> tuple[object, object]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as exc:
        raise RuntimeError(
            "Parquet storage failed; expected pyarrow installed"
        ) from exc
    return pyarrow, pyarrow.parquet


def _row_count(grouped: dict[object, list[object]]) -> int:
    return sum(len(rows) for rows in grouped.values())


def _partition_value(value: str | None) -> str:
    return "__null__" if value is None else value


def _safe_token(value: str) -> str:
    token = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return token.strip("_") or "__null__"


def _matches(left_value: str | None, right_value: str | None) -> bool:
    return right_value is None or left_value == right_value


def _bar_sort_key(bar: OHLCVBar) -> tuple[str, str, str]:
    return bar.symbol, bar.timeframe, bar.timestamp.isoformat()


def _return_sort_key(record: ReturnRecord) -> tuple[str, str, str]:
    return record.symbol, record.timeframe, record.timestamp.isoformat()
