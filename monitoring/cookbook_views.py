"""Read-only live preview views for research cookbooks."""

from __future__ import annotations

from django.views.generic import TemplateView

from monitoring.cookbook import (
    global_validation_commands,
    local_safety_boundaries,
    next_improvement_groups,
    research_cookbook_sections,
)


class ResearchCookbookView(TemplateView):
    """Render the Quant systems cookbook without executing commands.

    Example:
        Visit `/cookbook/` during local development.
    """

    template_name = "monitoring/cookbook.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add structured cookbook sections and safety notes."""
        context = super().get_context_data(**kwargs)
        context["cookbook_sections"] = research_cookbook_sections()
        context["validation_commands"] = global_validation_commands()
        context["safety_boundaries"] = local_safety_boundaries()
        context["next_improvement_groups"] = next_improvement_groups()
        return context
