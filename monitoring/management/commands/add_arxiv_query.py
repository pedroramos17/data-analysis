"""Create bounded arXiv API sources for science-paper monitoring."""

from urllib.parse import urlencode

from django.core.management.base import BaseCommand, CommandParser

from monitoring.models import Source

ARXIV_API_URL = "https://export.arxiv.org/api/query"


class Command(BaseCommand):
    """Create or update a disabled arXiv API query source."""

    help = "Create an arXiv API source that follows official bounded query guidance."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add arXiv query options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--query", required=True)
        parser.add_argument("--name", default="")
        parser.add_argument("--max-results", type=int, default=25)
        parser.add_argument("--category", default=Source.Category.SCIENCE)
        parser.add_argument("--tags", default="science,research,papers")

    def handle(self, *args: object, **options: object) -> None:
        """Create the source and print its URL.

        Example:
            `python manage.py add_arxiv_query --query "startup AI"`
        """
        source = _upsert_arxiv_source(options)
        self.stdout.write(f"Created arXiv source {source.name}: {source.url}")


def _upsert_arxiv_source(options: dict[str, object]) -> Source:
    query = str(options["query"])
    name = str(options.get("name") or f"arXiv: {query}")[:180]
    source, _created = Source.objects.update_or_create(
        name=name,
        defaults=_source_defaults(query, options),
    )
    return source


def _source_defaults(query: str, options: dict[str, object]) -> dict[str, object]:
    return {
        "url": _arxiv_query_url(query, int(options["max_results"])),
        "source_type": Source.SourceType.API,
        "fetch_method": Source.FetchMethod.API,
        "source_kind": Source.SourceKind.PAPER,
        "category": str(options["category"]),
        "tags": _tags(str(options["tags"])),
        "cadence_minutes": 240,
        "rate_limit_seconds": 3,
        "is_enabled": False,
        "reliability_score": 0.9,
    }


def _arxiv_query_url(query: str, max_results: int) -> str:
    bounded = max(1, min(100, max_results))
    payload = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": bounded,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    return f"{ARXIV_API_URL}?{urlencode(payload)}"


def _tags(value: str) -> list[str]:
    return [tag.strip().lower() for tag in value.split(",") if tag.strip()]
