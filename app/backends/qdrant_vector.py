"""Qdrant vector backend.

Searches the ``doc_chunks`` collection and maps Qdrant ScoredPoints to
RankedResult.  Payload fields follow the atlas-docs/03 schema:
  source_id, doc_id, chunk_idx, text.
"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import QueryResponse, ScoredPoint

from app.domain import RankedResult

_COLLECTION = "doc_chunks"


class QdrantVectorClient:
    """Implements VectorClient using the async Qdrant Python SDK."""

    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def search(self, vector: list[float], k: int) -> list[RankedResult]:
        """Cosine-similarity search over ``doc_chunks`` collection."""
        response: QueryResponse = await self._client.query_points(
            collection_name=_COLLECTION,
            query=vector,
            limit=k,
            with_payload=True,
        )
        results: list[RankedResult] = []
        for rank, hit in enumerate(response.points, start=1):
            point: ScoredPoint = hit
            payload: dict[str, object] = point.payload or {}
            results.append(
                RankedResult(
                    id=str(point.id),
                    text=str(payload.get("text", "")),
                    source_id=str(payload.get("source_id", "")),
                    rank=rank,
                )
            )
        return results
