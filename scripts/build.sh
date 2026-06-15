#!/usr/bin/env bash
# build.sh — build verification: the package imports cleanly. The MCP server
# module (atlas_mcp_doc_search.server) is the real importable entrypoint; importing it constructs
# the FastMCP app and registers the doc_search tool without touching live
# backends (those are wired only under `python -m atlas_mcp_doc_search.server`). Publishes nothing.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
# shellcheck source=scripts/lib/colors.sh
source scripts/lib/colors.sh
# shellcheck source=scripts/lib/common.sh
source scripts/lib/common.sh
trap 'on_err "$LINENO" "$?"' ERR

require_cmd python "pip install -e .[dev]"
run "import smoke (atlas_mcp_doc_search.server)" python -c "import atlas_mcp_doc_search.server"
log_ok "build verification passed"
