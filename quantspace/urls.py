"""QuantSpace URL routes."""

from __future__ import annotations

from django.urls import path

from quantspace import views

app_name = "quantspace"

urlpatterns = [
    path("papers/", views.PaperListView.as_view(), name="paper-list"),
    path("papers/upload/", views.paper_upload_view, name="paper-upload"),
    path("papers/<int:pk>/", views.PaperDetailView.as_view(), name="paper-detail"),
    path("papers/<int:pk>/ask/", views.paper_ask_view, name="paper-ask"),
    path("papers/<int:pk>/extract/", views.paper_extract_view, name="paper-extract"),
    path(
        "papers/<int:pk>/factors/",
        views.generate_factors_for_latest_extraction,
        name="paper-generate-factors",
    ),
    path("factor-lab/", views.FactorLabView.as_view(), name="factor-lab"),
]
