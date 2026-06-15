"""Text chunker — splits a document into overlapping character windows.

No external dependencies; uses only the Python standard library.

Design
------
* Window-based char split with configurable ``chunk_size`` and ``overlap``.
  Overlap ensures that sentences or phrases that straddle a boundary are
  represented in at least one chunk, improving recall.
* Chunk IDs are stable deterministic UUIDs (uuid5) derived from
  ``source_id`` and ``chunk_idx`` so that re-ingesting the same document
  always produces the *same* IDs — making upserts idempotent.
"""

from __future__ import annotations

import uuid

from atlas_mcp_doc_search.domain import ChunkRecord

# Namespace UUID for chunk ID generation (arbitrary, fixed for the project).
_CHUNK_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _chunk_id(source_id: str, chunk_idx: int) -> str:
    """Return a stable UUID string for a given (source_id, chunk_idx) pair."""
    return str(uuid.uuid5(_CHUNK_NS, f"{source_id}:{chunk_idx}"))


def chunk_text(
    text: str,
    *,
    source_id: str,
    doc_id: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[ChunkRecord]:
    """Split *text* into overlapping character windows.

    Args:
        text:       Raw document text to split.
        source_id:  Opaque source document identifier (carried through to payload).
        doc_id:     Internal Atlas document record ID.
        chunk_size: Maximum number of characters per chunk (default 512).
        overlap:    Number of characters shared between consecutive chunks (default 64).

    Returns:
        Ordered list of ``ChunkRecord`` objects with stable IDs and zero-based
        ``chunk_idx`` values.

    Raises:
        ValueError: If ``chunk_size`` < 1, ``overlap`` < 0, or ``overlap`` >= ``chunk_size``.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be < chunk_size ({chunk_size})")

    stripped = text.strip()
    if not stripped:
        return []

    step = chunk_size - overlap
    records: list[ChunkRecord] = []
    idx = 0
    start = 0

    while start < len(stripped):
        end = start + chunk_size
        chunk_text_slice = stripped[start:end].strip()
        if chunk_text_slice:
            records.append(
                ChunkRecord(
                    id=_chunk_id(source_id, idx),
                    source_id=source_id,
                    doc_id=doc_id,
                    chunk_idx=idx,
                    text=chunk_text_slice,
                )
            )
            idx += 1
        start += step

    return records
