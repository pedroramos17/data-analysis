"""Tests for dynamic Google News RSS topic sources."""

from django.test import TestCase

from monitoring.google_news import build_google_news_url, create_google_news_source


class GoogleNewsSourceTests(TestCase):
    """Google News topic source regression tests."""

    def test_build_google_news_url_encodes_query(self) -> None:
        """Topic search URLs preserve Google News RSS query parameters."""
        url = build_google_news_url("AI chips")

        self.assertIn("q=AI+chips", url)
        self.assertIn("ceid=US%3Aen", url)

    def test_create_google_news_source_sets_dynamic_metadata(self) -> None:
        """Dynamic topic sources are Tier 4 RSS sources."""
        source = create_google_news_source("AI chips", "technology", ("ai", "chips"))

        self.assertTrue(source.is_dynamic)
        self.assertEqual(source.source_tier, 4)
        self.assertEqual(source.category, "technology")
        self.assertEqual(source.tags, ["ai", "chips"])
