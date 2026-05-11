"""Discovery candidate review pages and actions."""

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from monitoring.discovery import approve_discovery_candidate, reject_discovery_candidate
from monitoring.models import DiscoveryCandidate


class DiscoveryCandidateListView(ListView):
    """List source discovery candidates for human review.

    Example:
        Visit `/candidates/?status=pending`.
    """

    model = DiscoveryCandidate
    paginate_by = 50
    template_name = "monitoring/discovery_candidate_list.html"
    context_object_name = "candidates"

    def get_queryset(self) -> QuerySet[DiscoveryCandidate]:
        """Return filtered source candidates.

        Example:
            Django calls this while rendering candidates.
        """
        queryset = self.model.objects.all()
        queryset = _filter_candidate_field(queryset, "status", self.request.GET)
        return _filter_candidate_field(queryset, "candidate_type", self.request.GET)


@require_POST
def approve_candidate_action(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """Approve one candidate and return to the candidate list.

    Example:
        `POST /candidates/1/approve/`
    """
    candidate = get_object_or_404(DiscoveryCandidate, pk=pk)
    approve_discovery_candidate(candidate)
    messages.success(request, f"Approved {candidate.name}")
    return redirect("monitoring:discovery-candidate-list")


@require_POST
def reject_candidate_action(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """Reject one candidate and return to the candidate list.

    Example:
        `POST /candidates/1/reject/`
    """
    candidate = get_object_or_404(DiscoveryCandidate, pk=pk)
    reject_discovery_candidate(candidate)
    messages.success(request, f"Rejected {candidate.name}")
    return redirect("monitoring:discovery-candidate-list")


def _filter_candidate_field(
    queryset: QuerySet[DiscoveryCandidate],
    field_name: str,
    values: object,
) -> QuerySet[DiscoveryCandidate]:
    value = values.get(field_name, "") if hasattr(values, "get") else ""
    if not value:
        return queryset
    return queryset.filter(**{field_name: value})
