"""Tests for curated RSS catalog validation."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase

from monitoring.catalog import FeedCatalogRow, load_feed_catalog, validate_feed_catalog
from monitoring.models import Source


class CatalogValidationTests(TestCase):
    """Catalog validation regression tests."""

    def test_valid_catalog_row_is_accepted(self) -> None:
        """A valid feed row passes category, tier, and domain checks."""
        rows = [_catalog_row()]

        validate_feed_catalog(rows, ("example.org",))

        self.assertEqual(rows[0].category, Source.Category.SECURITY)

    def test_duplicate_feed_url_is_rejected(self) -> None:
        """Catalog URLs must be unique."""
        rows = [_catalog_row(), _catalog_row(name="Example Copy")]

        with self.assertRaisesMessage(ValueError, "expected unique URLs"):
            validate_feed_catalog(rows, ("example.org",))

    def test_duplicate_source_name_is_rejected(self) -> None:
        """Catalog source names must be unique."""
        rows = [_catalog_row(), _catalog_row(url="https://example.org/other.xml")]

        with self.assertRaisesMessage(ValueError, "expected unique names"):
            validate_feed_catalog(rows, ("example.org",))

    def test_non_allowlisted_domain_is_rejected(self) -> None:
        """Every feed URL must be on the trusted domain allowlist."""
        rows = [_catalog_row(url="https://blocked.example/feed.xml")]

        with self.assertRaisesMessage(ValueError, "expected allowlisted domain"):
            validate_feed_catalog(rows, ("example.org",))

    def test_invalid_category_is_rejected(self) -> None:
        """Categories are limited to the fixed catalog taxonomy."""
        rows = [_catalog_row(category="unknown")]

        with self.assertRaisesMessage(ValueError, "expected one of"):
            validate_feed_catalog(rows, ("example.org",))

    def test_invalid_tier_is_rejected(self) -> None:
        """Source tiers must be 1, 2, 3, or 4."""
        rows = [_catalog_row(source_tier=5)]

        with self.assertRaisesMessage(ValueError, "expected 1, 2, 3, or 4"):
            validate_feed_catalog(rows, ("example.org",))

    def test_load_feed_catalog_reads_json_files(self) -> None:
        """Catalog loading validates external JSON catalog and domain files."""
        with TemporaryDirectory() as directory_name:
            catalog_path, domains_path = _write_catalog_files(Path(directory_name))
            rows = load_feed_catalog(catalog_path, domains_path)

        self.assertEqual(rows[0].name, "Example Feed")


def _catalog_row(
    name: str = "Example Feed",
    url: str = "https://example.org/feed.xml",
    category: str = Source.Category.SECURITY,
    source_tier: int = 1,
) -> FeedCatalogRow:
    return FeedCatalogRow(
        name, url, category, ("security",), source_tier, "en", 60, 10, 0.9, "", False
    )


def _write_catalog_files(directory_path: Path) -> tuple[Path, Path]:
    catalog_path = directory_path / "feeds.json"
    domains_path = directory_path / "domains.json"
    catalog_path.write_text(_catalog_json(), encoding="utf-8")
    domains_path.write_text('["example.org"]', encoding="utf-8")
    return catalog_path, domains_path


def _catalog_json() -> str:
    return """
    [{
      "name": "Example Feed",
      "url": "https://example.org/feed.xml",
      "category": "security",
      "tags": ["security"],
      "source_tier": 1
    }]
    """
