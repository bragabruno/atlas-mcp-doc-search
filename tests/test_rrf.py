"""Tests for the RRF fusion implementation."""

from __future__ import annotations

from app.domain import RankedResult
from app.rrf import RRF_K, fuse


def make_result(chunk_id: str, rank: int) -> RankedResult:
    return RankedResult(
        id=chunk_id, text=f"text-{chunk_id}", source_id=f"src-{chunk_id}", rank=rank
    )


class TestRRFScoring:
    def test_single_list_score_is_correct(self) -> None:
        """A document ranked #1 in one list, absent in the other, scores 0.5.

        Raw = 1/(60+1), max_score = 2/(60+1) → normalised = 0.5.
        """
        result = make_result("a", rank=1)
        chunks = fuse([result], [], top_k=1)
        assert len(chunks) == 1
        assert chunks[0].id == "a"
        assert abs(chunks[0].score - 0.5) < 1e-9

    def test_top1_in_both_lists_gets_max_score(self) -> None:
        """A document at rank #1 in *both* lists scores 1.0 (max)."""
        r = make_result("x", rank=1)
        chunks = fuse([r], [r], top_k=1)
        assert chunks[0].id == "x"
        assert abs(chunks[0].score - 1.0) < 1e-9

    def test_higher_rank_gives_lower_score(self) -> None:
        """Documents ranked lower (higher rank number) get lower RRF scores."""
        r1 = make_result("first", rank=1)
        r2 = make_result("second", rank=2)
        chunks = fuse([r1, r2], [], top_k=2)
        assert chunks[0].id == "first"
        assert chunks[1].id == "second"
        assert chunks[0].score > chunks[1].score

    def test_score_clipped_to_one(self) -> None:
        """Scores never exceed 1.0."""
        r = make_result("a", rank=1)
        chunks = fuse([r], [r], top_k=1)
        assert chunks[0].score <= 1.0

    def test_score_non_negative(self) -> None:
        r = make_result("a", rank=50)
        chunks = fuse([r], [], top_k=1)
        assert chunks[0].score >= 0.0

    def test_top_k_limits_output(self) -> None:
        """fuse() never returns more than top_k chunks."""
        results = [make_result(str(i), rank=i + 1) for i in range(10)]
        chunks = fuse(results, [], top_k=4)
        assert len(chunks) == 4

    def test_empty_both_lists_returns_empty(self) -> None:
        assert fuse([], [], top_k=8) == []

    def test_only_vector_list(self) -> None:
        """Works when BM25 list is empty."""
        r = make_result("v1", rank=1)
        chunks = fuse([], [r], top_k=1)
        assert chunks[0].id == "v1"

    def test_fusion_boosts_appearing_in_both(self) -> None:
        """A document appearing in both lists outranks one only in one list."""
        shared = make_result("shared", rank=3)
        unique_bm25 = make_result("only-bm25", rank=1)  # ranked higher in BM25
        chunks = fuse([unique_bm25, shared], [shared], top_k=2)
        # 'shared' should beat 'only-bm25': RRF(3 in both) > RRF(1 in one)
        ids = [c.id for c in chunks]
        assert ids[0] == "shared"

    def test_rrf_k_constant_is_60(self) -> None:
        """Verify the standard RRF constant hasn't drifted."""
        assert RRF_K == 60

    def test_source_id_propagated(self) -> None:
        """source_id from the ranked result appears on the Chunk."""
        r = RankedResult(id="c1", text="hello", source_id="page-42", rank=1)
        chunks = fuse([r], [], top_k=1)
        assert chunks[0].source_id == "page-42"

    def test_deduplication_across_lists(self) -> None:
        """The same chunk_id in both lists is not returned twice."""
        r = make_result("dup", rank=1)
        chunks = fuse([r], [r], top_k=10)
        ids = [c.id for c in chunks]
        assert ids.count("dup") == 1
