#!/usr/bin/env bash
# local.sh — run the MCP doc-search server locally over FastMCP Streamable HTTP.
# Wires the live backends (ES, Qdrant, gateway embeddings) from env, so the
# service endpoints + gateway API key must be exported first:
#   ELASTICSEARCH_URL, QDRANT_URL, ATLAS_GATEWAY_URL, ATLAS_GATEWAY_API_KEY
# The server listens on FastMCP's default Streamable HTTP port (8000).
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
# shellcheck source=scripts/lib/colors.sh
source scripts/lib/colors.sh
# shellcheck source=scripts/lib/common.sh
source scripts/lib/common.sh
trap 'on_err "$LINENO" "$?"' ERR

require_cmd python "pip install -e .[dev]"
log_info "atlas-mcp-doc-search → FastMCP Streamable HTTP (/mcp) on :8000 (Ctrl-C to stop)"
exec python -m atlas_mcp_doc_search.server
