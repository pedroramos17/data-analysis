# Generated for Sourceflow comparison-machine foundation.

import hashlib
import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")


def backfill_source_providers(apps, schema_editor):
    Provider = apps.get_model("monitoring", "Provider")
    Source = apps.get_model("monitoring", "Source")
    for source in Source.objects.all():
        provider, _created = Provider.objects.get_or_create(
            name=source.name,
            defaults={
                "canonical_name": _canonical_name(source.name),
                "domain": _domain_from_url(source.url),
            },
        )
        source.provider_id = provider.id
        source.save(update_fields=["provider"])


def backfill_article_fields(apps, schema_editor):
    NormalizedDocument = apps.get_model("monitoring", "NormalizedDocument")
    for article in NormalizedDocument.objects.select_related("raw_event"):
        raw_url = (
            article.raw_event.url if article.raw_event_id else article.canonical_url
        )
        extracted_text = article.text or article.content
        article.url = raw_url or article.canonical_url
        article.url_hash = _url_hash(article.canonical_url)
        article.description = article.content[:700]
        article.extracted_text = extracted_text
        article.fetched_at = _article_fetched_at(article)
        article.status = "normalized"
        article.save(update_fields=_article_update_fields())


def _article_update_fields():
    return ["url", "url_hash", "description", "extracted_text", "fetched_at", "status"]


def _article_fetched_at(article):
    if article.raw_event_id and article.raw_event.fetched_at:
        return article.raw_event.fetched_at
    return article.ingested_at


def _canonical_name(name):
    return " ".join(name.lower().split())


def _domain_from_url(url):
    if not url:
        return ""
    return urlsplit(url).netloc.lower().split(":", 1)[0]


def _url_hash(raw_url):
    return hashlib.sha256(
        _canonicalize_article_url(raw_url).encode("utf-8")
    ).hexdigest()


def _canonicalize_article_url(raw_url):
    parts = urlsplit(raw_url.strip())
    query = _canonical_query(parts.query)
    netloc = _canonical_netloc(parts.scheme.lower(), parts.netloc.lower())
    path = _canonical_path(parts.path or "/")
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _canonical_query(query):
    pairs = parse_qsl(query, keep_blank_values=True)
    clean_pairs = [(key, value) for key, value in pairs if _keep_query_key(key)]
    return urlencode(sorted(clean_pairs), doseq=True)


def _keep_query_key(key):
    if key in TRACKING_QUERY_KEYS:
        return False
    return not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)


def _canonical_netloc(scheme, netloc):
    if scheme == "http" and netloc.endswith(":80"):
        return netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        return netloc[:-4]
    return netloc


