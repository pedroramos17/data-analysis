"""Admin registration for canonical Sourceflow models."""

from __future__ import annotations

from django.contrib import admin

from sourceflow import models


CANONICAL_MODELS = (
    models.ProviderOwner,
    models.Source,
    models.Document,
    models.DocumentChunk,
    models.Entity,
    models.EntityAlias,
    models.EntityMention,
    models.Claim,
    models.Event,
    models.EvidenceSpan,
    models.KnowledgeEdge,
    models.AssumptionPolicy,
    models.Belief,
    models.Justification,
    models.InferenceRule,
    models.RetractionLog,
    models.RetrievalTrace,
    models.RiskFactor,
    models.Asset,
    models.Instrument,
    models.PortfolioPosition,
)


for model in CANONICAL_MODELS:
    admin.site.register(model)
