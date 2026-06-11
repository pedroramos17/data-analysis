# Generated manually to merge the financial-intelligence and comparison branches.

from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0008_financial_intelligence"),
        ("monitoring", "0012_topicclusterslice_topicclusterslicedocument_and_more"),
    ]

    operations: list[object] = []
