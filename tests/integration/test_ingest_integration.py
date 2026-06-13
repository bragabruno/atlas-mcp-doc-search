"""Integration test — corpus ingestion against real Elasticsearch + Qdrant (AGT-8).

Spins ephemeral Elasticsearch and Qdrant containers via testcontainers and runs
the REAL `run_ingestion` pipeline against them, asserting chunks land in both
the ES `doc_chunks` index and the Qdrant `doc_chunks` collection. Only the
gateway embedding HTTP call is stubbed (deterministic 8-dim vectors) — the part
under test is the real-backend write path the offline unit tests can only fake,
exactly where the live bugs were (Qdrant client lifecycle + collection
creation, ES bulk shape).

Requires Docker. Marked `integration`, so excluded from the default offline
suite (`pytest`); run explicitly with `pytest -m integration`.
"""

# testcontainers is a namespace package without type stubs.
# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from elasticsearch import AsyncElasticsearch
from qdrant_client import AsyncQdrantClient

pytest.importorskip("testcontainers.elasticsearch")
pytest.importorskip("testcontainers.qdrant")
from testcontainers.elasticsearch import ElasticSearchContainer  # noqa: E402
from testcontainers.qdrant import QdrantContainer  # noqa: E402

from app.ingest import pipeline  # noqa: E402

# Match the local stack's pins (atlas-infra/local/compose.dev.yaml).
_ES_IMAGE = "elasticsearch:9.4.0"
_QDRANT_IMAGE = "qdrant/qdrant:v1.17.1"
_EMBED_DIM = 8  # MockProvider's embedding width

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def es_url() -> Iterator[str]:
    container = (
        ElasticSearchContainer(_ES_IMAGE)
        .with_env("discovery.type", "single-node")
        .with_env("xpack.security.enabled", "false")
        .with_env("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
    )
    with container as es:
        yield f"http://{es.get_container_host_ip()}:{es.get_exposed_port(9200)}"


@pytest.fixture(scope="module")
def qdrant_url() -> Iterator[str]:
    with QdrantContainer(_QDRANT_IMAGE) as qd:
        yield f"http://{qd.get_container_host_ip()}:{qd.get_exposed_port(6333)}"


def _corpus(tmp_path: Path) -> Path:
    docs = [
        {
            "id": "EUR-REACH-Annex-XVII-Entry-27",
            "source_id": "EUR-REACH-Annex-XVII-Entry-27",
            "text": "Restriction entry 27 limits nickel release from articles.",
        },
        {
            "id": "EUR-CLP-1272-2008-Art17",
            "source_id": "EUR-CLP-1272-2008-Art17",
            "text": "Article 17 sets out the content requirements for hazard labels.",
        },
    ]
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(d) for d in docs))
    return path


async def _fake_embed(
    client: httpx.AsyncClient, base_url: str, api_key: str, model: str, texts: list[str]
) -> list[list[float]]:
    """Deterministic 8-dim vectors — one per input, no gateway needed."""
    return [[0.1] * _EMBED_DIM for _ in texts]


async def _qdrant_points(url: str) -> int:
    client = AsyncQdrantClient(url=url)
    try:
        # Upsert isn't waited-on in the pipeline; poll briefly for consistency.
        for _ in range(10):
            collections = {c.name for c in (await client.get_collections()).collections}
            if "doc_chunks" in collections:
                count = await client.count(collection_name="doc_chunks")
                if count.count > 0:
                    return count.count
            await asyncio.sleep(0.5)
        return 0
    finally:
        await client.close()


async def test_run_ingestion_writes_to_real_backends(
    es_url: str, qdrant_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "_embed_batch", _fake_embed)

    total = await pipeline.run_ingestion(
        source_path=_corpus(tmp_path),
        gateway_url="http://unused",  # embeddings are stubbed
        gateway_api_key="x",
        embed_model="mock",
        es_url=es_url,
        qdrant_url=qdrant_url,
    )
    assert total == 2  # two short docs, one chunk each

    es = AsyncElasticsearch([es_url])
    try:
        await es.indices.refresh(index="doc_chunks")
        es_count = (await es.count(index="doc_chunks"))["count"]
    finally:
        await es.close()
    assert es_count == 2

    assert await _qdrant_points(qdrant_url) == 2
