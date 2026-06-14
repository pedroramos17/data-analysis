"""Tests for the Quant systems cookbook preview."""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import reverse


class ResearchCookbookTests(SimpleTestCase):
    """Cookbook content should be complete and locally previewable."""

    def test_cookbook_route_renders_new_systems(self) -> None:
        """The live preview page lists all first-class quant systems."""
        response = self.client.get(reverse("monitoring:research-cookbook"))

        self.assertEqual(response.status_code, 200)
        for label in _system_labels():
            self.assertContains(response, label)

    def test_cookbook_route_lists_validation_and_safety_boundaries(self) -> None:
        """The page documents validation commands and local-only boundaries."""
        response = self.client.get(reverse("monitoring:research-cookbook"))

        for expected_text in _required_page_text():
            self.assertContains(response, expected_text)

    def test_cookbook_sections_have_run_and_test_paths(self) -> None:
        """Every section has executable commands or routes and tests."""
        from monitoring.cookbook import research_cookbook_sections

        for section in research_cookbook_sections():
            self.assertTrue(
                section.run_commands or section.routes,
                msg=f"{section.name} lacks run commands or routes",
            )
            self.assertTrue(section.test_commands, msg=f"{section.name} lacks tests")

    def test_next_improvements_have_priority_and_rationale(self) -> None:
        """Each next-improvement item is actionable and prioritized."""
        from monitoring.cookbook import next_improvement_groups

        for group in next_improvement_groups():
            self.assertTrue(group.items, msg=f"{group.title} has no items")
            for item in group.items:
                self.assertTrue(item.priority)
                self.assertTrue(item.rationale)


def _system_labels() -> tuple[str, ...]:
    return (
        "ResearchSpace",
        "Quant Core",
        "MarketLab",
        "Graphs And Topology",
        "Risk And Regime",
        "Portfolio",
        "LOB Microstructure",
        "Full Experiment",
        "Multifractal",
    )


def _required_page_text() -> tuple[str, ...]:
    return (
        "ruff check quant",
        "manage.py check",
        "makemigrations --check --dry-run",
        "manage.py test quant",
        "manage.py test",
        "No paid API dependency",
        "No live trading",
        "Optional dependencies fail clearly",
        "No fake metrics",
    )
