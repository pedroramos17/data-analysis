"""Alert review actions for human-in-loop workflows."""

from django.contrib import messages
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from monitoring.alerts import (
    acknowledge_alert_hit,
    duplicate_alert_hit,
    ignore_alert_hit,
    resolve_alert_hit,
)
from monitoring.models import AlertFeedback, AlertHit


@require_POST
def alert_status_action(
    request: HttpRequest,
    pk: int,
    status: str,
) -> HttpResponse:
    """Apply one alert status transition from the review page.

    Example:
        `POST /alerts/1/acknowledge/`
    """
    alert_hit = get_object_or_404(AlertHit, pk=pk)
    if not _apply_status(alert_hit, status):
        return HttpResponseBadRequest(
            f"Invalid alert status action {status}; expected acknowledge, resolve, ignore, or duplicate"
        )
    messages.success(request, f"Updated alert {alert_hit.title}")
    return redirect("monitoring:alert-hit-list")


@require_POST
def alert_feedback_action(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """Store human feedback on one generated alert.

    Example:
        `POST /alerts/1/feedback/`
    """
    alert_hit = get_object_or_404(AlertHit, pk=pk)
    AlertFeedback.objects.create(
        alert_hit=alert_hit,
        user=request.user if request.user.is_authenticated else None,
        label=request.POST.get("label", AlertFeedback.Label.USEFUL),
        comment=request.POST.get("comment", ""),
    )
    messages.success(request, "Saved alert feedback")
    return redirect("monitoring:alert-hit-list")


def _apply_status(alert_hit: AlertHit, status: str) -> bool:
    if status == "acknowledge":
        acknowledge_alert_hit(alert_hit)
        return True
    if status == "resolve":
        resolve_alert_hit(alert_hit)
        return True
    if status == "ignore":
        ignore_alert_hit(alert_hit)
        return True
    if status == "duplicate":
        duplicate_alert_hit(alert_hit)
        return True
    return False
