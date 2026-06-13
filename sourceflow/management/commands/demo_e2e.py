"""Run the Phase 15 end-to-end demo from a single command.

    manage.py demo_e2e            # run the demo, print the full JSON report
    manage.py demo_e2e --summary  # print just the step headlines + invariants

The demo ingests a cluster of articles about a company facing a regulatory
investigation and produces all ten required outputs, then prints the
Definition-of-Done invariants (evidence, justification, auditability).
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db import transaction

from sourceflow.orchestration import run_end_to_end_demo


class Command(BaseCommand):
    help = "Run the sourceflow end-to-end demo (ingest -> ... -> portfolio explanation)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--summary", action="store_true", help="Print headlines + invariants only")
        parser.add_argument(
            "--keep", action="store_true",
            help="Persist the demo data (default rolls it back so the command is repeatable)",
        )

    def handle(self, *args, **options) -> None:
        if options.get("keep"):
            report = run_end_to_end_demo()
        else:
            # Roll back the seeded demo data so the command can be run repeatedly.
            report = self._run_and_rollback()

        if options.get("summary"):
            self._print_summary(report)
        else:
            self.stdout.write(json.dumps(report, indent=2, default=str))

    def _run_and_rollback(self) -> dict:
        captured: dict = {}

        class _Rollback(Exception):
            pass

        try:
            with transaction.atomic():
                captured.update(run_end_to_end_demo())
                raise _Rollback
        except _Rollback:
            pass
        return captured

    def _print_summary(self, report: dict) -> None:
        self.stdout.write(self.style.SUCCESS(report.get("scenario", "")))
        for key, value in report.get("steps", {}).items():
            if isinstance(value, list):
                headline = f"{len(value)} item(s)"
            elif isinstance(value, dict):
                headline = ", ".join(f"{k}={value[k]}" for k in list(value)[:3])
            else:
                headline = str(value)
            self.stdout.write(f"  {key}: {headline}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Invariants:"))
        all_ok = True
        for name, ok in report.get("invariants", {}).items():
            all_ok = all_ok and bool(ok)
            mark = "PASS" if ok else "FAIL"
            self.stdout.write(f"  [{mark}] {name}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("DEFINITION OF DONE MET" if all_ok else "INVARIANTS FAILED"))
