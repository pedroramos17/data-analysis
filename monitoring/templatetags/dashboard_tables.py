"""Reusable dashboard table rendering helpers."""

from dataclasses import dataclass

from django import template


register = template.Library()


@dataclass(frozen=True, slots=True)
class DashboardTableColumn:
    """One reusable dashboard table column.

    Example:
        `DashboardTableColumn("job", "Job")`
    """

    key: str
    label: str
    css_class: str = ""


@dataclass(frozen=True, slots=True)
class DashboardTableCell:
    """One reusable dashboard table cell.

    Example:
        `DashboardTableCell("Open", href="/jobs/1/")`
    """

    text: str
    href: str = ""
    css_class: str = ""


@dataclass(frozen=True, slots=True)
class DashboardTable:
    """Server-rendered dashboard table payload.

    Example:
        `DashboardTable("jobs", columns, rows, "No jobs")`
    """

    table_id: str
    columns: tuple[DashboardTableColumn, ...]
    rows: tuple[tuple[DashboardTableCell, ...], ...]
    empty_message: str
    caption: str = ""


@register.inclusion_tag("monitoring/components/data_table.html")
def dashboard_table(table: DashboardTable) -> dict[str, DashboardTable]:
    """Render a dashboard table with consistent overflow and resizing.

    Example:
        `{% dashboard_table recent_jobs_table %}`
    """
    return {"table": table}


def text_cell(text: object, css_class: str = "") -> DashboardTableCell:
    """Return a plain text table cell.

    Example:
        `cell = text_cell(job.status)`
    """
    return DashboardTableCell(str(text), "", css_class)


def link_cell(text: object, href: str, css_class: str = "") -> DashboardTableCell:
    """Return a linked table cell.

    Example:
        `cell = link_cell(job.job_name, "/dashboard/jobs/1/")`
    """
    return DashboardTableCell(str(text), href, css_class)
