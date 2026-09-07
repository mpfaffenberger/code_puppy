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


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_registration_persists_template_not_expanded_endpoint(
    monkeypatch, tmp_path, transport
):
    monkeypatch.setenv("MCP_TEST_BASE", "https://example.invalid/private-marker")
    path = tmp_path / "registry.json"
    registry = ServerRegistry(str(path))
    template = "${MCP_TEST_BASE}/mcp"
    config = ServerConfig(
        id="test", name="test", type=transport, config={"url": template}
    )
    assert registry.register(config) == "test"
    persisted = path.read_text()
    assert "private-marker" not in persisted
    assert template in persisted
    restored = ServerRegistry(str(path)).get("test")
    assert restored is not None
    assert restored.config["url"] == template


@pytest.mark.parametrize("transport", ["http", "sse"])
def test_registration_error_does_not_disclose_expansion(
    monkeypatch, tmp_path, caplog, transport
):
    monkeypatch.setenv("MCP_TEST_BASE", "file:///private/SECRET")
    path = tmp_path / "registry.json"
    registry = ServerRegistry(str(path))
    config = ServerConfig(
        id="test", name="test", type=transport, config={"url": "$MCP_TEST_BASE/mcp"}
    )
    with pytest.raises(
        ValueError, match="URL must start with http:// or https://"
    ) as exc:
        registry.register(config)
    assert "SECRET" not in str(exc.value) + caplog.text
    assert "MCP_TEST_BASE" not in str(exc.value) + caplog.text
    assert not path.exists()
