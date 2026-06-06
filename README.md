# atlas-mcp-doc-search

MCP server that exposes hybrid document search over the Atlas ingested corpus. Built with the official Python `mcp` SDK, Python 3.12 asyncio, and deployed as a standalone K8s service on AKS.

## Tool Contract

### `doc_search`

```
doc_search(query: str, k: int = 8) -> {chunks: [{id, text, source_id, score}]}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | required | Natural-language search query |
| `k` | `int` | `8` | Number of top-ranked chunks to return |

**Returns** a list of up to `k` chunks, each with:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique chunk identifier |
| `text` | `str` | Raw chunk text |
| `source_id` | `str` | Identifier of the source document |
| `score` | `float` | Reciprocal Rank Fusion (RRF) fused score |

## Hybrid Retrieval Approach

The server implements **HYBRID retrieval** — combining sparse (BM25) and dense (vector) signals and fusing them with Reciprocal Rank Fusion (RRF):

1. **Query embedding** — the raw query string is sent to the Atlas gateway's `/v1/embeddings` endpoint to produce a dense vector.
2. **Parallel retrieval**
   - **Elasticsearch BM25** keyword search over the `doc_chunks` index.
   - **Qdrant** vector similarity search over collection `doc_chunks` (payload fields: `source_id`, `doc_id`, `chunk_idx`, `text`).
3. **Fusion** — both ranked lists are merged with RRF to produce a single ranked list.
4. **Return** — top `k` results are returned with their fused scores.

## Dependencies

| Dependency | Role |
|------------|------|
| `mcp` (official Python SDK) | MCP server framework |
| Elasticsearch | BM25 keyword retrieval over `doc_chunks` |
| Qdrant | Dense vector retrieval over collection `doc_chunks` |
| Atlas gateway `/v1/embeddings` | Query embedding generation |

## Diagrams

- [Component (C4-L3)](docs/diagrams/component-c4.md)
- [Sequence — hybrid doc search](docs/diagrams/seq-doc-search-hybrid.md)
- [Class diagram](docs/diagrams/class.puml)

## Related

- [atlas-docs](../atlas-docs) — document ingestion pipeline that populates the corpus
- [atlas-mcp-citations](../atlas-mcp-citations) — citation verification MCP server
