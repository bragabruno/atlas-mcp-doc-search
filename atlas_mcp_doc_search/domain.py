"""Domain types — no framework imports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """A single retrieved document chunk."""

    id: str
    text: str
    source_id: str
    score: float


@dataclass(frozen=True)
class RankedResult:
    """A chunk at a specific rank position from a single retriever."""

    id: str
    text: str
    source_id: str
    rank: int  # 1-based


@dataclass(frozen=True)
class ChunkRecord:
    """A chunk ready for ingestion into Qdrant + Elasticsearch.

    Payload schema mirrors atlas-docs/03 § 3.1:
      source_id  — opaque source document identifier
      doc_id     — internal Atlas document record ID
      chunk_idx  — zero-based chunk position within the document
      text       — raw chunk text
      id         — stable deterministic ID (uuid5 of source_id + chunk_idx)
    """

    id: str
    source_id: str
    doc_id: str
    chunk_idx: int
    text: str
