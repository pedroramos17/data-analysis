"""Sentence embedding wrapper for local all-MiniLM-L6-v2 models."""

from __future__ import annotations

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def embed_text(
    text: str, model_name: str = DEFAULT_EMBEDDING_MODEL
) -> dict[str, object]:
    """Build one CPU embedding vector from a locally cached model.

    Example:
        `embed_text("market risk report")`
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        return _embedding_error(model_name, error)
    try:
        model = SentenceTransformer(model_name, device="cpu", local_files_only=True)
        vector = model.encode(text, normalize_embeddings=True).tolist()
    except Exception as error:
        return _embedding_error(model_name, error)
    return _embedding_payload(model_name, vector)


def _embedding_payload(model_name: str, vector: list[float]) -> dict[str, object]:
    rounded = [round(float(value), 6) for value in vector]
    payload = {"backend": model_name, "vector": rounded, "dimensions": len(rounded)}
    payload["error"] = ""
    return payload


def _embedding_error(model_name: str, error: Exception) -> dict[str, object]:
    message = (
        f"Embedding unavailable for {model_name}; expected locally downloaded "
        f"sentence-transformers model: {error}"
    )
    return {
        "backend": f"{model_name}:unavailable",
        "vector": [],
        "dimensions": 0,
        "error": message,
    }
