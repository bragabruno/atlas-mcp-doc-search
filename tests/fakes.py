"""In-process fake backends for offline testing.

No live Elasticsearch, Qdrant, or gateway required.
"""

from __future__ import annotations

from app.domain import ChunkRecord, RankedResult


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


# ---------------------------------------------------------------------------
# Write-side fakes for ingestion tests
# ---------------------------------------------------------------------------


class FakeVectorWriter:
    """Records upserted (ChunkRecord, vector) pairs in memory.

    Implements idempotency: upserting the same point_id overwrites the
    existing entry (mimicking Qdrant upsert semantics).
    """

    def __init__(self) -> None:
        # point_id -> (ChunkRecord, vector)
        self._store: dict[str, tuple[ChunkRecord, list[float]]] = {}

    async def upsert(self, records: list[ChunkRecord], vectors: list[list[float]]) -> None:
        for record, vector in zip(records, vectors, strict=True):
            self._store[record.id] = (record, vector)

    @property
    def stored(self) -> list[tuple[ChunkRecord, list[float]]]:
        """Return all stored (record, vector) pairs ordered by chunk_idx."""
        return sorted(self._store.values(), key=lambda rv: rv[0].chunk_idx)

    def records(self) -> list[ChunkRecord]:
        return [r for r, _ in self.stored]

    def vectors(self) -> list[list[float]]:
        return [v for _, v in self.stored]


class FakeESWriter:
    """Records indexed ChunkRecords in memory.

    Implements idempotency: indexing the same chunk id overwrites the
    existing entry (mimicking Elasticsearch index-with-id semantics).
    """

    def __init__(self) -> None:
        # doc _id -> ChunkRecord
        self._store: dict[str, ChunkRecord] = {}

    async def index(self, records: list[ChunkRecord]) -> None:
        for record in records:
            self._store[record.id] = record

    @property
    def stored(self) -> list[ChunkRecord]:
        """Return all stored records ordered by chunk_idx."""
        return sorted(self._store.values(), key=lambda r: r.chunk_idx)

    def __len__(self) -> int:
        return len(self._store)
