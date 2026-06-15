"""Optional, config-gated bearer auth for the MCP /mcp endpoint (BRA-883).

The MCP server is exposed over streamable-http with no auth by default so the
local stack, the Postman collection, and the agent-runtime client keep working
unchanged. This module adds an *opt-in* shared-secret gate:

- ``ATLAS_MCP_AUTH_TOKEN`` unset/empty  → no auth enforced (current behavior).
- ``ATLAS_MCP_AUTH_TOKEN`` set           → every HTTP request must carry
  ``Authorization: Bearer <token>``; otherwise a 401 is returned before the
  MCP handler runs.

Implemented as a thin ASGI middleware wrapping ``FastMCP.streamable_http_app()``
rather than FastMCP's built-in OAuth ``token_verifier`` (which is scope/OAuth
shaped and would alter the handshake unconditionally). When the token is unset
the middleware is a pure passthrough, so the streamable-http handshake is
byte-for-byte identical to the un-wrapped app.
"""

from __future__ import annotations

import hmac
import os
from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_AUTH_TOKEN_ENV = "ATLAS_MCP_AUTH_TOKEN"


def configured_token() -> str | None:
    """Return the configured bearer token, or ``None`` when auth is disabled."""
    token = os.environ.get(_AUTH_TOKEN_ENV)
    return token or None


def authorized(headers: dict[bytes, bytes], token: str | None) -> bool:
    """Return whether a request's raw ASGI headers satisfy the auth policy.

    Pure function over the (already-lowercased) ASGI header mapping so it can be
    unit-tested without a running server.

    Args:
        headers: ASGI ``scope["headers"]`` as a ``{name: value}`` byte mapping.
        token: The configured bearer token, or ``None`` when auth is disabled.

    Returns:
        ``True`` if auth is disabled (``token`` is ``None``) or the request
        carries a ``Bearer`` token whose value matches the configured token.
    """
    if token is None:
        return True

    provided = headers.get(b"authorization", b"").decode("latin-1")
    if not provided:
        return False

    # Split on the first run of whitespace into "<scheme> <credentials>"
    parts = provided.split(None, 1)
    if len(parts) != 2:
        return False

    scheme, provided_token = parts
    if scheme.lower() != "bearer":
        return False

    # Constant-time compare on the token value to avoid leaking it via timing.
    return hmac.compare_digest(provided_token, token)


class BearerAuthMiddleware:
    """ASGI middleware enforcing the optional bearer token on HTTP requests.

    When no token is configured the middleware is a transparent passthrough; the
    wrapped app — and therefore the streamable-http handshake — behaves exactly
    as if the middleware were absent.
    """

    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.token is None or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        if not authorized(headers, self.token):
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def serve(mcp: FastMCP) -> None:
    """Run the MCP server over streamable-http, applying optional bearer auth.

    When ``ATLAS_MCP_AUTH_TOKEN`` is unset this defers to the stock
    ``mcp.run(transport="streamable-http")`` path so behavior is unchanged. When
    it is set, the streamable-http ASGI app is wrapped with
    ``BearerAuthMiddleware`` and served via uvicorn using the same host, port,
    and log level FastMCP would have used.
    """
    token = configured_token()
    if token is None:
        mcp.run(transport="streamable-http")
        return

    import uvicorn

    app = BearerAuthMiddleware(mcp.streamable_http_app(), token)
    uvicorn.run(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
