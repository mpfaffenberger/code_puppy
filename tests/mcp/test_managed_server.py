"""
Tests for ManagedMCPServer.

Comprehensive coverage for server lifecycle management, configuration,
and status tracking functionality.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.mcp_.managed_server import (
    ManagedMCPServer,
    ServerConfig,
    ServerState,
    _expand_env_vars,
    process_tool_call,
)


# =============================================================================
# _expand_env_vars tests
# =============================================================================


class TestExpandEnvVars:
    """Tests for the _expand_env_vars helper function."""

    def test_expand_env_vars_string(self):
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

    def test_expand_env_vars_dict(self):
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

    def test_expand_env_vars_list(self):
        """Test env var expansion in lists."""
        with patch.dict(os.environ, {"ARG1": "value1", "ARG2": "value2"}):
            input_list = ["$ARG1", "static", "$ARG2"]
            result = _expand_env_vars(input_list)
            assert result == ["value1", "static", "value2"]

    def test_expand_env_vars_nested(self):
        """Test env var expansion in nested structures."""
        with patch.dict(os.environ, {"KEY": "secret"}):
            input_nested = {
                "headers": {"Auth": "Bearer $KEY"},
                "args": ["--key=$KEY"],
            }
            result = _expand_env_vars(input_nested)
            assert result["headers"]["Auth"] == "Bearer secret"
            assert result["args"] == ["--key=secret"]

    def test_expand_env_vars_non_string(self):
        """Test that non-string values pass through unchanged."""
        assert _expand_env_vars(42) == 42
        assert _expand_env_vars(3.14) == 3.14
        assert _expand_env_vars(True) is True
        assert _expand_env_vars(None) is None


# =============================================================================
# process_tool_call tests
# =============================================================================


class TestProcessToolCall:
    """Tests for the process_tool_call function."""

    @pytest.mark.asyncio
    async def test_process_tool_call_basic(self):
        """Test basic tool call processing."""
        # Create mock context
        mock_ctx = MagicMock()
        mock_ctx.deps = {"some": "deps"}

        # Create mock call_tool function
        mock_call_tool = AsyncMock(return_value="tool_result")

        # Patch emit_info to avoid actual output
        with patch("code_puppy.mcp_.managed_server.emit_info"):
            result = await process_tool_call(
                ctx=mock_ctx,
                call_tool=mock_call_tool,
                name="test_tool",
                tool_args={"arg1": "value1"},
            )

        assert result == "tool_result"
        mock_call_tool.assert_called_once_with(
            "test_tool", {"arg1": "value1"}, {"deps": {"some": "deps"}}
        )

    @pytest.mark.asyncio
    async def test_process_tool_call_with_complex_args(self):
        """Test tool call with complex nested arguments."""
        mock_ctx = MagicMock()
        mock_ctx.deps = None

        mock_call_tool = AsyncMock(return_value={"nested": "result"})

        with patch("code_puppy.mcp_.managed_server.emit_info"):
            result = await process_tool_call(
                ctx=mock_ctx,
                call_tool=mock_call_tool,
                name="complex_tool",
                tool_args={"list": [1, 2, 3], "dict": {"nested": "value"}},
            )

        assert result == {"nested": "result"}


# =============================================================================
# ServerConfig tests
# =============================================================================


class TestServerConfig:
    """Tests for the ServerConfig dataclass."""

    def test_server_config_defaults(self):
        """Test ServerConfig with default values."""
        config = ServerConfig(id="test", name="test-server", type="sse")
        assert config.id == "test"
        assert config.name == "test-server"
        assert config.type == "sse"
        assert config.enabled is True
        assert config.config == {}

    def test_server_config_with_all_fields(self):
        """Test ServerConfig with all fields specified."""
        config = ServerConfig(
            id="custom-id",
            name="custom-name",
            type="stdio",
            enabled=False,
            config={"command": "echo", "args": ["hello"]},
        )
        assert config.id == "custom-id"
        assert config.name == "custom-name"
        assert config.type == "stdio"
        assert config.enabled is False
        assert config.config == {"command": "echo", "args": ["hello"]}


# =============================================================================
# ManagedMCPServer initialization tests
# =============================================================================


class TestManagedMCPServerInit:
    """Tests for ManagedMCPServer initialization."""

    def test_init_sse_server(self):
        """Test initialization with SSE server type."""
        config = ServerConfig(
            id="sse-1",
            name="sse-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_sse = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=mock_sse
        ):
            server = ManagedMCPServer(config)

        assert server.config == config
        assert server._state == ServerState.STOPPED
        assert server._enabled is False  # Always starts disabled
        assert server._pydantic_server == mock_sse

    def test_init_stdio_server(self):
        """Test initialization with stdio server type."""
        config = ServerConfig(
            id="stdio-1",
            name="stdio-server",
            type="stdio",
            config={"command": "echo", "args": ["hello"]},
        )

        mock_stdio = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)

        assert server._state == ServerState.STOPPED
        assert server._pydantic_server == mock_stdio

    def test_init_http_server(self):
        """Test initialization with HTTP server type."""
        config = ServerConfig(
            id="http-1",
            name="http-server",
            type="http",
            config={"url": "http://localhost:9090"},
        )

        mock_http = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP",
            return_value=mock_http,
        ):
            server = ManagedMCPServer(config)

        assert server._state == ServerState.STOPPED
        assert server._pydantic_server == mock_http

    def test_init_error_state(self):
        """Test that initialization errors set ERROR state."""
        config = ServerConfig(
            id="bad-1",
            name="bad-server",
            type="unsupported_type",
            config={},
        )

        server = ManagedMCPServer(config)

        assert server._state == ServerState.ERROR
        assert server._error_message is not None
        assert "unsupported_type" in server._error_message.lower()

    def test_init_sse_missing_url(self):
        """Test SSE server without URL raises error."""
        config = ServerConfig(
            id="bad-sse",
            name="bad-sse-server",
            type="sse",
            config={},  # Missing url
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()

    def test_init_stdio_missing_command(self):
        """Test stdio server without command raises error."""
        config = ServerConfig(
            id="bad-stdio",
            name="bad-stdio-server",
            type="stdio",
            config={},  # Missing command
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "command" in server._error_message.lower()

    def test_init_http_missing_url(self):
        """Test HTTP server without URL raises error."""
        config = ServerConfig(
            id="bad-http",
            name="bad-http-server",
            type="http",
            config={},  # Missing url
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()


# =============================================================================
# ManagedMCPServer SSE configuration tests
# =============================================================================


class TestManagedMCPServerSSEConfig:
    """Tests for SSE server configuration options."""

    def test_sse_with_timeout(self):
        """Test SSE server with timeout option."""
        config = ServerConfig(
            id="sse-timeout",
            name="sse-server",
            type="sse",
            config={"url": "http://localhost:8080", "timeout": 60},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["timeout"] == 60

    def test_sse_with_read_timeout(self):
        """Test SSE server with read_timeout option."""
        config = ServerConfig(
            id="sse-read-timeout",
            name="sse-server",
            type="sse",
            config={"url": "http://localhost:8080", "read_timeout": 120},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["read_timeout"] == 120

    def test_sse_with_http_client(self):
        """Test SSE server with custom http_client."""
        mock_client = MagicMock()
        config = ServerConfig(
            id="sse-client",
            name="sse-server",
            type="sse",
            config={"url": "http://localhost:8080", "http_client": mock_client},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["http_client"] == mock_client

    def test_sse_with_headers_creates_http_client(self):
        """Test SSE server with headers creates http_client."""
        config = ServerConfig(
            id="sse-headers",
            name="sse-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer token"},
            },
        )

        mock_client = MagicMock()
        with (
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE"
            ) as mock_constructor,
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_client,
            ),
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["http_client"] == mock_client

    def test_sse_env_var_expansion_in_url(self):
        """Test that SSE URL has env vars expanded."""
        config = ServerConfig(
            id="sse-env",
            name="sse-server",
            type="sse",
            config={"url": "http://$SSE_HOST:$SSE_PORT"},
        )

        with (
            patch.dict(os.environ, {"SSE_HOST": "api.example.com", "SSE_PORT": "8888"}),
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE"
            ) as mock_constructor,
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["url"] == "http://api.example.com:8888"


# =============================================================================
# ManagedMCPServer stdio configuration tests
# =============================================================================


class TestManagedMCPServerStdioConfig:
    """Tests for stdio server configuration options."""

    def test_stdio_with_string_args(self):
        """Test stdio server with args as string."""
        config = ServerConfig(
            id="stdio-str-args",
            name="stdio-server",
            type="stdio",
            config={"command": "echo", "args": "hello world"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            # String args should be split
            assert call_kwargs["args"] == ["hello", "world"]

    def test_stdio_with_list_args(self):
        """Test stdio server with args as list."""
        config = ServerConfig(
            id="stdio-list-args",
            name="stdio-server",
            type="stdio",
            config={"command": "node", "args": ["server.js", "--port", "3000"]},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["args"] == ["server.js", "--port", "3000"]

    def test_stdio_with_env(self):
        """Test stdio server with custom environment."""
        config = ServerConfig(
            id="stdio-env",
            name="stdio-server",
            type="stdio",
            config={
                "command": "echo",
                "env": {"CUSTOM_VAR": "$OUTER_VAR", "STATIC": "value"},
            },
        )

        with (
            patch.dict(os.environ, {"OUTER_VAR": "expanded"}),
            patch(
                "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
            ) as mock_constructor,
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["env"]["CUSTOM_VAR"] == "expanded"
            assert call_kwargs["env"]["STATIC"] == "value"

    def test_stdio_with_cwd(self):
        """Test stdio server with working directory."""
        config = ServerConfig(
            id="stdio-cwd",
            name="stdio-server",
            type="stdio",
            config={"command": "echo", "cwd": "$HOME/project"},
        )

        with (
            patch.dict(os.environ, {"HOME": "/home/user"}),
            patch(
                "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
            ) as mock_constructor,
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["cwd"] == "/home/user/project"

    def test_stdio_default_timeout(self):
        """Test stdio server has default 60s timeout."""
        config = ServerConfig(
            id="stdio-timeout",
            name="stdio-server",
            type="stdio",
            config={"command": "echo"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["timeout"] == 60

    def test_stdio_custom_timeout(self):
        """Test stdio server with custom timeout."""
        config = ServerConfig(
            id="stdio-custom-timeout",
            name="stdio-server",
            type="stdio",
            config={"command": "echo", "timeout": 120},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["timeout"] == 120

    def test_stdio_with_read_timeout(self):
        """Test stdio server with read_timeout option."""
        config = ServerConfig(
            id="stdio-read-timeout",
            name="stdio-server",
            type="stdio",
            config={"command": "echo", "read_timeout": 90},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["read_timeout"] == 90


# =============================================================================
# ManagedMCPServer HTTP configuration tests
# =============================================================================


class TestManagedMCPServerHTTPConfig:
    """Tests for HTTP server configuration options."""

    def test_http_basic(self):
        """Test basic HTTP server creation."""
        config = ServerConfig(
            id="http-basic",
            name="http-server",
            type="http",
            config={"url": "http://localhost:9000"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["url"] == "http://localhost:9000"

    def test_http_with_timeout(self):
        """Test HTTP server with timeout option."""
        config = ServerConfig(
            id="http-timeout",
            name="http-server",
            type="http",
            config={"url": "http://localhost:9000", "timeout": 45},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["timeout"] == 45

    def test_http_with_read_timeout(self):
        """Test HTTP server with read_timeout option."""
        config = ServerConfig(
            id="http-read-timeout",
            name="http-server",
            type="http",
            config={"url": "http://localhost:9000", "read_timeout": 180},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
        ) as mock_constructor:
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["read_timeout"] == 180

    def test_http_with_headers(self):
        """Test HTTP server with headers (passed directly, not via http_client)."""
        config = ServerConfig(
            id="http-headers",
            name="http-server",
            type="http",
            config={
                "url": "http://localhost:9000",
                "headers": {"Authorization": "Bearer $API_KEY"},
            },
        )

        with (
            patch.dict(os.environ, {"API_KEY": "secret-token"}),
            patch(
                "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
            ) as mock_constructor,
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            # Headers should be passed directly with env vars expanded
            assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token"

    def test_http_env_var_expansion_in_url(self):
        """Test that HTTP URL has env vars expanded."""
        config = ServerConfig(
            id="http-env",
            name="http-server",
            type="http",
            config={"url": "http://${HTTP_HOST}:${HTTP_PORT}/mcp"},
        )

        with (
            patch.dict(
                os.environ, {"HTTP_HOST": "mcp.example.com", "HTTP_PORT": "443"}
            ),
            patch(
                "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
            ) as mock_constructor,
        ):
            ManagedMCPServer(config)
            call_kwargs = mock_constructor.call_args.kwargs
            assert call_kwargs["url"] == "http://mcp.example.com:443/mcp"


# =============================================================================
# get_pydantic_server tests
# =============================================================================


class TestGetPydanticServer:
    """Tests for get_pydantic_server method."""

    def test_get_server_when_enabled_and_running(self):
        """Test getting server when enabled and running."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_sse = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=mock_sse
        ):
            server = ManagedMCPServer(config)
            server.enable()

        result = server.get_pydantic_server()
        assert result == mock_sse

    def test_get_server_raises_when_none(self):
        """Test get_pydantic_server raises when server is None."""
        config = ServerConfig(
            id="bad",
            name="bad-server",
            type="unsupported",
            config={},
        )

        server = ManagedMCPServer(config)
        # Server creation failed, so _pydantic_server is None

        with pytest.raises(RuntimeError, match="is not available"):
            server.get_pydantic_server()

    def test_get_server_raises_when_disabled(self):
        """Test get_pydantic_server raises when server is disabled."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_sse = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=mock_sse
        ):
            server = ManagedMCPServer(config)
            # Don't enable - server starts disabled

        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()

    def test_get_server_raises_when_quarantined(self):
        """Test get_pydantic_server raises when server is quarantined."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_sse = MagicMock()
        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=mock_sse
        ):
            server = ManagedMCPServer(config)
            server.enable()
            server.quarantine(3600)  # Quarantine for 1 hour

        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()


