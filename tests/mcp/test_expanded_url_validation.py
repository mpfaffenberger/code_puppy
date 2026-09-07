"""Registry validation and runtime must agree without exposing expanded secrets."""

import pytest

from code_puppy.mcp_.managed_server import ServerConfig, _expand_env_vars
from code_puppy.mcp_.registry import ServerRegistry


@pytest.mark.parametrize("transport", ["http", "sse"])
@pytest.mark.parametrize(
    "url", ["$MCP_TEST_BASE/mcp", "${MCP_TEST_BASE}/mcp", "https://example.invalid/mcp"]
)
def test_expanded_url_is_accepted_without_mutating_config(monkeypatch, transport, url):
    monkeypatch.setenv("MCP_TEST_BASE", "https://example.invalid")
    config = ServerConfig(id="test", name="test", type=transport, config={"url": url})
    assert _expand_env_vars(url).startswith("https://")
    assert ServerRegistry.validate_config(object.__new__(ServerRegistry), config) == []
    assert config.config["url"] == url


@pytest.mark.parametrize(
    "value", [None, "", "file:///private/SECRET", "SECRET-not-a-url"]
)
def test_invalid_expansion_is_rejected_without_echoing_it(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MCP_TEST_BASE", raising=False)
    else:
        monkeypatch.setenv("MCP_TEST_BASE", value)
    config = ServerConfig(
        id="test", name="test", type="http", config={"url": "$MCP_TEST_BASE/mcp"}
    )
    errors = ServerRegistry.validate_config(object.__new__(ServerRegistry), config)
    assert errors
    assert "SECRET" not in str(errors)
    assert "MCP_TEST_BASE" not in str(errors)
