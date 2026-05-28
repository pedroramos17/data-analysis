"""Provider-neutral instruction templates for cloud job specs."""


PROVIDER_TEMPLATES: dict[str, str] = {
    "local_runner": "Run examples/run_cloud_job.py with the generated job spec.",
    "kaggle_notebook": "Upload repo, data artifacts, and job spec; run one partition.",
    "colab": "Mount storage, install optional requirements, and run one job spec.",
    "gcp": "Use a notebook, VM, or batch runner; prefer preemptible resources.",
    "aws": "Use a notebook, EC2, or batch runner; prefer spot for retryable jobs.",
    "azure": "Use a notebook, VM, or batch runner with portable artifact paths.",
}


def provider_template(provider: str) -> str:
    """Return generic provider instructions without requiring an SDK.

    Example:
        `provider_template("gcp")`
    """
    try:
        return PROVIDER_TEMPLATES[provider]
    except KeyError as error:
        expected = ", ".join(sorted(PROVIDER_TEMPLATES))
        message = f"Invalid provider {provider!r}; expected one of: {expected}"
        raise ValueError(message) from error


def render_provider_readme() -> str:
    """Render provider instructions for a generated cloud plan folder.

    Example:
        `text = render_provider_readme()`
    """
    lines = ["# Run Cloud Jobs", ""]
    lines.extend(f"## {name}\n\n{body}\n" for name, body in PROVIDER_TEMPLATES.items())
    return "\n".join(lines)