# =============================================================================
# _get_http_client tests
# =============================================================================


class TestGetHttpClient:
    """Tests for _get_http_client method."""

    def test_get_http_client_with_headers(self):
        """Test _get_http_client creates client with headers."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer $TOKEN", "X-Static": "value"},
            },
        )

        mock_client = MagicMock()
        with (
            patch.dict(os.environ, {"TOKEN": "my-secret"}),
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
            ),
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_client,
            ) as mock_create,
        ):
            server = ManagedMCPServer(config)
            client = server._get_http_client()

            # Verify create_async_client was called with expanded headers
            mock_create.assert_called()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret"
            assert call_kwargs["headers"]["X-Static"] == "value"
            assert client == mock_client

    def test_get_http_client_with_custom_timeout(self):
        """Test _get_http_client uses custom timeout."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080", "timeout": 90},
        )

        mock_client = MagicMock()
        with (
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
            ),
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_client,
            ) as mock_create,
        ):
            server = ManagedMCPServer(config)
            server._get_http_client()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["timeout"] == 90

    def test_get_http_client_default_timeout(self):
        """Test _get_http_client uses default 30s timeout."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_client = MagicMock()
        with (
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
            ),
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_client,
            ) as mock_create,
        ):
            server = ManagedMCPServer(config)
            server._get_http_client()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["timeout"] == 30

    def test_get_http_client_handles_non_string_header_values(self):
        """Test _get_http_client handles non-string header values."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"String-Header": "value", "Int-Header": 42},
            },
        )

        mock_client = MagicMock()
        with (
            patch(
                "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
            ),
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_client,
            ) as mock_create,
        ):
            server = ManagedMCPServer(config)
            server._get_http_client()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["headers"]["String-Header"] == "value"
            assert call_kwargs["headers"]["Int-Header"] == 42


