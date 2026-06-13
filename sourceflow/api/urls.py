"""URL routes for the Phase 11 sourceflow knowledge API.

Mounted under ``/sourceflow/api/`` by the project URLconf, so the canonical
paths from the Phase 11 spec become e.g. ``/sourceflow/api/documents`` and
``/sourceflow/api/beliefs/<id>/explain``.
"""

from __future__ import annotations

from django.urls import path

from sourceflow.api import views

app_name = "sourceflow_api"

urlpatterns = [
    path("documents", views.documents, name="documents"),
    path("entities", views.entities, name="entities"),
    path("claims", views.claims, name="claims"),
    path("events", views.events, name="events"),
    path("kg/entity/<str:entity_id>", views.kg_entity, name="kg-entity"),
    path("kg/path", views.kg_path, name="kg-path"),
    path("beliefs/<int:belief_id>/explain", views.belief_explain, name="belief-explain"),
    path("reasoning/run", views.reasoning_run, name="reasoning-run"),
    path("graphrag/query", views.graphrag_query, name="graphrag-query"),
    path("source-comparison/event/<int:event_id>", views.source_comparison_event, name="source-comparison-event"),
    path("quant/risk/<str:asset_id>", views.quant_risk, name="quant-risk"),
    path("quant/portfolio/explain", views.quant_portfolio_explain, name="quant-portfolio-explain"),
]
