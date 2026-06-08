"""Tests for SearchService — hybrid search orchestration with fake backends."""

from __future__ import annotations

import pytest

from atlas_mcp_doc_search.domain import RankedResult
from atlas_mcp_doc_search.search_service import SearchService
from tests.fakes import FakeBM25Client, FakeEmbeddingsClient, FakeVectorClient


def make_result(chunk_id: str, rank: int, source_id: str = "src-1") -> RankedResult:
    return RankedResult(id=chunk_id, text=f"text-{chunk_id}", source_id=source_id, rank=rank)


@pytest.fixture()
def service_both_lists() -> SearchService:
    """Service with 3 BM25 + 3 vector results sharing 1 chunk."""
    bm25_results = [
        make_result("a", rank=1, source_id="doc-a"),
        make_result("b", rank=2, source_id="doc-b"),
        make_result("shared", rank=3, source_id="doc-shared"),
    ]
    vector_results = [
        make_result("shared", rank=1, source_id="doc-shared"),
        make_result("c", rank=2, source_id="doc-c"),
        make_result("d", rank=3, source_id="doc-d"),
    ]
    return SearchService(
        embeddings=FakeEmbeddingsClient(),
        bm25=FakeBM25Client(bm25_results),
        vector=FakeVectorClient(vector_results),
    )


class TestSearchServiceReturnShape:
    async def test_returns_chunks_with_required_fields(
        self, service_both_lists: SearchService
    ) -> None:
        """Every returned Chunk has id, text, source_id, score."""
        chunks = await service_both_lists.search("regulatory compliance", k=5)
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk.id, str) and chunk.id
            assert isinstance(chunk.text, str) and chunk.text
            assert isinstance(chunk.source_id, str) and chunk.source_id
            assert isinstance(chunk.score, float)
            assert 0.0 <= chunk.score <= 1.0

    async def test_respects_k_limit(self, service_both_lists: SearchService) -> None:
        chunks = await service_both_lists.search("query", k=3)
        assert len(chunks) <= 3

    async def test_k_1_returns_single_chunk(self, service_both_lists: SearchService) -> None:
        chunks = await service_both_lists.search("query", k=1)
        assert len(chunks) == 1

    async def test_chunks_are_ordered_by_score_descending(
        self, service_both_lists: SearchService
    ) -> None:
        chunks = await service_both_lists.search("query", k=8)
        scores = [c.score for c in chunks]
        assert scores == sorted(scores, reverse=True)

    async def test_source_ids_are_preserved(self, service_both_lists: SearchService) -> None:
        """source_ids from both backends pass through correctly."""
        chunks = await service_both_lists.search("query", k=8)
        source_ids = {c.source_id for c in chunks}
        assert "doc-a" in source_ids or "doc-b" in source_ids or "doc-shared" in source_ids


class TestSearchServiceFusion:
    async def test_shared_chunk_appears_once(self, service_both_lists: SearchService) -> None:
        """A chunk present in both BM25 and vector results appears exactly once."""
        chunks = await service_both_lists.search("query", k=8)
        ids = [c.id for c in chunks]
        assert ids.count("shared") == 1

    async def test_shared_chunk_ranked_highly(self, service_both_lists: SearchService) -> None:
        """'shared' appears in both lists so must be in top-2 after RRF."""
        chunks = await service_both_lists.search("query", k=8)
        top_ids = [c.id for c in chunks[:2]]
        assert "shared" in top_ids

    async def test_empty_bm25_still_returns_vector_results(self) -> None:
        service = SearchService(
            embeddings=FakeEmbeddingsClient(),
            bm25=FakeBM25Client([]),
            vector=FakeVectorClient([make_result("v1", rank=1)]),
        )
        chunks = await service.search("q", k=8)
        assert any(c.id == "v1" for c in chunks)

    async def test_empty_vector_still_returns_bm25_results(self) -> None:
        service = SearchService(
            embeddings=FakeEmbeddingsClient(),
            bm25=FakeBM25Client([make_result("b1", rank=1)]),
            vector=FakeVectorClient([]),
        )
        chunks = await service.search("q", k=8)
        assert any(c.id == "b1" for c in chunks)

    async def test_both_empty_returns_empty(self) -> None:
        service = SearchService(
            embeddings=FakeEmbeddingsClient(),
            bm25=FakeBM25Client([]),
            vector=FakeVectorClient([]),
        )
        chunks = await service.search("q", k=8)
        assert chunks == []


class TestSearchServiceContract:
    """Validate the response shape matches atlas-docs/03 MCP tool output schema."""

    async def test_output_matches_atlas_docs_schema(
        self, service_both_lists: SearchService
    ) -> None:
        """Response must be serialisable to {chunks: [{id, text, source_id, score}]}."""
        chunks = await service_both_lists.search("test query", k=4)
        payload = {
            "chunks": [
                {
                    "id": c.id,
                    "text": c.text,
                    "source_id": c.source_id,
                    "score": c.score,
                }
                for c in chunks
            ]
        }
        assert "chunks" in payload
        for item in payload["chunks"]:
            assert set(item.keys()) == {"id", "text", "source_id", "score"}
            assert isinstance(item["id"], str)
            assert isinstance(item["text"], str)
            assert isinstance(item["source_id"], str)
            assert isinstance(item["score"], float)
            # score in [0, 1] as per atlas-docs/03 § 6.1
            assert 0.0 <= item["score"] <= 1.0
