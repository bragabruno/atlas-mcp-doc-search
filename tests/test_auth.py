"""Unit tests for the optional config-gated bearer auth (BRA-883).

Fully offline: exercises the pure ``_authorized`` helper and the
``BearerAuthMiddleware`` ASGI wrapper directly against a stub app — no running
server, no network.
"""

# Tests import the _AUTH_TOKEN_ENV internal so the env-var name cannot drift.
# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import pytest

from atlas_mcp_doc_search.auth import _AUTH_TOKEN_ENV, BearerAuthMiddleware, authorized

TOKEN = "s3cret-token"


def _hdrs(*pairs: tuple[bytes, bytes]) -> dict[bytes, bytes]:
    return dict(pairs)


# --- authorized -----------------------------------------------------------------


def test_authorized_disabled_allows_anything() -> None:
    # token=None => auth disabled => every request authorized, even with no header.
    assert authorized(_hdrs(), token=None) is True
    assert authorized(_hdrs((b"authorization", b"garbage")), token=None) is True


def test_authorized_missing_header_rejected() -> None:
    assert authorized(_hdrs(), token=TOKEN) is False


def test_authorized_wrong_token_rejected() -> None:
    assert authorized(_hdrs((b"authorization", b"Bearer nope")), token=TOKEN) is False


def test_authorized_wrong_scheme_rejected() -> None:
    assert authorized(_hdrs((b"authorization", f"Basic {TOKEN}".encode())), token=TOKEN) is False


def test_authorized_correct_bearer_accepted() -> None:
    assert authorized(_hdrs((b"authorization", f"Bearer {TOKEN}".encode())), token=TOKEN) is True


# --- BearerAuthMiddleware (ASGI) ------------------------------------------------


class _StubApp:
    """Minimal ASGI app that records whether it was reached and 200s."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _run(app: Any, scope: MutableMapping[str, Any]) -> int:
    """Drive an ASGI app once and return the response status code."""
    status = -1

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: MutableMapping[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]

    await app(scope, receive, send)
    return status


def _http_scope(*headers: tuple[bytes, bytes]) -> dict[str, Any]:
    return {"type": "http", "headers": list(headers)}


async def test_middleware_passthrough_when_token_unset() -> None:
    stub = _StubApp()
    mw = BearerAuthMiddleware(stub, token=None)

    # No headers: middleware should be a no-op when token is unset.
    status = await _run(mw, _http_scope())
    assert status == 200
    assert stub.called is True

    # Authorization header present: still a no-op when token is unset.
    status_with_auth = await _run(
        mw,
        _http_scope((b"authorization", b"Bearer wrong")),
    )
    assert status_with_auth == 200
    assert stub.called is True


async def test_middleware_rejects_missing_bearer_when_token_set() -> None:
    stub = _StubApp()
    mw = BearerAuthMiddleware(stub, token=TOKEN)
    status = await _run(mw, _http_scope())
    assert status == 401
    assert stub.called is False


async def test_middleware_rejects_wrong_bearer_when_token_set() -> None:
    stub = _StubApp()
    mw = BearerAuthMiddleware(stub, token=TOKEN)
    status = await _run(mw, _http_scope((b"authorization", b"Bearer wrong")))
    assert status == 401
    assert stub.called is False


async def test_middleware_allows_correct_bearer_when_token_set() -> None:
    stub = _StubApp()
    mw = BearerAuthMiddleware(stub, token=TOKEN)
    status = await _run(mw, _http_scope((b"authorization", f"Bearer {TOKEN}".encode())))
    assert status == 200
    assert stub.called is True


async def test_middleware_ignores_non_http_scopes() -> None:
    # Lifespan / websocket scopes must pass through untouched even when gated.
    stub = _StubApp()
    mw = BearerAuthMiddleware(stub, token=TOKEN)

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    sent: list[Any] = []

    async def send(message: Any) -> None:
        sent.append(message)

    await mw({"type": "lifespan"}, receive, send)
    assert stub.called is True


@pytest.mark.parametrize("token_env", ["", "  "])
def test_configured_token_treats_blank_as_disabled(
    token_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atlas_mcp_doc_search.auth import configured_token

    monkeypatch.setenv(_AUTH_TOKEN_ENV, token_env)
    # Empty string disables; a whitespace-only value is a real (if odd) token.
    expected = None if token_env == "" else token_env
    assert configured_token() == expected


def test_configured_token_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from atlas_mcp_doc_search.auth import configured_token

    monkeypatch.delenv(_AUTH_TOKEN_ENV, raising=False)
    assert configured_token() is None