def _canonical_path(path):
    if path != "/" and path.endswith("/"):
        return path[:-1]
    return path


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0010_custom_profile_type_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="Owner",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=180, unique=True)),
                ("canonical_name", models.CharField(max_length=180, unique=True)),
                ("homepage_url", models.URLField(blank=True, max_length=1200)),
                ("country", models.CharField(blank=True, max_length=80)),
                ("notes", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
                "indexes": [
                    models.Index(
                        fields=["canonical_name"], name="monitoring__canonic_8427d3_idx"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Provider",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=180, unique=True)),
                ("canonical_name", models.CharField(blank=True, max_length=180)),
                ("domain", models.CharField(blank=True, max_length=240)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="providers",
                        to="monitoring.owner",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "indexes": [
                    models.Index(
                        fields=["canonical_name"], name="monitoring__canonic_8137c4_idx"
                    ),
                    models.Index(
                        fields=["domain"], name="monitoring__domain_8ceb26_idx"
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="source",
            name="provider",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sources",
                to="monitoring.provider",
            ),
        ),
        migrations.RunPython(backfill_source_providers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="source",
            name="provider",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sources",
                to="monitoring.provider",
            ),
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="url",
            field=models.URLField(blank=True, default="", max_length=1200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="url_hash",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="description",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="extracted_text",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="fetched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="normalizeddocument",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("normalized", "Normalized"),
                    ("enriched", "Enriched"),
                    ("clustered", "Clustered"),
                    ("failed", "Failed"),
                ],
                default="normalized",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_article_fields, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(
                fields=["url_hash"], name="monitoring__url_has_e0e37f_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(fields=["status"], name="monitoring__status_f995fe_idx"),
        ),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(
                fields=["fetched_at"], name="monitoring__fetched_75561b_idx"
            ),
        ),
        migrations.AddField(
            model_name="topiccluster",
            name="merge_reason",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="topiccluster",
            name="merged_into",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="merged_events",
                to="monitoring.topiccluster",
            ),
        ),
        migrations.AddField(
            model_name="topiccluster",
            name="representative_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="representative_events",
                to="monitoring.normalizeddocument",
            ),
        ),
        migrations.AddField(
            model_name="documenttopic",
            name="link_reason",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="documenttopic",
            name="is_reviewed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documenttopic",
            name="is_incorrect",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="documenttopic",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="ArticleEmbedding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("backend", models.CharField(max_length=80)),
                ("model_name", models.CharField(blank=True, max_length=160)),
                ("vector", models.JSONField(blank=True, default=list)),
                ("dimensions", models.PositiveIntegerField(default=0)),
                ("text_hash", models.CharField(max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.normalizeddocument",
                    ),
                ),
            ],
            options={
                "ordering": ["article_id", "backend"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("article", "backend"),
                        name="unique_article_embedding_backend",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ArticleEntityMention",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("mention_text", models.CharField(max_length=240)),
                ("mention_count", models.PositiveIntegerField(default=1)),
                (
                    "confidence",
                    models.DecimalField(decimal_places=2, default=1, max_digits=5),
                ),
                ("backend", models.CharField(default="local_heuristic", max_length=80)),
                ("context", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.normalizeddocument",
                    ),
                ),
                (
                    "entity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.canonicalentity",
                    ),
                ),
            ],
            options={
                "ordering": ["article_id", "entity__name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("article", "entity", "backend"),
                        name="unique_article_entity_backend",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Claim",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("claim_text", models.TextField()),
                ("normalized_claim", models.CharField(max_length=500)),
                ("claim_type", models.CharField(default="statement", max_length=80)),
                (
                    "confidence",
                    models.DecimalField(decimal_places=2, default=1, max_digits=5),
                ),
                ("backend", models.CharField(default="local_heuristic", max_length=80)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.normalizeddocument",
                    ),
                ),
            ],
            options={
                "ordering": ["article_id", "id"],
                "indexes": [
                    models.Index(
                        fields=["normalized_claim"],
                        name="monitoring__normali_80c1af_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("article", "normalized_claim", "backend"),
                        name="unique_article_claim_backend",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="FrameFeature",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("feature_type", models.CharField(max_length=80)),
                ("value", models.FloatField(default=0)),
                ("evidence", models.JSONField(blank=True, default=dict)),
                ("backend", models.CharField(default="local_heuristic", max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.normalizeddocument",
                    ),
                ),
            ],
            options={
                "ordering": ["article_id", "feature_type"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("article", "feature_type", "backend"),
                        name="unique_article_frame_feature",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="EventCoverage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("coverage_type", models.CharField(max_length=20)),
                ("article_count", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("dominant_entities", models.JSONField(blank=True, default=list)),
                ("shared_claims", models.JSONField(blank=True, default=list)),
                ("unique_claims", models.JSONField(blank=True, default=list)),
                ("omissions", models.JSONField(blank=True, default=list)),
                ("framing", models.JSONField(blank=True, default=dict)),
                ("amplification_score", models.FloatField(default=1)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.topiccluster",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.owner",
                    ),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.provider",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["event_id", "coverage_type"],
                "indexes": [
                    models.Index(
                        fields=["event", "coverage_type"],
                        name="monitoring__event_i_e8dbc5_idx",
                    ),
                    models.Index(
                        fields=["provider"], name="monitoring__provide_1df53b_idx"
                    ),
                    models.Index(
                        fields=["owner"], name="monitoring__owner_i_20c9f9_idx"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ClaimCluster",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("normalized_claim", models.CharField(max_length=500)),
                ("representative_claim", models.TextField()),
                ("provider_count", models.PositiveIntegerField(default=0)),
                ("article_count", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.topiccluster",
                    ),
                ),
            ],
            options={
                "ordering": ["event_id", "representative_claim"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("event", "normalized_claim"),
                        name="unique_event_claim_cluster",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="EventComparisonSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "generated_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("snapshot_hash", models.CharField(max_length=64)),
                ("notes", models.TextField(blank=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.topiccluster",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at"],
                "indexes": [
                    models.Index(
                        fields=["event", "generated_at"],
                        name="monitoring__event_i_026165_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ClaimClusterMember",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("similarity", models.FloatField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "claim",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.claim",
                    ),
                ),
                (
                    "claim_cluster",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.claimcluster",
                    ),
                ),
            ],
            options={
                "ordering": ["claim_cluster_id", "claim_id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("claim_cluster", "claim"),
                        name="unique_claim_cluster_member",
                    )
                ],
            },
        ),
    ]
