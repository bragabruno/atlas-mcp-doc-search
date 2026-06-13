"""AGT-8 — corpus ingestion pipeline tests.

The chunker tests are fully offline. The pipeline smoke test mocks out all
external clients (httpx, Elasticsearch, Qdrant) so no services are needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingest.chunker import chunk_document

# ---------------------------------------------------------------------------
# chunker
# ---------------------------------------------------------------------------

def test_chunk_empty_text_returns_no_chunks() -> None:
    assert chunk_document(text="", source_id="doc-1") == []


def test_chunk_whitespace_only_returns_no_chunks() -> None:
    assert chunk_document(text="   \n\t  ", source_id="doc-1") == []


def test_chunk_short_text_single_chunk() -> None:
    chunks = chunk_document(text="hello world", source_id="doc-1", chunk_size=512, overlap=0)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].source_id == "doc-1"
    assert chunks[0].id == "doc-1:0"


def test_chunk_preserves_source_id() -> None:
    long_text = "a" * 1000
    chunks = chunk_document(text=long_text, source_id="reg-42", chunk_size=100, overlap=10)
    assert all(c.source_id == "reg-42" for c in chunks)


def test_chunk_ids_are_sequential() -> None:
    long_text = "word " * 200
    chunks = chunk_document(text=long_text, source_id="doc-x", chunk_size=50, overlap=10)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.id == f"doc-x:{c.chunk_index}" for c in chunks)


def test_chunk_overlap_means_consecutive_chunks_share_text() -> None:
    text = "a" * 100
    chunks = chunk_document(text=text, source_id="s", chunk_size=20, overlap=5)
    if len(chunks) >= 2:
        # The tail of chunk[0] should appear at the start of chunk[1].
        tail = chunks[0].text[-5:]
        head = chunks[1].text[:5]
        assert tail == head


def test_chunk_invalid_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_document(text="hello", source_id="s", chunk_size=0)


def test_chunk_invalid_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_document(text="hello", source_id="s", chunk_size=10, overlap=10)


# ---------------------------------------------------------------------------
# pipeline (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["find_spec"]).find_spec("elasticsearch") is None,
    reason="elasticsearch not installed",
)
async def test_pipeline_ingests_jsonl_and_returns_chunk_count(tmp_path: Path) -> None:
    source = tmp_path / "corpus.jsonl"
    docs = [
        {"id": "doc-1", "source_id": "reg-1", "text": "This is the first regulation text."},
        {"id": "doc-2", "source_id": "reg-2", "text": "Second regulation with different content."},
    ]
    source.write_text("\n".join(json.dumps(d) for d in docs))

    fake_vector = [0.1] * 8

    # Mock httpx response for /v1/embeddings — one embedding PER input text,
    # mirroring the real gateway contract (the pipeline zips strict=True; the
    # old fixed single-embedding mock made this test fail on multi-doc input).
    def _embed_response(url: str, *, json: dict, **_: object) -> MagicMock:  # noqa: A002
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        inputs = json["input"]
        resp.json.return_value = {
            "data": [{"embedding": fake_vector, "index": i} for i in range(len(inputs))]
        }
        return resp

    # asynccontextmanager-compatible mock for httpx.AsyncClient
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=_embed_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    mock_es = AsyncMock()
    mock_es.__aenter__ = AsyncMock(return_value=mock_es)
    mock_es.__aexit__ = AsyncMock(return_value=False)

    mock_qdrant = AsyncMock()
    mock_qdrant.__aenter__ = AsyncMock(return_value=mock_qdrant)
    mock_qdrant.__aexit__ = AsyncMock(return_value=False)
    # _ensure_collection lists existing collections before the first upsert.
    mock_qdrant.get_collections = AsyncMock(
        return_value=SimpleNamespace(collections=[])
    )

    with (
        patch("app.ingest.pipeline.httpx.AsyncClient", return_value=mock_http),
        patch("app.ingest.pipeline.AsyncElasticsearch", return_value=mock_es),
        patch("app.ingest.pipeline.AsyncQdrantClient", return_value=mock_qdrant),
    ):
        from app.ingest.pipeline import run_ingestion

        total = await run_ingestion(
            source_path=source,
            gateway_url="http://gateway:8000",
            gateway_api_key="dev-key",
            embed_model="text-embedding-3-small",
            es_url="http://es:9200",
            qdrant_url="http://qdrant:6333",
            chunk_size=512,
            overlap=64,
        )

    assert total == 2  # two docs, each fits in one chunk
    assert mock_qdrant.upsert.called
    assert mock_es.bulk.called
