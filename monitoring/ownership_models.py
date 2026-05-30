"""Provider and owner metadata for source comparison."""

from urllib.parse import urlsplit

from django.db import models


class Owner(models.Model):
    """A source owner used for coverage comparisons.

    Example:
        `Owner.objects.create(name="Example Media", canonical_name="example media")`
    """

    name = models.CharField(max_length=180, unique=True)
    canonical_name = models.CharField(max_length=180, unique=True)
    homepage_url = models.URLField(max_length=1200, blank=True)
    country = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["canonical_name"])]

    def __str__(self) -> str:
        """Return the owner display name.

        Example:
            `str(owner)`
        """
        return self.name


class Provider(models.Model):
    """A publication provider that may belong to a larger owner.

    Example:
        `Provider.objects.create(name="Example Wire")`
    """

    name = models.CharField(max_length=180, unique=True)
    canonical_name = models.CharField(max_length=180, blank=True)
    domain = models.CharField(max_length=240, blank=True)
    owner = models.ForeignKey(
        Owner,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="providers",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["canonical_name"]),
            models.Index(fields=["domain"]),
        ]

    def __str__(self) -> str:
        """Return the provider display name.

        Example:
            `str(provider)`
        """
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        """Fill comparison defaults before saving.

        Example:
            `provider.save()`
        """
        if not self.canonical_name:
            self.canonical_name = canonical_provider_name(self.name)
        super().save(*args, **kwargs)


def canonical_provider_name(name: str) -> str:
    """Normalize a provider or owner name for grouping.

    Example:
        `canonical_provider_name(" Example Wire ")`
    """
    return " ".join(name.lower().split())


def domain_from_url(url: str) -> str:
    """Extract a lowercase hostname from a URL.

    Example:
        `domain_from_url("https://Example.org/feed.xml")`
    """
    if not url.strip():
        return ""
    return urlsplit(url).netloc.lower().split(":", 1)[0]
