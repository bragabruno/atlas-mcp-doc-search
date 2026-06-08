"""Gateway embeddings backend.

Calls the Atlas gateway ``POST /v1/embeddings`` endpoint (OpenAI-compatible)
to produce a dense query vector.
"""

from __future__ import annotations

import httpx

_EMBED_MODEL = "embed"


class GatewayEmbeddingsClient:
    """Implements EmbeddingsClient via the Atlas gateway /v1/embeddings API."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for *text*."""
        response = await self._client.post(
            f"{self._base_url}/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": text, "model": _EMBED_MODEL},
        )
        response.raise_for_status()
        body = response.json()
        return list(body["data"][0]["embedding"])
