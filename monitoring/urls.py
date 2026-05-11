"""URL routes for browsing normalized public-source records."""

from django.urls import path

from monitoring import alert_views, candidate_views, export_views, views

app_name = "monitoring"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("documents/", views.DocumentListView.as_view(), name="document-list"),
    path("alerts/", views.AlertHitListView.as_view(), name="alert-hit-list"),
    path(
        "alerts/<int:pk>/feedback/",
        alert_views.alert_feedback_action,
        name="alert-feedback-action",
    ),
    path(
        "alerts/<int:pk>/<str:status>/",
        alert_views.alert_status_action,
        name="alert-status-action",
    ),
    path(
        "candidates/",
        candidate_views.DiscoveryCandidateListView.as_view(),
        name="discovery-candidate-list",
    ),
    path(
        "candidates/<int:pk>/approve/",
        candidate_views.approve_candidate_action,
        name="approve-candidate-action",
    ),
    path(
        "candidates/<int:pk>/reject/",
        candidate_views.reject_candidate_action,
        name="reject-candidate-action",
    ),
    path("digest/", views.FeedDigestView.as_view(), name="feed-digest"),
    path(
        "exports/", views.ExportArtifactListView.as_view(), name="export-artifact-list"
    ),
    path(
        "exports/<int:pk>/",
        views.ExportArtifactDetailView.as_view(),
        name="export-artifact-detail",
    ),
    path(
        "exports/<int:pk>/rows/",
        export_views.parquet_rows_api,
        name="export-artifact-rows-api",
    ),
    path("topics/", views.TopicClusterListView.as_view(), name="topic-cluster-list"),
    path("sources/", views.SourceListView.as_view(), name="source-list"),
    path("sources/<int:pk>/", views.SourceDetailView.as_view(), name="source-detail"),
    path("failures/", views.DeadLetterListView.as_view(), name="dead-letter-list"),
    path(
        "actions/enrich-documents/",
        views.enrich_documents_action,
        name="enrich-documents-action",
    ),
    path(
        "actions/discover-sources/",
        views.discover_sources_action,
        name="discover-sources-action",
    ),
    path(
        "actions/evaluate-alerts/",
        views.evaluate_alerts_action,
        name="evaluate-alerts-action",
    ),
    path(
        "actions/cluster-topics/",
        views.cluster_topics_action,
        name="cluster-topics-action",
    ),
    path(
        "actions/score-source-reputation/",
        views.score_source_reputation_action,
        name="score-source-reputation-action",
    ),
    path(
        "actions/export-parquet/",
        views.export_parquet_action,
        name="export-parquet-action",
    ),
    path(
        "actions/nlp-pipeline/",
        views.nlp_pipeline_action,
        name="nlp-pipeline-action",
    ),
    path(
        "api/news/v1/list-feed-digest/",
        views.list_feed_digest_api,
        name="feed-digest-api",
    ),
]
