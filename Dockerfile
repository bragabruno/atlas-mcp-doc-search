# syntax=docker/dockerfile:1
# atlas-mcp-doc-search runtime image — multi-stage, non-root, pinned base.
# Base pinned exactly (atlas-docs/02 §2), matching the CI image. Runtime deps are
# the exact-pinned [project.dependencies] from pyproject.toml (no dev deps).

FROM python:3.12.13-slim-bookworm AS build
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY . .
# Install the package + its pinned runtime deps into an isolated venv.
RUN python -m venv /venv \
 && /venv/bin/pip install --no-cache-dir .

FROM python:3.12.13-slim-bookworm AS runtime
# Non-root runtime user.
RUN groupadd --system app \
 && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /venv /venv
COPY --from=build /app /app
ENV PATH="/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTMCP_HOST=0.0.0.0
USER app
EXPOSE 8000
# FastMCP MCP server over Streamable HTTP (/mcp on :8000). FASTMCP_HOST is forced
# to 0.0.0.0 so the published port is reachable (FastMCP defaults to 127.0.0.1,
# which is unreachable across the container boundary). Backend endpoints + the
# gateway API key (ELASTICSEARCH_URL, QDRANT_URL, ATLAS_GATEWAY_URL,
# ATLAS_GATEWAY_API_KEY) are injected per-env at deploy time via the Key Vault
# CSI mount (atlas-docs/04); the image ships no secrets.
CMD ["python", "-m", "atlas_mcp_doc_search.server"]
