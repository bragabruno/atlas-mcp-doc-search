"""Tests for the AGT-8 ingestion pipeline.

All tests are fully offline — no live Elasticsearch, Qdrant, or gateway.
Fakes from tests/fakes.py are injected for all backend clients.
"""

from __future__ import annotations

import pytest

from app.domain import ChunkRecord
from app.ingestion.chunker import chunk_text
from app.ingestion.pipeline import IngestionPipeline
from tests.fakes import FakeEmbeddingsClient, FakeESWriter, FakeVectorWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SMALL_DOC = "Article 1 — General Provisions. " * 5  # ~165 chars
MEDIUM_DOC = ("Regulatory text. " * 40).strip()  # ~680 chars → 2 chunks at 512/64


def make_pipeline(
    chunk_size: int = 512,
    overlap: int = 64,
) -> tuple[IngestionPipeline, FakeVectorWriter, FakeESWriter]:
    vec = FakeVectorWriter()
    es = FakeESWriter()
    pipeline = IngestionPipeline(
        embeddings=FakeEmbeddingsClient(dim=4),
        vector_writer=vec,
        es_writer=es,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    return pipeline, vec, es


# ---------------------------------------------------------------------------
# Chunker unit tests
# ---------------------------------------------------------------------------


class TestChunker:
    def test_empty_text_returns_no_chunks(self) -> None:
        assert chunk_text("", source_id="s1", doc_id="d1") == []

    def test_whitespace_only_returns_no_chunks(self) -> None:
        assert chunk_text("   \n\t  ", source_id="s1", doc_id="d1") == []

    def test_short_text_produces_single_chunk(self) -> None:
        records = chunk_text("Hello world", source_id="s1", doc_id="d1", chunk_size=512, overlap=0)
        assert len(records) == 1
        assert records[0].text == "Hello world"

    def test_chunk_idx_is_zero_based(self) -> None:
        records = chunk_text(MEDIUM_DOC, source_id="s1", doc_id="d1", chunk_size=512, overlap=64)
        for expected_idx, rec in enumerate(records):
            assert rec.chunk_idx == expected_idx

    def test_chunk_idx_ordering_is_sequential(self) -> None:
        records = chunk_text(MEDIUM_DOC, source_id="s1", doc_id="d1", chunk_size=200, overlap=20)
        indices = [r.chunk_idx for r in records]
        assert indices == list(range(len(records)))

    def test_source_id_preserved_on_every_chunk(self) -> None:
        records = chunk_text(
            MEDIUM_DOC, source_id="src-42", doc_id="d1", chunk_size=200, overlap=20
        )
        assert all(r.source_id == "src-42" for r in records)

    def test_doc_id_preserved_on_every_chunk(self) -> None:
        records = chunk_text(
            MEDIUM_DOC, source_id="s1", doc_id="doc-99", chunk_size=200, overlap=20
        )
        assert all(r.doc_id == "doc-99" for r in records)

    def test_chunk_length_bounded_by_chunk_size(self) -> None:
        records = chunk_text(MEDIUM_DOC, source_id="s1", doc_id="d1", chunk_size=100, overlap=10)
        for rec in records:
            assert len(rec.text) <= 100

    def test_chunk_ids_are_stable_across_calls(self) -> None:
        """Re-chunking the same doc produces identical IDs."""
        r1 = chunk_text(SMALL_DOC, source_id="s1", doc_id="d1")
        r2 = chunk_text(SMALL_DOC, source_id="s1", doc_id="d1")
        assert [r.id for r in r1] == [r.id for r in r2]

    def test_chunk_ids_differ_for_different_source_ids(self) -> None:
        r1 = chunk_text("same text", source_id="src-A", doc_id="d1")
        r2 = chunk_text("same text", source_id="src-B", doc_id="d1")
        assert r1[0].id != r2[0].id

    def test_chunk_ids_are_unique_within_document(self) -> None:
        records = chunk_text(MEDIUM_DOC, source_id="s1", doc_id="d1", chunk_size=200, overlap=20)
        ids = [r.id for r in records]
        assert len(ids) == len(set(ids))

    def test_multiple_chunks_produced_for_long_text(self) -> None:
        records = chunk_text(MEDIUM_DOC, source_id="s1", doc_id="d1", chunk_size=200, overlap=20)
        assert len(records) >= 2

    def test_overlap_zero_no_repeated_content(self) -> None:
        """With overlap=0, consecutive chunks should not share content."""
        text = "A" * 300
        records = chunk_text(text, source_id="s1", doc_id="d1", chunk_size=100, overlap=0)
        assert len(records) == 3
        combined = "".join(r.text for r in records)
        assert combined == text.strip()

    def test_invalid_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("x", source_id="s1", doc_id="d1", chunk_size=0)

    def test_invalid_overlap_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("x", source_id="s1", doc_id="d1", chunk_size=100, overlap=-1)

    def test_overlap_gte_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("x", source_id="s1", doc_id="d1", chunk_size=50, overlap=50)


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------


class TestIngestionPipeline:
    async def test_empty_text_returns_empty_list(self) -> None:
        pipeline, vec, es = make_pipeline()
        result = await pipeline.ingest("", source_id="s1", doc_id="d1")
        assert result == []
        assert vec.records() == []
        assert es.stored == []

    async def test_ingest_writes_to_both_stores(self) -> None:
        pipeline, vec, es = make_pipeline(chunk_size=200, overlap=20)
        records = await pipeline.ingest(MEDIUM_DOC, source_id="src-1", doc_id="doc-1")
        assert len(records) >= 1
        assert len(vec.records()) == len(records)
        assert len(es.stored) == len(records)

    async def test_source_id_preserved_in_qdrant(self) -> None:
        pipeline, vec, _es = make_pipeline(chunk_size=200, overlap=20)
        await pipeline.ingest(MEDIUM_DOC, source_id="src-X", doc_id="doc-1")
        assert all(r.source_id == "src-X" for r in vec.records())

    async def test_source_id_preserved_in_es(self) -> None:
        pipeline, _vec, es = make_pipeline(chunk_size=200, overlap=20)
        await pipeline.ingest(MEDIUM_DOC, source_id="src-Y", doc_id="doc-1")
        assert all(r.source_id == "src-Y" for r in es.stored)

    async def test_chunk_idx_ordering_correct_in_qdrant(self) -> None:
        """Qdrant records are in ascending chunk_idx order."""
        pipeline, vec, _es = make_pipeline(chunk_size=150, overlap=15)
        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        indices = [r.chunk_idx for r in vec.records()]
        assert indices == list(range(len(indices)))

    async def test_chunk_idx_ordering_correct_in_es(self) -> None:
        """ES records are in ascending chunk_idx order."""
        pipeline, _vec, es = make_pipeline(chunk_size=150, overlap=15)
        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        indices = [r.chunk_idx for r in es.stored]
        assert indices == list(range(len(indices)))

    async def test_vector_count_matches_record_count(self) -> None:
        """One embedding vector per chunk record."""
        pipeline, vec, _es = make_pipeline(chunk_size=200, overlap=20)
        records = await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        assert len(vec.vectors()) == len(records)

    async def test_idempotent_reingest_does_not_duplicate_in_qdrant(self) -> None:
        """Re-ingesting the same document updates, not duplicates, Qdrant entries."""
        pipeline, vec, _es = make_pipeline(chunk_size=200, overlap=20)
        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        first_count = len(vec.records())

        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        assert len(vec.records()) == first_count

    async def test_idempotent_reingest_does_not_duplicate_in_es(self) -> None:
        """Re-ingesting the same document updates, not duplicates, ES entries."""
        pipeline, _vec, es = make_pipeline(chunk_size=200, overlap=20)
        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        first_count = len(es)

        await pipeline.ingest(MEDIUM_DOC, source_id="s1", doc_id="d1")
        assert len(es) == first_count

    async def test_two_docs_with_same_text_different_source_ids_stored_separately(self) -> None:
        """Different source_ids produce different chunk IDs — no collision."""
        pipeline, vec, _es = make_pipeline(chunk_size=512, overlap=0)
        await pipeline.ingest(SMALL_DOC, source_id="src-A", doc_id="doc-A")
        await pipeline.ingest(SMALL_DOC, source_id="src-B", doc_id="doc-B")
        ids = [r.id for r in vec.records()]
        assert len(ids) == len(set(ids))

    async def test_fixture_corpus_chunked_embedded_upserted(self) -> None:
        """Small fixture corpus: 3 docs → chunks in both stores with source_ids."""
        corpus = [
            ("Article 1 on data protection in the EU. " * 10, "src-eu-1", "doc-eu-1"),
            ("US financial regulations for hedge funds. " * 10, "src-us-1", "doc-us-1"),
            ("APAC environmental compliance rules. " * 10, "src-ap-1", "doc-ap-1"),
        ]
        pipeline, vec, es = make_pipeline(chunk_size=200, overlap=20)
        all_records: list[ChunkRecord] = []
        for text, source_id, doc_id in corpus:
            records = await pipeline.ingest(text, source_id=source_id, doc_id=doc_id)
            all_records.extend(records)

        # All chunks landed in both stores.
        assert len(vec.records()) == len(all_records)
        assert len(es.stored) == len(all_records)

        # Every source_id from the corpus is represented.
        qdrant_sources = {r.source_id for r in vec.records()}
        es_sources = {r.source_id for r in es.stored}
        for _, source_id, _ in corpus:
            assert source_id in qdrant_sources
            assert source_id in es_sources

        # No duplicate chunk IDs across the corpus.
        all_ids = [r.id for r in vec.records()]
        assert len(all_ids) == len(set(all_ids))
