"""URL routes for the Phase 11 minimal UI screens (mounted under /sourceflow/)."""

from __future__ import annotations

from django.urls import path

from sourceflow.ui import views

app_name = "sourceflow_ui"

urlpatterns = [
    path("", views.index, name="index"),
    path("documents/", views.document_explorer, name="documents"),
    path("entities/", views.entity_list, name="entities"),
    path("entities/<int:entity_id>/", views.entity_profile, name="entity-profile"),
    path("claims/", views.claim_explorer, name="claims"),
    path("events/", views.event_clusters, name="event-clusters"),
    path("source-comparison/", views.source_comparison, name="source-comparison"),
    path("source-comparison/event/<int:event_id>/", views.source_comparison, name="source-comparison-event"),
    path("kg/path/", views.kg_path_view, name="kg-path"),
    path("beliefs/", views.belief_list, name="beliefs"),
    path("beliefs/<int:belief_id>/", views.belief_explanation, name="belief-explanation"),
    path("graphrag/", views.graphrag_query_view, name="graphrag"),
    path("risk/", views.risk_view, name="risk"),
    path("risk/<int:asset_id>/", views.risk_view, name="risk-asset"),
    path("portfolio/", views.portfolio_view, name="portfolio"),
]
