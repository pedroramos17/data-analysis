"""Export normalized documents to Parquet."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from monitoring.exporters import (
    SUPPORTED_EXPORT_DATASETS,
    export_dataset_artifact,
    export_documents_artifact,
)


class Command(BaseCommand):
    """Write normalized documents to an Arrow / Parquet file.

    Example:
        `python manage.py export_parquet --output exports/documents.parquet`
    """

    help = "Export normalized documents to a Parquet file."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add the output file option.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument(
            "--output", default=str(settings.PARQUET_EXPORT_DIR / "documents.parquet")
        )
        parser.add_argument("--dataset", default="documents")
        parser.add_argument("--output-dir", default=str(settings.PARQUET_EXPORT_DIR))

    def handle(self, *args: object, **options: object) -> None:
        """Run the Parquet export.

        Example:
            Django calls this after parsing command options.
        """
        dataset = str(options["dataset"])
        if dataset == "documents":
            artifact = export_documents_artifact(Path(str(options["output"])))
            self.stdout.write(f"Wrote {artifact.path} ({artifact.row_count} rows)")
            return
        artifacts = _export_datasets(dataset, Path(str(options["output_dir"])))
        for artifact in artifacts:
            self.stdout.write(f"Wrote {artifact.path} ({artifact.row_count} rows)")


def _export_datasets(dataset: str, output_dir: Path) -> list[object]:
    if dataset == "all":
        return [
            _export_one_dataset(name, output_dir) for name in SUPPORTED_EXPORT_DATASETS
        ]
    if dataset not in SUPPORTED_EXPORT_DATASETS:
        expected = ("documents", "all", *SUPPORTED_EXPORT_DATASETS)
        raise ValueError(f"Invalid dataset {dataset!r}; expected one of {expected!r}")
    return [_export_one_dataset(dataset, output_dir)]


def _export_one_dataset(dataset: str, output_dir: Path) -> object:
    return export_dataset_artifact(dataset, output_dir / f"{dataset}.parquet")
