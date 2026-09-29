"""The Claude OAuth transport talks to its plugin only through callbacks.

Plugin-agnostic on purpose: a fake registration stands in for the
claude_code_oauth plugin, so plugin refactors can't break core CI.
"""

from __future__ import annotations

import pytest

from code_puppy import callbacks
from code_puppy.claude_cache_client import ClaudeCacheAsyncClient


@pytest.fixture
def plugin(monkeypatch):
    """Register ``fn`` as the only callback for a phase (restored after)."""

    def _register(phase: str, fn) -> None:
        monkeypatch.setitem(callbacks._callbacks, phase, [])
        callbacks.register_callback(phase, fn)

    return _register


@pytest.mark.parametrize("answer, expected", [(True, True), (False, False)])
def test_stored_token_expiry_asks_the_plugin(plugin, answer, expected):
    plugin("check_claude_oauth_token_expiry", lambda: answer)
    assert ClaudeCacheAsyncClient._check_stored_token_expiry() is expected


async def test_opaque_bearer_defers_the_refresh_decision_to_the_plugin(plugin):
    """No decodable JWT age -> fall back to the plugin's stored-token expiry."""
    import httpx2

    plugin("check_claude_oauth_token_expiry", lambda: True)
    client = ClaudeCacheAsyncClient()
    request = httpx2.Request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    try:
        assert client._should_refresh_token(request) is True
    finally:
        await client.aclose()


def test_stored_token_expiry_is_conservative_when_the_seam_breaks(monkeypatch):
    def broken():
        raise RuntimeError("callbacks unavailable")

    monkeypatch.setattr(callbacks, "on_check_claude_oauth_token_expiry", broken)
    assert ClaudeCacheAsyncClient._check_stored_token_expiry() is False


async def test_refreshed_token_from_the_plugin_replaces_the_bearer(plugin):
    plugin("refresh_claude_oauth_token", lambda: "fresh-token")
    client = ClaudeCacheAsyncClient(headers={"Authorization": "Bearer stale"})
    try:
        assert client._refresh_claude_oauth_token() == "fresh-token"
        assert client.headers["Authorization"] == "Bearer fresh-token"
    finally:
        await client.aclose()


@pytest.mark.parametrize("registered", [True, False])
async def test_no_token_from_the_plugin_leaves_headers_alone(
    plugin, monkeypatch, registered
):
    if registered:
        plugin("refresh_claude_oauth_token", lambda: None)
    else:
        monkeypatch.setitem(callbacks._callbacks, "refresh_claude_oauth_token", [])
    client = ClaudeCacheAsyncClient(headers={"Authorization": "Bearer stale"})
    try:
        assert client._refresh_claude_oauth_token() is None
        assert client.headers["Authorization"] == "Bearer stale"
    finally:
        await client.aclose()
