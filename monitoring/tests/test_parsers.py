"""Tests for feed, HTML, sitemap, and API parsers."""

from pathlib import Path

from django.test import SimpleTestCase

from monitoring.parsers.api import parse_api_records
from monitoring.parsers.arxiv import parse_arxiv_api_records
from monitoring.parsers.html import parse_html_document
from monitoring.parsers.rss import parse_rss_records
from monitoring.parsers.sitemap import parse_sitemap_urls

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"


class ParserTests(SimpleTestCase):
    """Parser regression tests for bundled sample payloads."""

    def test_rss_parser_extracts_records(self) -> None:
        """RSS records include title, link, author, timestamp, and tags."""
        records = parse_rss_records(_sample_text("sample_feed.xml"), ("security",))

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].title, "OpenSSL Advisory Published")
        self.assertEqual(records[0].external_id, "advisory-001")
        self.assertEqual(records[0].tags, ("security",))

    def test_html_parser_extracts_metadata(self) -> None:
        """HTML parsing keeps canonical URL, language, author, and paragraphs."""
        record = parse_html_document(
            _sample_text("sample_article.html"),
            "https://example.org/fallback",
            ("paper",),
        )

        self.assertEqual(record.url, "https://example.org/papers/open-research")
        self.assertEqual(record.author, "Ada Lovelace")
        self.assertEqual(record.language, "en")
        self.assertIn("repeatable ingestion", record.content)

    def test_sitemap_parser_extracts_urls(self) -> None:
        """Sitemap parsing returns loc values."""
        xml_text = "<urlset><url><loc>https://example.org/a</loc></url></urlset>"

        self.assertEqual(parse_sitemap_urls(xml_text), ["https://example.org/a"])

    def test_api_parser_extracts_items(self) -> None:
        """Approved API parser converts item objects to parsed records."""
        records = parse_api_records(_sample_text("sample_api.json"), ("api",))

        self.assertEqual(records[0].title, "Public API Item")
        self.assertEqual(records[0].external_id, "api-001")

    def test_rss_parser_cleans_html_content_encoded(self) -> None:
        """RSS parser strips HTML, decodes entities, and clips snippets."""
        records = parse_rss_records(_content_encoded_feed())

        self.assertEqual(records[0].content, "Alpha & Beta analysis continues")

    def test_rss_parser_rejects_empty_short_and_duplicate_snippets(self) -> None:
        """Digest records need useful snippets distinct from the headline."""
        records = parse_rss_records(_low_value_feed())

        self.assertEqual(records, [])

    def test_atom_parser_extracts_entries(self) -> None:
        """Atom entries are parsed into the same record contract."""
        records = parse_rss_records(_atom_feed())

        self.assertEqual(records[0].title, "Atom Title")
        self.assertIn("useful Atom summary", records[0].content)

    def test_rss_parser_recovers_common_malformed_feed_characters(self) -> None:
        """Bare ampersands and invalid control chars are sanitized once."""
        records = parse_rss_records(_malformed_feed())

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Politico NOAA Style Feed")
        self.assertIn("Alpha & Beta", records[0].content)

    def test_arxiv_api_parser_extracts_paper_metadata(self) -> None:
        """arXiv Atom API entries preserve abstracts, authors, and links."""
        records = parse_arxiv_api_records(_arxiv_api_feed(), ("science",))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.title, "Startup Knowledge Graphs")
        self.assertIn("venture capital", record.content)
        self.assertEqual(record.author, "Ada Lovelace, Grace Hopper")
        self.assertEqual(record.tags, ("science", "cs.AI", "cs.CL"))
        self.assertEqual(record.metadata["arxiv_id"], "2605.00001v1")
        self.assertEqual(record.metadata["doi"], "10.1234/example")
        self.assertEqual(
            record.metadata["pdf_url"], "https://arxiv.org/pdf/2605.00001v1"
        )


def _sample_text(name: str) -> str:
    return (SAMPLE_DIR / name).read_text(encoding="utf-8")


def _content_encoded_feed() -> str:
    return """
    <rss version="2.0"><channel><item>
      <title>Alpha Beta</title>
      <link>https://example.org/alpha</link>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <![CDATA[<p>Alpha &amp; Beta analysis continues</p>]]>
      </content:encoded>
    </item></channel></rss>
    """


def _low_value_feed() -> str:
    return """
    <rss version="2.0"><channel>
      <item><title>Same Headline</title><link>https://example.org/1</link><description>Same Headline</description></item>
      <item><title>Short</title><link>https://example.org/2</link><description>Too short</description></item>
    </channel></rss>
    """


def _atom_feed() -> str:
    return """
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Atom Title</title>
        <link href="https://example.org/atom" />
        <id>atom-1</id>
        <updated>2026-05-09T10:00:00Z</updated>
        <summary>A useful Atom summary with enough detail for review.</summary>
      </entry>
    </feed>
    """


def _malformed_feed() -> str:
    return """
    junk before xml
    <rss version="2.0"><channel><item>
      <title>Politico NOAA Style Feed</title>
      <link>https://example.org/feed-item</link>
      <description>Alpha & Beta update includes NOAA control \x08 data and enough words.</description>
    </item></channel></rss>
    """


def _arxiv_api_feed() -> str:
    return """
    <feed xmlns="http://www.w3.org/2005/Atom"
          xmlns:arxiv="http://arxiv.org/schemas/atom">
      <entry>
        <id>http://arxiv.org/abs/2605.00001v1</id>
        <updated>2026-05-09T12:00:00Z</updated>
        <published>2026-05-08T12:00:00Z</published>
        <title>Startup Knowledge Graphs</title>
        <summary>We study venture capital signals in science news graphs.</summary>
        <author><name>Ada Lovelace</name></author>
        <author><name>Grace Hopper</name></author>
        <category term="cs.AI" />
        <category term="cs.CL" />
        <arxiv:doi>10.1234/example</arxiv:doi>
        <arxiv:comment>12 pages</arxiv:comment>
        <link href="https://arxiv.org/abs/2605.00001v1" rel="alternate" />
        <link href="https://arxiv.org/pdf/2605.00001v1" title="pdf" />
      </entry>
    </feed>
    """
