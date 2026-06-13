"""AGT-8 — Corpus ingestion pipeline.

Orchestrates end-to-end ingestion of a regulatory corpus:

  1. Read JSONL source (each line: {id, text, source_id}).
  2. Chunk each document (`chunker.chunk_document`).
  3. Embed each chunk in batches via the Atlas gateway `/v1/embeddings`.
  4. Write chunks to Qdrant (doc_chunks) and Elasticsearch (doc_chunks) in parallel.

Each step is fail-fast on error. The pipeline is idempotent if the index/collection
is cleared beforehand (Qdrant `upsert` and ES `index` are naturally idempotent for
the same chunk id).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from elasticsearch import AsyncElasticsearch
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from app.ingest.chunker import TextChunk, chunk_document

log = logging.getLogger(__name__)

_ES_INDEX = "doc_chunks"
_QDRANT_COLLECTION = "doc_chunks"
_EMBED_BATCH = 32


async def _embed_batch(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    texts: list[str],
) -> list[list[float]]:
    """Call gateway /v1/embeddings and return one vector per input."""
    resp = await client.post(
        f"{base_url.rstrip('/')}/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": texts, "model": model},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    # Sort by index to preserve input order.
    return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


async def _write_es(es: AsyncElasticsearch, chunks: list[TextChunk]) -> None:
    """Bulk-index chunks into Elasticsearch."""
    ops: list[Any] = []
    for c in chunks:
        ops.append({"index": {"_index": _ES_INDEX, "_id": c.id}})
        ops.append({"text": c.text, "source_id": c.source_id, "chunk_index": c.chunk_index})
    if ops:
        await es.bulk(body=ops, refresh=False)


async def _ensure_collection(qdrant: AsyncQdrantClient, vector_size: int) -> None:
    """Create the doc_chunks collection if absent (idempotent).

    Discovered on the first live run: upserting into a non-existent collection
    is a 404, so the pipeline must create it (cosine distance, dimensionality
    from the embedding model in use — 8 for the local mock, 1536+ for real ones).
    """
    from qdrant_client.models import Distance, VectorParams

    existing = {c.name for c in (await qdrant.get_collections()).collections}
    if _QDRANT_COLLECTION not in existing:
        await qdrant.create_collection(
            collection_name=_QDRANT_COLLECTION,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        log.info("created qdrant collection %s (dim=%d)", _QDRANT_COLLECTION, vector_size)


async def _write_qdrant(
    qdrant: AsyncQdrantClient,
    chunks: list[TextChunk],
    vectors: list[list[float]],
) -> None:
    """Upsert chunk vectors into Qdrant."""
    points = [
        PointStruct(
            id=abs(hash(c.id)) % (2**63),
            vector=vec,
            payload={
                "chunk_id": c.id,
                "text": c.text,
                "source_id": c.source_id,
                "chunk_index": c.chunk_index,
            },
        )
        for c, vec in zip(chunks, vectors, strict=True)
    ]
    await qdrant.upsert(collection_name=_QDRANT_COLLECTION, points=points)


async def _iter_source(path: Path) -> AsyncIterator[dict[str, str]]:
    """Yield documents from a JSONL file (each line an {id, source_id, text} object)."""
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                doc: dict[str, str] = json.loads(line)
                yield doc


async def run_ingestion(
    *,
    source_path: Path,
    gateway_url: str,
    gateway_api_key: str,
    embed_model: str,
    es_url: str,
    qdrant_url: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> int:
    """Ingest the corpus at *source_path* and return the total chunks written."""
    # AsyncQdrantClient is NOT an async context manager (qdrant-client 1.18) —
    # construct it plainly and close in `finally`. Discovered on first live run;
    # the unit tests use fakes so this never surfaced offline.
    qdrant = AsyncQdrantClient(url=qdrant_url)
    try:
        async with (
            httpx.AsyncClient() as http,
            AsyncElasticsearch([es_url]) as es,
        ):
            total = 0
            batch: list[TextChunk] = []

            async def flush() -> None:
                nonlocal total
                if not batch:
                    return
                texts = [c.text for c in batch]
                vectors = await _embed_batch(http, gateway_url, gateway_api_key, embed_model, texts)
                if vectors:
                    await _ensure_collection(qdrant, vector_size=len(vectors[0]))
                await asyncio.gather(
                    _write_es(es, batch),
                    _write_qdrant(qdrant, batch, vectors),
                )
                total += len(batch)
                log.info("ingested %d chunks (total %d)", len(batch), total)
                batch.clear()

            async for doc in _iter_source(source_path):
                chunks = chunk_document(
                    text=doc.get("text", ""),
                    source_id=doc.get("source_id", doc.get("id", "unknown")),
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                batch.extend(chunks)
                if len(batch) >= _EMBED_BATCH:
                    await flush()

            await flush()  # remainder
            log.info("ingestion complete — %d total chunks", total)
            return total
    finally:
        await qdrant.close()
