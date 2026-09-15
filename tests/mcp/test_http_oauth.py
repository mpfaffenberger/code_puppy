"""OAuth configuration and transport integration, without real browser login."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.http_auth import http_auth
from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig


def test_no_auth_preserves_existing_behavior():
    assert http_auth({}, "http://remote/mcp", {"Authorization": "Bearer token"}) is None


@pytest.mark.parametrize("method", ["basic", "Bearer secret", {}, True])
def test_invalid_auth_rejected(method):
    with pytest.raises(ValueError):
        http_auth({"auth": method}, "https://example.com/mcp", None)


@pytest.mark.parametrize(
    "url",
    ["http://remote/mcp", "ftp://localhost/mcp", "https://user:secret@example.com/mcp"],
)
def test_insecure_oauth_url_rejected(url):
    with pytest.raises(ValueError):
        http_auth({"auth": "oauth"}, url, None)


@pytest.mark.parametrize("header", ["Authorization", "authorization", "AUTHORIZATION"])
def test_conflicting_credentials_rejected(header):
    with pytest.raises(ValueError):
        http_auth({"auth": "oauth"}, "https://example.com/mcp", {header: "secret"})


@pytest.mark.parametrize(
    "url", ["https://example.com/mcp", "http://127.0.0.1:8080/mcp"]
)
def test_oauth_provider_is_deferred(url):
    provider = http_auth({"auth": "oauth"}, url, None)
    assert provider._bound is False
    assert provider._callback_host == "127.0.0.1"


@pytest.mark.parametrize("timeout,expected", [(None, 330), (90, 90)])
def test_http_transport_receives_oauth_and_login_timeout(
    monkeypatch, timeout, expected
):
    monkeypatch.setenv("TEST_MCP_URL", "https://example.com/mcp")
    config = {"url": "$TEST_MCP_URL", "auth": "oauth"}
    if timeout is not None:
        config["timeout"] = timeout
    with (
        patch("code_puppy.mcp_.managed_server.StreamableHttpTransport") as transport,
        patch("code_puppy.mcp_.managed_server.MCPToolset") as toolset,
    ):
        ManagedMCPServer(
            ServerConfig(id="test", name="test", type="http", config=config)
        )
    assert transport.call_args.kwargs["url"] == "https://example.com/mcp"
    assert transport.call_args.kwargs["auth"] is not None
    assert toolset.call_args.kwargs["init_timeout"] == expected


def test_wizard_can_choose_oauth():
    from code_puppy.mcp_.config_wizard import MCPConfigWizard

    with (
        patch(
            "code_puppy.mcp_.config_wizard.get_mcp_manager", return_value=MagicMock()
        ),
        patch("code_puppy.mcp_.config_wizard.confirm_ask", side_effect=[True, False]),
        patch("code_puppy.mcp_.config_wizard.prompt_ask", return_value="330"),
        patch.object(
            MCPConfigWizard, "prompt_url", return_value="https://example.com/mcp"
        ),
    ):
        config = MCPConfigWizard().prompt_http_config()
    assert config["auth"] == "oauth"
    assert config["timeout"] == 330
