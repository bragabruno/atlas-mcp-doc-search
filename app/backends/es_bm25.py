"""Elasticsearch BM25 backend.

Searches the ``doc_chunks`` index and maps Elasticsearch hits to RankedResult.
The client is injected so it can be swapped in tests.
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from app.domain import RankedResult

_INDEX = "doc_chunks"


class ElasticsearchBM25Client:
    """Implements BM25Client using the async Elasticsearch Python SDK."""

    def __init__(self, client: AsyncElasticsearch) -> None:
        self._client = client

    async def search(self, query: str, k: int) -> list[RankedResult]:
        """Full-text search over the ``doc_chunks`` index."""
        response = await self._client.search(
            index=_INDEX,
            body={
                "size": k,
                "query": {"match": {"text": query}},
            },
        )
        results: list[RankedResult] = []
        for rank, hit in enumerate(response["hits"]["hits"], start=1):
            source = hit["_source"]
            results.append(
                RankedResult(
                    id=hit["_id"],
                    text=source["text"],
                    source_id=source["source_id"],
                    rank=rank,
                )
            )
        return results
