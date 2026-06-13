"""ResearchSpace local research cockpit tests."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse


class ResearchSpaceUploadTests(TestCase):
    """PDF upload should create deduplicated local Paper records."""

    @override_settings(SOURCEFLOW_FEATURE_FLAGS={"RESEARCHSPACE_PDF_UPLOAD": True})
    def test_pdf_upload_creates_paper(self) -> None:
        """Uploading a PDF stores one local Paper."""
        response = self.client.post(
            reverse("researchspace:paper-upload"),
            {
                "title": "MCI-GRU",
                "pdf": SimpleUploadedFile(
                    "mci-gru.pdf",
                    b"%PDF-1.4 local paper",
                    content_type="application/pdf",
                ),
            },
        )

        from researchspace.models import Paper

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Paper.objects.get().title, "MCI-GRU")

    @override_settings(SOURCEFLOW_FEATURE_FLAGS={"RESEARCHSPACE_PDF_UPLOAD": True})
    def test_duplicate_pdf_hash_is_detected(self) -> None:
        """The same PDF bytes reuse the first Paper by sha256."""
        from researchspace.services.pdf_extraction import ingest_uploaded_pdf

        first = SimpleUploadedFile("paper-a.pdf", b"%PDF same")
        second = SimpleUploadedFile("paper-b.pdf", b"%PDF same")

        first_result = ingest_uploaded_pdf("First", first)
        second_result = ingest_uploaded_pdf("Second", second)

        self.assertFalse(first_result.duplicate)
        self.assertTrue(second_result.duplicate)
        self.assertEqual(first_result.paper.pk, second_result.paper.pk)


class ResearchSpaceServiceTests(TestCase):
    """Core ResearchSpace services must work without paid APIs."""

    def test_chunking_preserves_page_ranges(self) -> None:
        """Merged chunks keep the first and last page numbers."""
        from researchspace.services.chunking import chunk_page_texts

        chunks = chunk_page_texts(
            [
                (1, "alpha market regime"),
                (2, "beta factor design"),
                (3, "gamma risk control"),
            ],
            max_chars=46,
        )

        self.assertEqual(chunks[0].page_start, 1)
        self.assertEqual(chunks[0].page_end, 2)
        self.assertEqual(chunks[1].page_start, 3)

    def test_vector_fallback_returns_relevant_chunks(self) -> None:
        """Simple search ranks overlapping local chunks first."""
        from researchspace.models import Paper, PaperChunk
        from researchspace.services.vector_search import search_paper_chunks

        paper = Paper.objects.create(title="Regime paper", sha256="abc")
        PaperChunk.objects.create(
            paper=paper,
            chunk_index=0,
            page_start=1,
            page_end=1,
            text="walk-forward regime factor validation",
        )
        PaperChunk.objects.create(
            paper=paper,
            chunk_index=1,
            page_start=2,
            page_end=2,
            text="unrelated appendix",
        )

        results = search_paper_chunks(paper, "regime validation", limit=1)

        self.assertEqual(results[0].chunk.chunk_index, 0)

    @override_settings(SOURCEFLOW_FEATURE_FLAGS={"RESEARCHSPACE_LLM_PROVIDER": False})
    def test_ask_paper_returns_prompt_preview_without_llm(self) -> None:
        """No LLM provider still returns retrieved chunks and prompt preview."""
        from researchspace.models import Paper, PaperChunk
        from researchspace.services.ask_paper import answer_paper_question

        paper = Paper.objects.create(title="No API paper", sha256="def")
        PaperChunk.objects.create(
            paper=paper,
            chunk_index=0,
            page_start=4,
            page_end=4,
            text="MFDFA uses walk-forward validation.",
        )

        result = answer_paper_question(paper, "How is validation handled?")

        self.assertIn("prompt_preview", result)
        self.assertIn("MFDFA", result["retrieved_chunks"][0]["text"])

    def test_quant_extraction_parser_accepts_partial_json(self) -> None:
        """Partial model output is parsed safely instead of raising."""
        from researchspace.services.quant_schema import parse_quant_extraction_payload

        parsed = parse_quant_extraction_payload(
            '{"methodology": ["walk-forward"], "factors": ['
        )

        self.assertEqual(parsed["methodology"], ["walk-forward"])
        self.assertEqual(parsed["factors"], [])

    def test_invalid_support_status_is_handled_safely(self) -> None:
        """Unknown support labels become NEEDS_REVIEW."""
        from researchspace.services.status import normalize_support_status

        self.assertEqual(normalize_support_status("certain"), "NEEDS_REVIEW")

    def test_factor_candidate_defaults_to_needs_backtest(self) -> None:
        """Generated factor candidates start unvalidated."""
        from researchspace.models import FactorCandidate, Paper

        paper = Paper.objects.create(title="Factor paper", sha256="ghi")
        candidate = FactorCandidate.objects.create(
            paper=paper,
            name="RegimeSpread",
            expression_json={"kind": "operand", "name": "spread"},
        )

        self.assertEqual(candidate.status, "NEEDS_BACKTEST")

    def test_no_profitability_claims_in_generated_prompts(self) -> None:
        """Prompt export keeps research framing and avoids profit claims."""
        from researchspace.models import FactorCandidate, Paper
        from researchspace.services.prompt_export import build_codex_prompt

        paper = Paper.objects.create(title="Prompt paper", sha256="jkl")
        candidate = FactorCandidate.objects.create(
            paper=paper,
            name="RiskSignal",
            expression_json={"kind": "operand", "name": "risk_signal"},
        )

        prompt = build_codex_prompt(candidate)

        self.assertNotIn("profit", prompt.lower())
        self.assertIn("NEEDS_BACKTEST", prompt)

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"RESEARCHSPACE_PYMUPDF_EXTRACTION": False}
    )
    def test_feature_flags_block_disabled_optional_features(self) -> None:
        """Disabled optional extraction raises the central feature error."""
        from researchspace.services.pdf_extraction import extract_pdf_pages
        from sourceflow.config.feature_flags import FeatureDisabledError

        with self.assertRaisesRegex(FeatureDisabledError, "RESEARCHSPACE_PYMUPDF"):
            extract_pdf_pages("paper.pdf")


class ResearchSpacePageTests(TestCase):
    """Core ResearchSpace pages should render in the local Django app."""

    def test_pages_render_locally(self) -> None:
        """List, detail, upload, ask, extract, and lab pages return HTML."""
        from researchspace.models import Paper

        paper = Paper.objects.create(title="Render paper", sha256="mno")
        urls = [
            reverse("researchspace:paper-list"),
            reverse("researchspace:paper-upload"),
            reverse("researchspace:paper-detail", args=[paper.pk]),
            reverse("researchspace:paper-ask", args=[paper.pk]),
            reverse("researchspace:paper-extract", args=[paper.pk]),
            reverse("researchspace:factor-lab"),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
