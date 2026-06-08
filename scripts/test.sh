#!/usr/bin/env bash
# test.sh — Gate 1 (dynamic correctness): offline unit tests via pytest.
# Zero API/LLM spend (fake ES/Qdrant/embeddings backends); no live services.
# Extra args are passed through to pytest (e.g. `scripts/test.sh -k rrf`).
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
# shellcheck source=scripts/lib/colors.sh
source scripts/lib/colors.sh
# shellcheck source=scripts/lib/common.sh
source scripts/lib/common.sh
trap 'on_err "$LINENO" "$?"' ERR

require_cmd pytest "pip install -e .[dev]"
run "pytest (offline)" pytest -q "$@"
log_ok "unit tests passed"
