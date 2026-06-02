"""SQLite metadata models for the QuantSpace research cockpit."""

from __future__ import annotations

from django.db import models

from quantspace.services.status import support_status_choices


class Paper(models.Model):
    """A locally stored research paper.

    Example:
        `Paper.objects.create(title="MFDFA", sha256="...")`
    """

    title = models.CharField(max_length=240)
    original_filename = models.CharField(max_length=255, blank=True)
    pdf_file = models.FileField(upload_to="quantspace/papers/", blank=True)
    sha256 = models.CharField(max_length=64, unique=True)
    mime_type = models.CharField(max_length=120, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["sha256"]), models.Index(fields=["title"])]

    def __str__(self) -> str:
        """Return the paper title used in lists."""
        return self.title


class PaperChunk(models.Model):
    """A searchable paper text chunk with page provenance.

    Example:
        `PaperChunk.objects.filter(paper=paper, page_start__lte=4)`
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    text = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    embedding_json = models.JSONField(default=list, blank=True)
    support_status = models.CharField(
        max_length=32,
        choices=support_status_choices(),
        default="SUPPORTED",
    )
    metadata_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["paper_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["paper", "chunk_index"],
                name="uniq_quantspace_paper_chunk",
            )
        ]
        indexes = [models.Index(fields=["paper", "page_start", "page_end"])]

    def __str__(self) -> str:
        """Return a compact chunk label."""
        return f"{self.paper_id}:{self.chunk_index}"


class PaperArtifact(models.Model):
    """A local artifact derived from one paper.

    Example:
        `PaperArtifact.objects.filter(artifact_type="chunks_parquet")`
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=80)
    path = models.CharField(max_length=1200, blank=True)
    content = models.TextField(blank=True)
    support_status = models.CharField(
        max_length=32,
        choices=support_status_choices(),
        default="NEEDS_REVIEW",
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["paper", "artifact_type"])]

    def __str__(self) -> str:
        """Return the artifact identity."""
        return f"{self.paper_id}:{self.artifact_type}"


class PaperQuestion(models.Model):
    """A local paper question and retrieval-first answer.

    Example:
        `PaperQuestion.objects.create(paper=paper, question="What is tested?")`
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="questions")
    question = models.TextField()
    answer = models.TextField(blank=True)
    prompt_preview = models.TextField(blank=True)
    llm_provider = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=32, default="RETRIEVAL_ONLY")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the question label."""
        return self.question[:80]


class PaperCitation(models.Model):
    """A page citation supporting a question or extraction.

    Example:
        `PaperCitation.objects.filter(question=question)`
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="citations")
    question = models.ForeignKey(
        PaperQuestion,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="citations",
    )
    chunk = models.ForeignKey(
        PaperChunk, null=True, blank=True, on_delete=models.SET_NULL
    )
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    quote = models.TextField(blank=True)
    support_status = models.CharField(
        max_length=32,
        choices=support_status_choices(),
        default="SUPPORTED",
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["paper_id", "page_start"]

    def __str__(self) -> str:
        """Return the citation page range."""
        return f"{self.paper_id}:p{self.page_start}-{self.page_end}"


class QuantExtraction(models.Model):
    """Structured Quant 4.0 methodology extracted from a paper.

    Example:
        `QuantExtraction.objects.filter(support_status="PARTIAL")`
    """

    paper = models.ForeignKey(
        Paper, on_delete=models.CASCADE, related_name="extractions"
    )
    extraction_json = models.JSONField(default=dict, blank=True)
    raw_response = models.TextField(blank=True)
    prompt_preview = models.TextField(blank=True)
    support_status = models.CharField(
        max_length=32,
        choices=support_status_choices(),
        default="NEEDS_REVIEW",
    )
    status = models.CharField(max_length=32, default="DRAFT")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the extraction identity."""
        return f"{self.paper_id}:{self.status}"


class FactorCandidate(models.Model):
    """A symbolic factor candidate generated from paper evidence.

    Example:
        `FactorCandidate.objects.filter(status="NEEDS_BACKTEST")`
    """

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="factors")
    extraction = models.ForeignKey(
        QuantExtraction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="factors",
    )
    name = models.CharField(max_length=180)
    expression_json = models.JSONField(default=dict, blank=True)
    rationale = models.TextField(blank=True)
    prompt_preview = models.TextField(blank=True)
    support_status = models.CharField(
        max_length=32,
        choices=support_status_choices(),
        default="NEEDS_REVIEW",
    )
    status = models.CharField(max_length=40, default="NEEDS_BACKTEST")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "support_status"])]

    def __str__(self) -> str:
        """Return the candidate name."""
        return self.name
