"""Provider-neutral object key layout for data lake artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DataLakePaths:
    """Build stable object keys for local, S3, R2, B2, or MinIO storage.

    Example:
        `DataLakePaths().model_artifact("mamba", "v1", "model.bin")`
    """

    prefix: str = ""

    def raw_data(
        self,
        source: str,
        asset_type: str,
        symbol: str,
        timeframe: str,
        date: str,
        filename: str,
    ) -> str:
        """Return a raw data lake object key."""
        return self._join(
            "raw",
            f"source={_token(source)}",
            f"asset_type={_token(asset_type)}",
            f"symbol={_token(symbol)}",
            f"timeframe={_token(timeframe)}",
            f"date={_token(date)}",
            _filename(filename),
        )

    def parquet_dataset(
        self,
        dataset: str,
        version: str,
        partition: Mapping[str, str],
        filename: str,
    ) -> str:
        """Return a curated Parquet dataset object key."""
        parts = [
            "datasets",
            f"dataset={_token(dataset)}",
            f"version={_token(version)}",
        ]
        parts.extend(
            f"{_token(key)}={_token(value)}" for key, value in partition.items()
        )
        parts.append(_filename(filename))
        return self._join(*parts)

    def model_artifact(self, model_name: str, model_version: str, filename: str) -> str:
        """Return a model artifact object key."""
        return self._join(
            "models",
            f"model_name={_token(model_name)}",
            f"model_version={_token(model_version)}",
            _filename(filename),
        )

    def backtest_report(self, run_id: str, filename: str) -> str:
        """Return a backtest report object key."""
        return self._join(
            "backtests",
            "reports",
            f"run_id={_token(run_id)}",
            _filename(filename),
        )

    def risk_report(self, run_id: str, filename: str) -> str:
        """Return a risk report object key."""
        return self._join(
            "risk",
            "reports",
            f"run_id={_token(run_id)}",
            _filename(filename),
        )

    def log_file(self, log_name: str, date: str, filename: str) -> str:
        """Return a log object key."""
        return self._join(
            "logs",
            f"log={_token(log_name)}",
            f"date={_token(date)}",
            _filename(filename),
        )

    def cached_dataset(self, dataset: str, version: str, filename: str) -> str:
        """Return a cached dataset object key."""
        return self._join(
            "cache",
            "datasets",
            f"dataset={_token(dataset)}",
            f"version={_token(version)}",
            _filename(filename),
        )

    def manifest_for(self, object_path: str) -> str:
        """Return the `_manifest.json` key beside an object."""
        parts = object_path.strip("/").split("/")
        if len(parts) <= 1:
            return self._join("_manifest.json")
        return "/".join([*parts[:-1], "_manifest.json"])

    def _join(self, *parts: str) -> str:
        prefix = self.prefix.strip("/")
        clean_parts = [part.strip("/") for part in parts if part.strip("/")]
        if prefix:
            clean_parts.insert(0, prefix)
        return "/".join(clean_parts)


def _token(value: str) -> str:
    token = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return token.strip("_") or "__null__"


def _filename(value: str) -> str:
    normalized = value.strip().replace("\\", "/").strip("/")
    if normalized and ".." not in normalized.split("/"):
        return normalized
    raise ValueError(f"Invalid filename {value!r}; expected relative file name")
