"""Export normalized documents to Parquet."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from monitoring.exporters import export_documents_artifact


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

    def handle(self, *args: object, **options: object) -> None:
        """Run the Parquet export.

        Example:
            Django calls this after parsing command options.
        """
        output_path = Path(str(options["output"]))
        artifact = export_documents_artifact(output_path)
        self.stdout.write(f"Wrote {artifact.path} ({artifact.row_count} rows)")
