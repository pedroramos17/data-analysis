"""Forms for ResearchSpace local paper workflows."""

from __future__ import annotations

from django import forms


class PaperUploadForm(forms.Form):
    """Upload one local research PDF."""

    title = forms.CharField(max_length=240, required=False)
    pdf = forms.FileField()


class PaperQuestionForm(forms.Form):
    """Ask a retrieval-first question over one paper."""

    question = forms.CharField(widget=forms.Textarea, min_length=3)


class ExtractionForm(forms.Form):
    """Optional raw extraction payload for parser testing."""

    raw_response = forms.CharField(widget=forms.Textarea, required=False)
