"""Admin registration for QuantSpace models."""

from __future__ import annotations

from django.contrib import admin

from quantspace.models import (
    FactorCandidate,
    Paper,
    PaperArtifact,
    PaperChunk,
    PaperCitation,
    PaperQuestion,
    QuantExtraction,
)

admin.site.register(Paper)
admin.site.register(PaperChunk)
admin.site.register(PaperArtifact)
admin.site.register(PaperQuestion)
admin.site.register(PaperCitation)
admin.site.register(QuantExtraction)
admin.site.register(FactorCandidate)
