"""AGT-8 — Text chunker for the regulatory corpus.

Splits a document into fixed-size overlapping chunks, preserving the source_id
on every chunk so downstream retrieval can trace back to the original document.
The chunk id is `<source_id>:<chunk_index>` — stable, deterministic, and unique
within a corpus.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """One chunk ready to be embedded and indexed."""

    id: str
    text: str
    source_id: str
    chunk_index: int


def chunk_document(
    *,
    text: str,
    source_id: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[TextChunk]:
    """Split *text* into overlapping word-boundary chunks.

    Args:
        text: The full document text.
        source_id: Identifier carried on every chunk (e.g. a regulation ID).
        chunk_size: Target chunk length in characters.
        overlap: Number of characters to repeat at the start of each chunk.

    Returns:
        List of `TextChunk` instances in document order.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    text = text.strip()
    if not text:
        return []

    step = chunk_size - overlap
    chunks: list[TextChunk] = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + chunk_size
        fragment = text[start:end].strip()
        if fragment:
            chunks.append(
                TextChunk(
                    id=f"{source_id}:{idx}",
                    text=fragment,
                    source_id=source_id,
                    chunk_index=idx,
                )
            )
            idx += 1
        start += step
    return chunks
