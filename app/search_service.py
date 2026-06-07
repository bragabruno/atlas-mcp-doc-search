"""SearchService — orchestrates hybrid retrieval and RRF fusion."""

from __future__ import annotations

import asyncio

from app.domain import Chunk
from app.protocols import BM25Client, EmbeddingsClient, VectorClient
from app.rrf import fuse


class SearchService:
    """Coordinate embedding, BM25, vector retrieval and RRF fusion."""

    def __init__(
        self,
        embeddings: EmbeddingsClient,
        bm25: BM25Client,
        vector: VectorClient,
    ) -> None:
        self._embeddings = embeddings
        self._bm25 = bm25
        self._vector = vector

    async def search(self, query: str, k: int = 8) -> list[Chunk]:
        """Execute hybrid search and return the top *k* fused chunks."""
        # Embed the query and run both retrievers concurrently.
        vector_embedding, bm25_results = await asyncio.gather(
            self._embeddings.embed(query),
            self._bm25.search(query, k),
        )
        vector_results = await self._vector.search(vector_embedding, k)
        return fuse(bm25_results, vector_results, top_k=k)
