#!/usr/bin/env python3
"""AGT-8 — Corpus ingestion CLI.

Usage:
    python scripts/ingest.py --source corpus.jsonl

Each line of the JSONL source must have the fields:
    id        : document identifier (used as source_id if source_id absent)
    text      : full document text
    source_id : (optional) regulatory source identifier; falls back to id

Environment variables (all required unless defaulted):
    ATLAS_GATEWAY_URL      e.g. http://localhost:8000
    ATLAS_GATEWAY_API_KEY  Bearer token
    ATLAS_EMBED_MODEL      embedding model alias (default: text-embedding-3-small)
    ATLAS_ES_URL           Elasticsearch URL (default: http://localhost:9200)
    ATLAS_QDRANT_URL       Qdrant URL (default: http://localhost:6333)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def _main(args: argparse.Namespace) -> None:
    from app.ingest.pipeline import run_ingestion

    total = await run_ingestion(
        source_path=Path(args.source),
        gateway_url=os.environ["ATLAS_GATEWAY_URL"],
        gateway_api_key=os.environ["ATLAS_GATEWAY_API_KEY"],
        embed_model=os.environ.get("ATLAS_EMBED_MODEL", "text-embedding-3-small"),
        es_url=os.environ.get("ATLAS_ES_URL", "http://localhost:9200"),
        qdrant_url=os.environ.get("ATLAS_QDRANT_URL", "http://localhost:6333"),
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(f"Done: {total} chunks ingested.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest regulatory corpus into Qdrant + ES")
    parser.add_argument("--source", required=True, help="Path to JSONL corpus file")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    args = parser.parse_args()
    try:
        asyncio.run(_main(args))
    except KeyError as exc:
        print(f"ERROR: missing env var {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
