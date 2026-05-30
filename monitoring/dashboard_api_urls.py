"""URL routes for the internal dashboard JSON API."""

from django.urls import path

from monitoring import dashboard_api as api


urlpatterns = [
    path("status/", api.dashboard_status_api, name="dashboard-api-status"),
    path("jobs/", api.dashboard_jobs_api, name="dashboard-api-jobs"),
    path(
        "jobs/<int:pk>/events/",
        api.dashboard_job_events_api,
        name="dashboard-api-job-events",
    ),
    path(
        "jobs/<int:pk>/logs/",
        api.dashboard_job_logs_api,
        name="dashboard-api-job-logs",
    ),
    path(
        "jobs/<int:pk>/<str:action>/",
        api.dashboard_job_action_api,
        name="dashboard-api-job-action",
    ),
    path("resources/", api.dashboard_resources_api, name="dashboard-api-resources"),
    path(
        "resources/refresh/",
        api.dashboard_resources_refresh_api,
        name="dashboard-api-resources-refresh",
    ),
    path("budget/", api.dashboard_budget_api, name="dashboard-api-budget"),
    path(
        "budget/policies/<int:pk>/update/",
        api.dashboard_budget_policy_update_api,
        name="dashboard-api-budget-policy-update",
    ),
]
