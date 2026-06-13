"""Views for the ResearchSpace local research cockpit."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, ListView

from researchspace.forms import ExtractionForm, PaperQuestionForm, PaperUploadForm
from researchspace.models import FactorCandidate, Paper
from researchspace.services.ask_paper import answer_paper_question
from researchspace.services.factor_prompting import generate_factor_candidates
from researchspace.services.pdf_extraction import ingest_uploaded_pdf
from researchspace.services.quant_extraction import extract_quant_methodology


class PaperListView(ListView):
    """List local research papers."""

    model = Paper
    paginate_by = 50
    template_name = "researchspace/paper_list.html"
    context_object_name = "papers"


class PaperDetailView(DetailView):
    """Show chunks, questions, extractions, and factor candidates."""

    model = Paper
    template_name = "researchspace/paper_detail.html"
    context_object_name = "paper"


class FactorLabView(ListView):
    """List generated factor candidates for review."""

    model = FactorCandidate
    paginate_by = 50
    template_name = "researchspace/factor_lab.html"
    context_object_name = "factors"


@require_http_methods(["GET", "POST"])
def paper_upload_view(request: HttpRequest) -> HttpResponse:
    """Upload and deduplicate a local PDF."""
    form = PaperUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        result = ingest_uploaded_pdf(
            str(form.cleaned_data.get("title") or ""),
            form.cleaned_data["pdf"],
        )
        messages.success(request, result.message)
        return redirect("researchspace:paper-detail", pk=result.paper.pk)
    return render(request, "researchspace/paper_upload.html", {"form": form})


@require_http_methods(["GET", "POST"])
def paper_ask_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Ask a retrieval-first question over one paper."""
    paper = get_object_or_404(Paper, pk=pk)
    form = PaperQuestionForm(request.POST or None)
    result = None
    if request.method == "POST" and form.is_valid():
        result = answer_paper_question(paper, form.cleaned_data["question"])
    return render(
        request,
        "researchspace/paper_ask.html",
        {"paper": paper, "form": form, "result": result},
    )


@require_http_methods(["GET", "POST"])
def paper_extract_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Extract Quant methodology from one paper."""
    paper = get_object_or_404(Paper, pk=pk)
    form = ExtractionForm(request.POST or None)
    extraction = None
    if request.method == "POST" and form.is_valid():
        extraction = extract_quant_methodology(paper, form.cleaned_data["raw_response"])
        messages.success(request, "Quant methodology extraction saved")
    return render(
        request,
        "researchspace/paper_extract.html",
        {"paper": paper, "form": form, "extraction": extraction},
    )


@require_http_methods(["POST"])
def generate_factors_for_latest_extraction(
    request: HttpRequest, pk: int
) -> HttpResponse:
    """Generate factor candidates for the latest extraction."""
    paper = get_object_or_404(Paper, pk=pk)
    extraction = paper.extractions.first()
    if extraction is None:
        messages.success(request, "Run extraction before generating factors")
        return redirect("researchspace:paper-detail", pk=paper.pk)
    generate_factor_candidates(extraction)
    messages.success(request, "Factor candidates generated")
    return redirect("researchspace:factor-lab")
