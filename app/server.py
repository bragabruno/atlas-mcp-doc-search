"""Atlas MCP doc-search server.

Exposes the ``doc_search`` tool via FastMCP / Streamable HTTP.
Backend clients (ES, Qdrant, gateway embeddings) are injected via the
``_service`` module-level singleton so the server can be used in tests
with fake backends without touching live services.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from app.domain import Chunk
from app.protocols import BM25Client, EmbeddingsClient, VectorClient
from app.search_service import SearchService

# Bind host/port from the env. FastMCP's own FASTMCP_HOST env var is not honored
# in this SDK version (its default kwarg overrides it), so read it explicitly and
# pass as a constructor kwarg (highest precedence). Default stays loopback for
# bare local runs; the container image sets FASTMCP_HOST=0.0.0.0 so the published
# port is reachable across the container boundary.
mcp: FastMCP = FastMCP(
    "atlas-doc-search",
    instructions="Hybrid BM25 + vector search over the Atlas document corpus.",
    host=os.environ.get("FASTMCP_HOST", "127.0.0.1"),
    port=int(os.environ.get("FASTMCP_PORT", "8000")),
)

# Module-level service — replaced by configure() before the server starts.
_service: SearchService | None = None


def configure(
    embeddings: EmbeddingsClient,
    bm25: BM25Client,
    vector: VectorClient,
) -> None:
    """Wire the backend clients into the module-level SearchService.

    Call this once at startup before running the server (or in test fixtures).
    """
    global _service
    _service = SearchService(embeddings=embeddings, bm25=bm25, vector=vector)


def _get_service() -> SearchService:
    if _service is None:
        raise RuntimeError("Server not configured — call configure() before serving.")
    return _service


@mcp.tool()
async def doc_search(query: str, k: int = 8) -> dict[str, list[dict[str, object]]]:
    """Hybrid document search: BM25 + vector, fused via Reciprocal Rank Fusion.

    Args:
        query: Natural-language search query (1–2000 characters).
        k: Number of top-ranked chunks to return (1–50, default 8).

    Returns:
        A dict with key ``chunks`` — a list of up to k objects, each with
        ``id``, ``text``, ``source_id``, and ``score`` (float in [0, 1]).
    """
    if not query or len(query) > 2000:
        raise ValueError("query must be between 1 and 2000 characters")
    k = max(1, min(50, k))

    service = _get_service()
    chunks: list[Chunk] = await service.search(query, k)
    return {
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


if __name__ == "__main__":
    import os

    import httpx
    from elasticsearch import AsyncElasticsearch
    from qdrant_client import AsyncQdrantClient

    from app.auth import serve
    from app.backends.es_bm25 import ElasticsearchBM25Client
    from app.backends.gateway_embeddings import GatewayEmbeddingsClient
    from app.backends.qdrant_vector import QdrantVectorClient

    es_url = os.environ["ELASTICSEARCH_URL"]
    qdrant_url = os.environ["QDRANT_URL"]
    gateway_url = os.environ["ATLAS_GATEWAY_URL"]
    gateway_key = os.environ["ATLAS_GATEWAY_API_KEY"]

    configure(
        embeddings=GatewayEmbeddingsClient(
            client=httpx.AsyncClient(),
            base_url=gateway_url,
            api_key=gateway_key,
        ),
        bm25=ElasticsearchBM25Client(AsyncElasticsearch([es_url])),
        vector=QdrantVectorClient(AsyncQdrantClient(url=qdrant_url)),
    )

    # BRA-883 — optional bearer auth (default-off via ATLAS_MCP_AUTH_TOKEN).
    serve(mcp)
