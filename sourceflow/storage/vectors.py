"""Embedding storage for sourceflow.

The default :class:`LocalVectorStore` is a dependency-light, NumPy-backed cosine
index using a deterministic hashing embedder -- it works everywhere and persists
to disk reproducibly. FAISS and Chroma are supported as optional backends via
:func:`vector_store`; when they are not installed the factory raises a clear
error rather than failing obscurely, so the local store stays the safe default.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Protocol


class MissingVectorBackend(RuntimeError):
    """Raised when an optional vector backend (faiss/chroma) is not installed."""


def embed_text(text: str, *, dim: int = 64) -> list[float]:
    """Deterministic hashing embedder -> L2-normalized dense vector."""
    import numpy as np

    vector = np.zeros(dim, dtype="float64")
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        bucket = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vector[bucket] += 1.0
    norm = float(np.linalg.norm(vector))
    if norm:
        vector /= norm
    return vector.tolist()


class VectorStore(Protocol):
    """Provider contract for an embedding store."""

    def add(self, identifier: str, vector: list[float]) -> None: ...
    def search(self, vector: list[float], *, k: int = 5) -> list[tuple[str, float]]: ...
    def __len__(self) -> int: ...


class LocalVectorStore:
    """NumPy-backed cosine-similarity vector store with reproducible persistence."""

    def __init__(self, dim: int = 64) -> None:
        import numpy as np

        self.dim = dim
        self._ids: list[str] = []
        self._matrix = np.zeros((0, dim), dtype="float64")

    def add(self, identifier: str, vector: list[float]) -> None:
        import numpy as np

        row = np.asarray(vector, dtype="float64").reshape(1, -1)
        if row.shape[1] != self.dim:
            raise ValueError(f"vector dim {row.shape[1]} != store dim {self.dim}")
        self._ids.append(str(identifier))
        self._matrix = np.vstack([self._matrix, row])

    def add_many(self, items: Iterable[tuple[str, list[float]]]) -> None:
        for identifier, vector in items:
            self.add(identifier, vector)

    def search(self, vector: list[float], *, k: int = 5) -> list[tuple[str, float]]:
        import numpy as np

        if not self._ids:
            return []
        query = np.asarray(vector, dtype="float64")
        query_norm = np.linalg.norm(query) or 1.0
        row_norms = np.linalg.norm(self._matrix, axis=1)
        row_norms[row_norms == 0] = 1.0
        scores = (self._matrix @ query) / (row_norms * query_norm)
        order = np.argsort(-scores)[: max(0, k)]
        return [(self._ids[i], float(scores[i])) for i in order]

    def __len__(self) -> int:
        return len(self._ids)

    def save(self, directory: str | Path) -> Path:
        import numpy as np

        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vectors.npy", self._matrix)
        (path / "ids.json").write_text(json.dumps({"dim": self.dim, "ids": self._ids}), encoding="utf-8")
        return path

    @classmethod
    def load(cls, directory: str | Path) -> "LocalVectorStore":
        import numpy as np

        path = Path(directory)
        meta = json.loads((path / "ids.json").read_text(encoding="utf-8"))
        store = cls(dim=int(meta["dim"]))
        store._ids = list(meta["ids"])
        store._matrix = np.load(path / "vectors.npy")
        return store


def build_chunk_vectors(*, dim: int = 64, store: LocalVectorStore | None = None) -> LocalVectorStore:
    """Embed every canonical document chunk into a local vector store."""
    from sourceflow.models import DocumentChunk

    store = store or LocalVectorStore(dim=dim)
    for chunk in DocumentChunk.objects.order_by("pk").values("id", "text"):
        store.add(f"chunk:{chunk['id']}", embed_text(chunk["text"], dim=dim))
    return store


def vector_store(backend: str = "local", *, dim: int = 64):
    """Return a vector store for the requested backend.

    ``local`` is always available. ``faiss``/``chroma`` are optional; if the
    library is not installed a :class:`MissingVectorBackend` error is raised.
    """
    backend = backend.lower()
    if backend == "local":
        return LocalVectorStore(dim=dim)
    if backend == "faiss":
        try:
            import faiss  # noqa: F401
        except ImportError as exc:
            raise MissingVectorBackend(
                "faiss is not installed; install faiss-cpu or use backend='local'"
            ) from exc
        return _FaissVectorStore(dim=dim)  # pragma: no cover - requires optional dep
    if backend == "chroma":
        try:
            import chromadb  # noqa: F401
        except ImportError as exc:
            raise MissingVectorBackend(
                "chromadb is not installed; install chromadb or use backend='local'"
            ) from exc
        return _ChromaVectorStore(dim=dim)  # pragma: no cover - requires optional dep
    raise ValueError(f"unknown vector backend: {backend!r}")


class _FaissVectorStore:  # pragma: no cover - exercised only when faiss is installed
    def __init__(self, dim: int = 64) -> None:
        import faiss
        import numpy as np

        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._ids: list[str] = []
        self._np = np

    def add(self, identifier: str, vector: list[float]) -> None:
        self._ids.append(str(identifier))
        self._index.add(self._np.asarray([vector], dtype="float32"))

    def search(self, vector: list[float], *, k: int = 5) -> list[tuple[str, float]]:
        scores, idx = self._index.search(self._np.asarray([vector], dtype="float32"), k)
        return [(self._ids[i], float(s)) for s, i in zip(scores[0], idx[0]) if 0 <= i < len(self._ids)]

    def __len__(self) -> int:
        return len(self._ids)


class _ChromaVectorStore:  # pragma: no cover - exercised only when chromadb is installed
    def __init__(self, dim: int = 64) -> None:
        import chromadb

        self.dim = dim
        self._client = chromadb.EphemeralClient()
        self._collection = self._client.create_collection("sourceflow")

    def add(self, identifier: str, vector: list[float]) -> None:
        self._collection.add(ids=[str(identifier)], embeddings=[vector])

    def search(self, vector: list[float], *, k: int = 5) -> list[tuple[str, float]]:
        result = self._collection.query(query_embeddings=[vector], n_results=k)
        ids = result["ids"][0]
        distances = result.get("distances", [[0.0] * len(ids)])[0]
        return [(identifier, float(1.0 - distance)) for identifier, distance in zip(ids, distances)]

    def __len__(self) -> int:
        return self._collection.count()