# =============================================================================
# Enable/Disable tests
# =============================================================================


class TestEnableDisable:
    """Tests for enable and disable methods."""

    def test_enable_sets_enabled_flag(self):
        """Test enable() sets the enabled flag."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            assert server._enabled is False

            server.enable()

            assert server._enabled is True

    def test_enable_transitions_to_running(self):
        """Test enable() transitions STOPPED to RUNNING."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            assert server._state == ServerState.STOPPED

            server.enable()

            assert server._state == ServerState.RUNNING
            assert server._start_time is not None

    def test_disable_sets_enabled_flag(self):
        """Test disable() clears the enabled flag."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()
            assert server._enabled is True

            server.disable()

            assert server._enabled is False

    def test_disable_transitions_to_stopped(self):
        """Test disable() transitions RUNNING to STOPPED."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()
            assert server._state == ServerState.RUNNING

            server.disable()

            assert server._state == ServerState.STOPPED
            assert server._stop_time is not None

    def test_is_enabled_returns_correct_state(self):
        """Test is_enabled() returns correct state."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

            assert server.is_enabled() is False
            server.enable()
            assert server.is_enabled() is True
            server.disable()
            assert server.is_enabled() is False


# =============================================================================
# Quarantine tests
# =============================================================================


class TestQuarantine:
    """Tests for quarantine functionality."""

    def test_quarantine_sets_quarantine_until(self):
        """Test quarantine() sets the quarantine time."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

            server.quarantine(3600)  # 1 hour

            assert server._quarantine_until is not None
            assert server._state == ServerState.QUARANTINED

    def test_is_quarantined_returns_true_during_quarantine(self):
        """Test is_quarantined() returns True during active quarantine."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

            server.quarantine(3600)

            assert server.is_quarantined() is True

    def test_is_quarantined_returns_false_when_not_quarantined(self):
        """Test is_quarantined() returns False when not quarantined."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

            assert server.is_quarantined() is False

    def test_quarantine_expires(self):
        """Test quarantine expires after duration."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()

            # Set quarantine to expire in the past
            server._quarantine_until = datetime.now() - timedelta(seconds=1)
            server._state = ServerState.QUARANTINED

            # Check should clear quarantine
            assert server.is_quarantined() is False
            assert server._quarantine_until is None
            assert server._state == ServerState.RUNNING  # Returns to running since enabled

    def test_quarantine_expiry_goes_to_stopped_if_disabled(self):
        """Test quarantine expiry goes to STOPPED if server is disabled."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            # Don't enable - leave disabled

            # Set quarantine to expire in the past
            server._quarantine_until = datetime.now() - timedelta(seconds=1)
            server._state = ServerState.QUARANTINED

            # Check should clear quarantine
            assert server.is_quarantined() is False
            assert server._state == ServerState.STOPPED  # Returns to stopped since disabled


