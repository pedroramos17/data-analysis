"""Build Sourceflow GraphRAG event context documents."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from monitoring.models import TopicCluster
from sourceflow.intelligence.xai.rag_context import build_event_rag_context


class Command(BaseCommand):
    """Build retrieval-ready event context files."""

    help = "Build Sourceflow GraphRAG context JSON and Markdown files."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add context builder options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--event-id", type=int, default=0)
        parser.add_argument("--recent", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Build one or many context documents.

        Example:
            `python manage.py build_graphrag_context --event-id 42`
        """
        output_dir = _output_dir()
        event_ids = _event_ids(options)
        for event_id in event_ids:
            build_event_rag_context(event_id, output_dir)
        self.stdout.write(f"Built {len(event_ids)} GraphRAG contexts")


def _event_ids(options: dict[str, object]) -> tuple[int, ...]:
    event_id = int(options.get("event_id") or 0)
    if event_id:
        return (event_id,)
    recent = int(options.get("recent") or 0)
    if recent <= 0:
        return ()
    rows = TopicCluster.objects.order_by("-window_end").values_list("id", flat=True)
    return tuple(int(value) for value in rows[:recent])


def _output_dir() -> Path:
    configured = getattr(settings, "GRAPHRAG_CONTEXT_DIR", "")
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "data"
