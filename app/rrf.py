"""Reciprocal Rank Fusion (RRF) implementation.

Formula: score(d) = sum_r 1 / (k + rank_r(d))
where k=60 is the standard RRF constant and rank_r(d) is the 1-based rank of
document d in ranked list r.  Documents not present in a list are skipped for
that list (treated as infinite rank).

Reference: Cormack, Clarke & Buettcher (2009).
"""

from __future__ import annotations

from app.domain import Chunk, RankedResult

RRF_K: int = 60  # Standard RRF constant (Cormack et al. 2009)


def fuse(
    bm25_results: list[RankedResult],
    vector_results: list[RankedResult],
    top_k: int,
) -> list[Chunk]:
    """Merge two ranked lists with RRF and return the top *top_k* chunks.

    Both input lists carry ``RankedResult`` items whose ``rank`` is 1-based.
    The fused ``score`` is normalised to [0, 1] by dividing by the theoretical
    maximum (1 / (k + 1) * 2 when a document is ranked #1 in both lists).
    This keeps the output score within the contract range stated in atlas-docs/03.
    """
    scores: dict[str, float] = {}
    meta: dict[str, tuple[str, str]] = {}  # id -> (text, source_id)

    for result in bm25_results:
        scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (RRF_K + result.rank)
        meta[result.id] = (result.text, result.source_id)

    for result in vector_results:
        scores[result.id] = scores.get(result.id, 0.0) + 1.0 / (RRF_K + result.rank)
        meta[result.id] = (result.text, result.source_id)

    # Theoretical max: ranked #1 in both lists → 2 / (k + 1)
    max_score = 2.0 / (RRF_K + 1)

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    return [
        Chunk(
            id=chunk_id,
            text=meta[chunk_id][0],
            source_id=meta[chunk_id][1],
            score=min(raw / max_score, 1.0),
        )
        for chunk_id, raw in ranked
    ]
