"""
Tests for ManagedMCPServer.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.managed_server import (
    ManagedMCPServer,
    ServerConfig,
    ServerState,
    _expand_env_vars,
)


@pytest.mark.asyncio
async def test_managed_server_header_env_expansion_mocked():
    """Test that headers with env vars are expanded correctly (using mocks).

    Headers are now passed directly to MCPServerStreamableHTTP instead of
    creating a custom http_client. This is a workaround for MCP 1.25.0 bug.
    """

    config_dict = {
        "url": "http://test.com",
        "headers": {
            "Authorization": "Bearer ${TEST_API_KEY}",
            "X-Custom": "FixedValue",
        },
    }

    server_config = ServerConfig(
        id="test-id", name="test-server", type="http", config=config_dict
    )

    mock_http_server = MagicMock()

    with (
        patch.dict(os.environ, {"TEST_API_KEY": "secret-123"}),
        patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP",
            return_value=mock_http_server,
        ) as mock_constructor,
    ):
        ManagedMCPServer(server_config)

        # Verify MCPServerStreamableHTTP was called with expanded headers
        mock_constructor.assert_called_once()
        call_kwargs = mock_constructor.call_args.kwargs

        # Headers should be passed directly and env vars expanded
        assert call_kwargs["headers"]["Authorization"] == "Bearer secret-123"
        assert call_kwargs["headers"]["X-Custom"] == "FixedValue"
        assert call_kwargs["url"] == "http://test.com"
        assert call_kwargs["tool_prefix"] == "test-server"


def test_stdio_tool_prefix_includes_server_name_and_configured_prefix():
    """Configured MCP prefixes are nested under the server name."""
    config_dict = {
        "command": "python",
        "tool_prefix": "repo",
    }
    server_config = ServerConfig(
        id="test-id", name="filesystem", type="stdio", config=config_dict
    )

    with patch("code_puppy.mcp_.managed_server.BlockingMCPServerStdio") as mock_stdio:
        mock_stdio.return_value = MagicMock()
        ManagedMCPServer(server_config)

    call_kwargs = mock_stdio.call_args.kwargs
    assert call_kwargs["tool_prefix"] == "filesystem_repo"


def test_sse_tool_prefix_uses_server_name():
    """SSE servers should namespace tools with their MCP server name too."""
    server_config = ServerConfig(
        id="test-id",
        name="docs",
        type="sse",
        config={"url": "http://localhost:8080/sse"},
    )

    with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
        mock_sse.return_value = MagicMock()
        ManagedMCPServer(server_config)

    call_kwargs = mock_sse.call_args.kwargs
    assert call_kwargs["tool_prefix"] == "docs"


def test_http_tool_prefix_expands_and_nests_configured_prefix():
    """HTTP prefixes include the server name plus any configured prefix."""
    server_config = ServerConfig(
        id="test-id",
        name="github",
        type="http",
        config={"url": "http://localhost:8080/mcp", "tool_prefix": "$MCP_SCOPE"},
    )

    with (
        patch.dict(os.environ, {"MCP_SCOPE": "issues"}),
        patch("code_puppy.mcp_.managed_server.MCPServerStreamableHTTP") as mock_http,
    ):
        mock_http.return_value = MagicMock()
        ManagedMCPServer(server_config)

    call_kwargs = mock_http.call_args.kwargs
    assert call_kwargs["tool_prefix"] == "github_issues"


def test_expand_env_vars_string():
    """Test env var expansion in strings."""
    with patch.dict(os.environ, {"MY_VAR": "expanded_value"}):
        # $VAR syntax
        assert _expand_env_vars("$MY_VAR") == "expanded_value"
        # ${VAR} syntax
        assert _expand_env_vars("${MY_VAR}") == "expanded_value"
        # Mixed content
        assert _expand_env_vars("Bearer $MY_VAR") == "Bearer expanded_value"
        # Plain string (no vars)
        assert _expand_env_vars("plain text") == "plain text"


def test_expand_env_vars_dict():
    """Test env var expansion in dicts."""
    with patch.dict(os.environ, {"API_KEY": "secret123", "HOST": "example.com"}):
        input_dict = {
            "Authorization": "Bearer $API_KEY",
            "Host": "$HOST",
            "Static": "no-change",
        }
        result = _expand_env_vars(input_dict)
        assert result["Authorization"] == "Bearer secret123"
        assert result["Host"] == "example.com"
        assert result["Static"] == "no-change"


def test_expand_env_vars_list():
    """Test env var expansion in lists."""
    with patch.dict(os.environ, {"ARG1": "value1", "ARG2": "value2"}):
        input_list = ["$ARG1", "static", "$ARG2"]
        result = _expand_env_vars(input_list)
        assert result == ["value1", "static", "value2"]


def test_expand_env_vars_nested():
    """Test env var expansion in nested structures."""
    with patch.dict(os.environ, {"KEY": "secret"}):
        input_nested = {
            "headers": {"Auth": "Bearer $KEY"},
            "args": ["--key=$KEY"],
        }
        result = _expand_env_vars(input_nested)
        assert result["headers"]["Auth"] == "Bearer secret"
        assert result["args"] == ["--key=secret"]


def test_expand_env_vars_non_string():
    """Test that non-string values pass through unchanged."""
    assert _expand_env_vars(42) == 42
    assert _expand_env_vars(3.14) == 3.14
    assert _expand_env_vars(True) is True
    assert _expand_env_vars(None) is None


class TestManagedMCPServerEnableFromConfig:
    """ManagedMCPServer._enabled should be initialised from ServerConfig.enabled.

    Before this fix, __init__ hardcoded ``self._enabled = False`` regardless
    of ``server_config.enabled``.  Every server therefore required an explicit
    ``/mcp start`` command before ``get_servers_for_agent()`` would include it.
    """

    def _make_config(self, enabled: bool) -> ServerConfig:
        return ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            enabled=enabled,
            config={"command": "echo", "args": []},
        )

    def test_enabled_true_in_config_makes_server_enabled(self):
        """ServerConfig(enabled=True) → is_enabled() is True right after construction."""
        server = ManagedMCPServer(self._make_config(enabled=True))
        assert server.is_enabled() is True

    def test_enabled_false_in_config_makes_server_disabled(self):
        """ServerConfig(enabled=False) → is_enabled() is False right after construction."""
        server = ManagedMCPServer(self._make_config(enabled=False))
        assert server.is_enabled() is False

    def test_enabled_flag_and_tracker_state_are_independent(self):
        """is_enabled() can be True while tracker state stays STOPPED.

        The enabled flag gates get_servers_for_agent() — it makes the server
        visible to pydantic-ai immediately on launch.  The tracker state only
        advances to RUNNING after start_server() actually spawns a subprocess
        and calls record_start_time().  Conflating the two caused
        ``/mcp status`` to show ``State: ✓ Run, Uptime: -`` because
        record_start_time() was never called.
        """
        server = ManagedMCPServer(self._make_config(enabled=True))
        assert server.is_enabled() is True
        # Internal _state is set in __init__ — it should still be STOPPED
        assert server._state == ServerState.STOPPED

    def test_enable_disable_still_work_as_runtime_overrides(self):
        """enable()/disable() remain valid for explicit runtime control."""
        server = ManagedMCPServer(self._make_config(enabled=False))
        assert server.is_enabled() is False

        server.enable()
        assert server.is_enabled() is True

        server.disable()
        assert server.is_enabled() is False