# =============================================================================
# get_captured_stderr tests
# =============================================================================


class TestGetCapturedStderr:
    """Tests for get_captured_stderr method."""

    def test_get_captured_stderr_for_stdio_server(self):
        """Test get_captured_stderr returns stderr for stdio servers."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            config={"command": "echo"},
        )

        # Create a proper mock that will pass isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.get_captured_stderr.return_value = ["line1", "line2", "line3"]

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set to ensure isinstance works
            server._pydantic_server = mock_stdio

        result = server.get_captured_stderr()
        assert result == ["line1", "line2", "line3"]

    def test_get_captured_stderr_returns_empty_for_non_stdio(self):
        """Test get_captured_stderr returns empty list for non-stdio servers."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

        result = server.get_captured_stderr()
        assert result == []


# =============================================================================
# wait_until_ready tests
# =============================================================================


class TestWaitUntilReady:
    """Tests for wait_until_ready method."""

    @pytest.mark.asyncio
    async def test_wait_until_ready_stdio_success(self):
        """Test wait_until_ready returns True when stdio server is ready."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            config={"command": "echo"},
        )

        # Create a proper mock that will pass isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.wait_until_ready = AsyncMock(return_value=None)

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set to ensure isinstance works
            server._pydantic_server = mock_stdio

        result = await server.wait_until_ready(timeout=10.0)
        assert result is True
        mock_stdio.wait_until_ready.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_wait_until_ready_stdio_failure(self):
        """Test wait_until_ready returns False when stdio server fails."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            config={"command": "echo"},
        )

        # Create a proper mock that will pass isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.wait_until_ready = AsyncMock(side_effect=TimeoutError("Timed out"))

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set to ensure isinstance works
            server._pydantic_server = mock_stdio

        result = await server.wait_until_ready(timeout=5.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_until_ready_non_stdio_returns_true(self):
        """Test wait_until_ready returns True immediately for non-stdio servers."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

        result = await server.wait_until_ready()
        assert result is True


# =============================================================================
# ensure_ready tests
# =============================================================================


class TestEnsureReady:
    """Tests for ensure_ready method."""

    @pytest.mark.asyncio
    async def test_ensure_ready_stdio_success(self):
        """Test ensure_ready completes successfully for stdio server."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            config={"command": "echo"},
        )

        # Create a proper mock that will pass isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.ensure_ready = AsyncMock(return_value=None)

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set to ensure isinstance works
            server._pydantic_server = mock_stdio

        await server.ensure_ready(timeout=10.0)
        mock_stdio.ensure_ready.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_ensure_ready_stdio_raises_on_failure(self):
        """Test ensure_ready raises exception for stdio server failure."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test",
            name="test-server",
            type="stdio",
            config={"command": "echo"},
        )

        # Create a proper mock that will pass isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.ensure_ready = AsyncMock(side_effect=TimeoutError("Server failed"))

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set to ensure isinstance works
            server._pydantic_server = mock_stdio

        with pytest.raises(TimeoutError, match="Server failed"):
            await server.ensure_ready(timeout=5.0)

    @pytest.mark.asyncio
    async def test_ensure_ready_non_stdio_does_nothing(self):
        """Test ensure_ready does nothing for non-stdio servers."""
        config = ServerConfig(
            id="test",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

        # Should complete without error
        await server.ensure_ready()


# =============================================================================
# get_status tests
# =============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_basic(self):
        """Test get_status returns basic status information."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

        status = server.get_status()

        assert status["id"] == "test-id"
        assert status["name"] == "test-server"
        assert status["type"] == "sse"
        assert status["state"] == "stopped"
        assert status["enabled"] is False
        assert status["quarantined"] is False
        assert status["server_available"] is False

    def test_get_status_running_server(self):
        """Test get_status for running server shows uptime."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()

        status = server.get_status()

        assert status["state"] == "running"
        assert status["enabled"] is True
        assert status["uptime_seconds"] is not None
        assert status["uptime_seconds"] >= 0
        assert status["start_time"] is not None
        assert status["server_available"] is True

    def test_get_status_quarantined_server(self):
        """Test get_status for quarantined server shows remaining time."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()
            server.quarantine(3600)  # 1 hour

        status = server.get_status()

        assert status["state"] == "quarantined"
        assert status["quarantined"] is True
        assert status["quarantine_remaining_seconds"] is not None
        assert status["quarantine_remaining_seconds"] > 0
        assert status["server_available"] is False

    def test_get_status_error_server(self):
        """Test get_status for server in error state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="unsupported",
            config={},
        )

        server = ManagedMCPServer(config)

        status = server.get_status()

        assert status["state"] == "error"
        assert status["error_message"] is not None
        assert status["server_available"] is False

    def test_get_status_includes_config_copy(self):
        """Test get_status includes a copy of config."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080", "extra": "value"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)

        status = server.get_status()

        # Config should be included
        assert status["config"]["url"] == "http://localhost:8080"
        assert status["config"]["extra"] == "value"

        # Modifying the returned config shouldn't affect the original
        status["config"]["url"] = "modified"
        assert server.config.config["url"] == "http://localhost:8080"

    def test_get_status_stop_time(self):
        """Test get_status includes stop_time after disable."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE", return_value=MagicMock()
        ):
            server = ManagedMCPServer(config)
            server.enable()
            server.disable()

        status = server.get_status()

        assert status["stop_time"] is not None


# =============================================================================
# ServerState enum tests
# =============================================================================


class TestServerState:
    """Tests for ServerState enum."""

    def test_all_states_defined(self):
        """Test all expected states are defined."""
        assert ServerState.STOPPED.value == "stopped"
        assert ServerState.STARTING.value == "starting"
        assert ServerState.RUNNING.value == "running"
        assert ServerState.STOPPING.value == "stopping"
        assert ServerState.ERROR.value == "error"
        assert ServerState.QUARANTINED.value == "quarantined"

    def test_state_values_are_strings(self):
        """Test all state values are strings."""
        for state in ServerState:
            assert isinstance(state.value, str)
