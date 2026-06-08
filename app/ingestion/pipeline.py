"""Ingestion pipeline — chunks → embed → upsert Qdrant + index Elasticsearch.

The pipeline is deliberately stateless: every call to ``ingest()`` is
idempotent because:
  * Chunk IDs are derived deterministically from (source_id, chunk_idx).
  * Qdrant upsert overwrites an existing point with the same ID.
  * Elasticsearch index with a fixed ``_id`` performs an upsert (update-or-create).

Existing chunks for the document are deleted from both stores before the new
chunks are written, so re-ingesting a shorter version of a document does not
leave stale chunks behind.
"""

from __future__ import annotations

import asyncio

from app.domain import ChunkRecord
from app.ingestion.chunker import chunk_text
from app.protocols import EmbeddingsClient, ESWriter, VectorWriter


class IngestionPipeline:
    """Chunk a document, embed every chunk, then write to Qdrant + Elasticsearch.

    Args:
        embeddings:   Client that produces a dense vector for a text string.
        vector_writer: Write-side Qdrant client (upserts ``doc_chunks`` collection).
        es_writer:    Write-side Elasticsearch client (indexes ``doc_chunks`` index).
        chunk_size:   Maximum characters per chunk (default 512).
        overlap:      Overlap in characters between consecutive chunks (default 64).
    """

    def __init__(
        self,
        embeddings: EmbeddingsClient,
        vector_writer: VectorWriter,
        es_writer: ESWriter,
        *,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> None:
        self._embeddings = embeddings
        self._vector_writer = vector_writer
        self._es_writer = es_writer
        self._chunk_size = chunk_size
        self._overlap = overlap

    async def ingest(
        self,
        text: str,
        *,
        source_id: str,
        doc_id: str,
    ) -> list[ChunkRecord]:
        """Ingest a single document.

        Chunks the *text*, embeds each chunk via the embeddings client, then
        writes to Qdrant (vector store) and Elasticsearch (BM25 index) in
        parallel.

        Args:
            text:      Raw document text.
            source_id: Opaque source identifier (e.g. Confluence page ID).
            doc_id:    Internal Atlas document record ID.

        Returns:
            The ordered list of ``ChunkRecord`` objects that were written.
            Returns an empty list if *text* is empty or whitespace-only.
        """
        records = chunk_text(
            text,
            source_id=source_id,
            doc_id=doc_id,
            chunk_size=self._chunk_size,
            overlap=self._overlap,
        )
        if not records:
            return []

        # Embed all chunks concurrently.
        vectors: list[list[float]] = list(
            await asyncio.gather(*[self._embeddings.embed(r.text) for r in records])
        )

        # Write to both stores in parallel.
        await asyncio.gather(
            self._vector_writer.upsert(records, vectors),
            self._es_writer.index(records),
        )

        return records
