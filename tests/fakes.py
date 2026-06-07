"""In-process fake backends for offline testing.

No live Elasticsearch, Qdrant, or gateway required.
"""

from __future__ import annotations

from app.domain import RankedResult


class FakeEmbeddingsClient:
    """Returns a deterministic fixed-length vector without calling the gateway."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim

    async def embed(self, text: str) -> list[float]:
        # Simple reproducible hash-based embedding — just needs to be non-zero.
        seed = sum(ord(c) for c in text)
        return [(seed + i) % 100 / 100.0 for i in range(self._dim)]


class FakeBM25Client:
    """Returns a configurable ordered list of RankedResults."""

    def __init__(self, results: list[RankedResult]) -> None:
        self._results = results

    async def search(self, query: str, k: int) -> list[RankedResult]:
        return self._results[:k]


class FakeVectorClient:
    """Returns a configurable ordered list of RankedResults."""

    def __init__(self, results: list[RankedResult]) -> None:
        self._results = results

    async def search(self, vector: list[float], k: int) -> list[RankedResult]:
        return self._results[:k]
