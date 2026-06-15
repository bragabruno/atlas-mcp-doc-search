"""Backend Protocols — all retrieval/embedding backends implement these.

Concrete implementations (ES, Qdrant, HTTP gateway) are injected at runtime.
Tests inject fakes so no live services are required.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlas_mcp_doc_search.domain import ChunkRecord, RankedResult


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


@runtime_checkable
class VectorWriter(Protocol):
    """Write-side protocol for upserting chunk vectors into Qdrant."""

    async def upsert(self, records: list[ChunkRecord], vectors: list[list[float]]) -> None:
        """Upsert *records* with their corresponding *vectors* into the store.

        Idempotency: callers may re-upsert the same point_id; the store MUST
        overwrite the existing point rather than duplicate it.
        ``records`` and ``vectors`` are parallel sequences of the same length.
        """
        ...


@runtime_checkable
class ESWriter(Protocol):
    """Write-side protocol for indexing chunk documents into Elasticsearch."""

    async def index(self, records: list[ChunkRecord]) -> None:
        """Index *records* into the ``doc_chunks`` ES index.

        Idempotency: callers use the chunk's stable ``id`` as the ES document
        ``_id``; repeated calls update the existing document, not duplicate it.
        """
        ...
