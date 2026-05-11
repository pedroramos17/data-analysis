from django.core.management.base import BaseCommand
from django.utils import timezone

from monitoring.ingestion_v2 import build_dedupe_hash, canonicalize_url
from monitoring.models import IngestedItem, IngestionRun, Source


class Command(BaseCommand):
    help = "Ingest enabled sources with idempotent upsert."

    def add_arguments(self, parser):
        parser.add_argument("--source", action="append", default=[])
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        sources = Source.objects.filter(is_enabled=True)
        if options["source"]:
            sources = sources.filter(name__in=options["source"])
        for source in sources:
            run = IngestionRun.objects.create(source=source, status=IngestionRun.Status.DRY_RUN if options["dry_run"] else IngestionRun.Status.SUCCESS)
            payload = {
                "source_id": source.name,
                "external_id": f"demo-{source.id}",
                "canonical_url": canonicalize_url(source.url),
                "title": f"{source.name} sample",
                "publisher": source.name,
                "published_at": timezone.now(),
            }
            payload["dedupe_hash"] = build_dedupe_hash(payload)
            run.items_seen = 1
            if not options["dry_run"]:
                _, created = IngestedItem.objects.update_or_create(
                    dedupe_hash=payload["dedupe_hash"],
                    defaults=dict(source=source, external_id=payload["external_id"], canonical_url=payload["canonical_url"], raw_url=source.url, title=payload["title"], publisher=source.name, published_at=payload["published_at"], fetched_at=timezone.now(), raw_payload_json=payload, extraction_method="api"),
                )
                run.items_created = 1 if created else 0
                run.items_updated = 0 if created else 1
            run.finished_at = timezone.now()
            run.save(update_fields=["items_seen", "items_created", "items_updated", "finished_at", "status"])
        self.stdout.write(self.style.SUCCESS("ingest_sources complete"))
