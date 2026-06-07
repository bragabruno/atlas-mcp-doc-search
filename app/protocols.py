"""Backend Protocols — all retrieval/embedding backends implement these.

Concrete implementations (ES, Qdrant, HTTP gateway) are injected at runtime.
Tests inject fakes so no live services are required.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain import RankedResult


@runtime_checkable
class EmbeddingsClient(Protocol):
    """Produces a dense embedding vector for a query string."""

    async def embed(self, text: str) -> list[float]:
        """Return the embedding for *text*."""
        ...


@runtime_checkable
class BM25Client(Protocol):
    """Sparse (keyword) retrieval via Elasticsearch BM25."""

    async def search(self, query: str, k: int) -> list[RankedResult]:
        """Return up to *k* ranked results for *query*."""
        ...


@runtime_checkable
class VectorClient(Protocol):
    """Dense (vector) retrieval via Qdrant."""

    async def search(self, vector: list[float], k: int) -> list[RankedResult]:
        """Return up to *k* ranked results nearest to *vector*."""
        ...
