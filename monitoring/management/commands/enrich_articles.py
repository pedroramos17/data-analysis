"""Run article-level comparison enrichment."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.models import NormalizedDocument
from monitoring.option_parsing import optional_int
from monitoring.services.claims import extract_article_claims
from monitoring.services.embeddings import embed_article
from monitoring.services.entities import enrich_article_entities
from monitoring.services.framing import extract_article_frame_features


class Command(BaseCommand):
    """Enrich normalized documents as comparison articles."""

    help = "Extract entities, claims, embeddings, and framing features."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add enrichment options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args: object, **options: object) -> None:
        """Run local article enrichment.

        Example:
            `python manage.py enrich_articles --limit 100`
        """
        limit = optional_int(options.get("limit")) or 500
        count = _enrich_articles(limit)
        self.stdout.write(f"Enriched {count} articles")


def _enrich_articles(limit: int) -> int:
    count = 0
    for article in NormalizedDocument.objects.all()[:limit]:
        _enrich_article(article)
        count += 1
    return count


def _enrich_article(article: NormalizedDocument) -> None:
    enrich_article_entities(article)
    extract_article_claims(article)
    embed_article(article)
    extract_article_frame_features(article)
    article.status = NormalizedDocument.Status.ENRICHED
    article.save(update_fields=["status"])
