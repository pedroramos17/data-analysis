"""URL routes for the multi-profile control dashboard."""

from django.urls import path

from monitoring import dashboard_control_views as views


urlpatterns = [
    path("", views.ControlDashboardView.as_view(), name="control-dashboard"),
    path("profiles/", views.ProfileConfigListView.as_view(), name="control-profiles"),
    path(
        "profiles/<int:pk>/update/",
        views.update_profile_action,
        name="control-profile-update",
    ),
    path("resources/", views.ResourceSnapshotListView.as_view(), name="control-resources"),
    path(
        "resources/refresh/",
        views.refresh_resources_action,
        name="control-resources-refresh",
    ),
    path("jobs/", views.PipelineJobListView.as_view(), name="control-jobs"),
    path("jobs/<int:pk>/", views.PipelineJobDetailView.as_view(), name="control-job-detail"),
    path(
        "jobs/<int:pk>/manifest/",
        views.job_manifest_download,
        name="control-job-manifest",
    ),
    path(
        "jobs/<int:pk>/<str:action>/",
        views.job_action,
        name="control-job-action",
    ),
    path("cloud-budget/", views.CloudBudgetView.as_view(), name="control-cloud-budget"),
    path("pipeline-plan/", views.pipeline_plan_view, name="control-pipeline-plan"),
    path("artifacts/", views.ArtifactDashboardView.as_view(), name="control-artifacts"),
    path("workers/", views.WorkerDashboardView.as_view(), name="control-workers"),
    path(
        "workers/stop-stale/",
        views.stop_stale_workers_action,
        name="control-workers-stop-stale",
    ),
]
