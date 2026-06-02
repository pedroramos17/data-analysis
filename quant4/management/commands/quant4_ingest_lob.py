"""Normalize local LOB data and write feature artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.lob.microstructure_labels import build_lob_labels
from quant4.services.lob.orderbook_features import build_orderbook_features
from quant4.services.lob.parser import parse_lob_jsonl
from sourceflow.config.feature_flags import require_feature


class Command(BaseCommand):
    """Create local LOB feature and label artifacts."""

    help = "Normalize local LOB JSONL data and write feature/label artifacts."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register local LOB ingestion options."""
        parser.add_argument("--input-path", required=True)
        parser.add_argument("--output-dir", default="data/quant4_lob")
        parser.add_argument("--venue-type", default="generic")
        parser.add_argument("--horizon", type=int, default=1)

    def handle(self, *args: object, **options: object) -> None:
        """Normalize books and report generated artifact paths."""
        require_feature("QUANT4_LOB_CORE")
        snapshots = parse_lob_jsonl(
            str(options["input_path"]),
            venue_type=str(options["venue_type"]),
        )
        paths = _write_lob_ingest_artifacts(
            snapshots,
            str(options["output_dir"]),
            int(options["horizon"]),
        )
        self.stdout.write(f"lob_snapshot_count={len(snapshots)}")
        self.stdout.write(f"lob_feature_path={paths['features_path']}")


def _write_lob_ingest_artifacts(
    snapshots: object,
    output_dir: str,
    horizon: int,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = _ingest_paths(root)
    _write_json(paths["features_path"], {"features": _features_payload(snapshots)})
    _write_json(paths["labels_path"], {"labels": _labels_payload(snapshots, horizon)})
    return paths


def _ingest_paths(root: Path) -> dict[str, str]:
    return {
        "features_path": str(root / "lob_features.json"),
        "labels_path": str(root / "lob_labels.json"),
    }


def _features_payload(snapshots: object) -> list[dict[str, object]]:
    return [
        {"timestamp": row.timestamp, "symbol": row.symbol, "values": row.values}
        for row in build_orderbook_features(snapshots)
    ]


def _labels_payload(snapshots: object, horizon: int) -> list[dict[str, object]]:
    return [
        {"timestamp": row.timestamp, "symbol": row.symbol, "values": row.values}
        for row in build_lob_labels(snapshots, horizon=horizon)
    ]


def _write_json(path: str, payload: dict[str, object]) -> None:
    Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
