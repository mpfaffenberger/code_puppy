"""
Comprehensive tests for ManagedMCPServer coverage.

Focuses on server lifecycle, start/stop operations, error handling,
and uncovered code paths.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from code_puppy.mcp_.managed_server import (
    ManagedMCPServer,
    ServerConfig,
    ServerState,
    process_tool_call,
)

# ============================================================================
# ServerState and ServerConfig Tests
# ============================================================================


class TestServerState:
    """Tests for ServerState enum."""

    def test_all_states_have_string_values(self):
        """All states should have string values for serialization."""
        assert ServerState.STOPPED.value == "stopped"
        assert ServerState.STARTING.value == "starting"
        assert ServerState.RUNNING.value == "running"
        assert ServerState.STOPPING.value == "stopping"
        assert ServerState.ERROR.value == "error"
        assert ServerState.QUARANTINED.value == "quarantined"


class TestServerConfig:
    """Tests for ServerConfig dataclass."""

    def test_minimal_config(self):
        """Test creating config with minimal required fields."""
        config = ServerConfig(id="test-id", name="test-name", type="sse")
        assert config.id == "test-id"
        assert config.name == "test-name"
        assert config.type == "sse"
        assert config.enabled is True  # default
        assert config.config == {}  # default

    def test_full_config(self):
        """Test creating config with all fields."""
        config = ServerConfig(
            id="test-id",
            name="test-name",
            type="stdio",
            enabled=False,
            config={"command": "python", "args": ["-m", "server"]},
        )
        assert config.enabled is False
        assert config.config["command"] == "python"


# ============================================================================
# process_tool_call Tests
# ============================================================================


class TestProcessToolCall:
    """Tests for process_tool_call function."""

    @pytest.mark.asyncio
    async def test_process_tool_call_emits_info_and_calls_tool(self):
        """Test that process_tool_call emits info and calls the underlying tool."""
        mock_ctx = Mock()
        mock_ctx.deps = {"some": "deps"}

        mock_call_tool = AsyncMock(return_value="tool_result")

        with patch("rich.console.Console") as mock_console_cls:
            mock_console = Mock()
            mock_console_cls.return_value = mock_console
            result = await process_tool_call(
                ctx=mock_ctx,
                call_tool=mock_call_tool,
                name="test_tool",
                tool_args={"arg1": "value1"},
            )

        # Verify banner was printed with tool name
        mock_console.print.assert_called_once()
        printed = mock_console.print.call_args[0][0]
        assert "test_tool" in printed
        assert "MCP TOOL CALL" in printed

        # Verify call_tool was called with correct args
        mock_call_tool.assert_called_once_with(
            "test_tool", {"arg1": "value1"}, {"deps": mock_ctx.deps}
        )

        # Verify result is passed through
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_process_tool_call_with_empty_args(self):
        """Test process_tool_call with empty arguments."""
        mock_ctx = Mock()
        mock_ctx.deps = None

        mock_call_tool = AsyncMock(return_value="result")

        with patch("rich.console.Console"):
            result = await process_tool_call(
                ctx=mock_ctx,
                call_tool=mock_call_tool,
                name="empty_args_tool",
                tool_args={},
            )

        mock_call_tool.assert_called_once_with("empty_args_tool", {}, {"deps": None})
        assert result == "result"


# ============================================================================
# ManagedMCPServer Initialization Tests
# ============================================================================


class TestManagedMCPServerInit:
    """Tests for ManagedMCPServer initialization."""

    def test_init_sets_default_state(self):
        """Test that initialization sets correct default state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        assert server._state == ServerState.STOPPED
        assert server._enabled is False  # Always starts disabled
        assert server._quarantine_until is None
        assert server._start_time is None
        assert server._stop_time is None
        assert server._error_message is None

    def test_init_handles_create_server_error(self):
        """Test that init handles _create_server exceptions."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE",
            side_effect=Exception("Connection failed"),
        ):
            server = ManagedMCPServer(config)

        assert server._state == ServerState.ERROR
        assert server._error_message == "Connection failed"
        assert server._pydantic_server is None


# ============================================================================
# get_pydantic_server Tests
# ============================================================================


class TestGetPydanticServer:
    """Tests for get_pydantic_server method."""

    def test_raises_when_server_is_none(self):
        """Test RuntimeError when server is None."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerSSE",
            side_effect=Exception("Failed"),
        ):
            server = ManagedMCPServer(config)

        with pytest.raises(RuntimeError, match="is not available"):
            server.get_pydantic_server()

    def test_raises_when_disabled(self):
        """Test RuntimeError when server is disabled."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        # Server starts disabled by default
        assert server._enabled is False

        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()

    def test_raises_when_quarantined(self):
        """Test RuntimeError when server is quarantined."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        server.quarantine(3600)  # Quarantine for 1 hour

        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()

    def test_returns_server_when_enabled(self):
        """Test that enabled server returns the pydantic server."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        mock_pydantic_server = MagicMock()
        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = mock_pydantic_server
            server = ManagedMCPServer(config)

        server.enable()

        result = server.get_pydantic_server()
        assert result is mock_pydantic_server


# ============================================================================
# _create_server Tests - SSE
# ============================================================================


class TestCreateServerSSE:
    """Tests for SSE server creation."""

    def test_sse_requires_url(self):
        """Test that SSE server requires url in config."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={},  # Missing url
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()

    def test_sse_with_timeout(self):
        """Test SSE server with timeout option."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080", "timeout": 30},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_sse.call_args.kwargs
            assert call_kwargs["timeout"] == 30

    def test_sse_with_read_timeout(self):
        """Test SSE server with read_timeout option."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080", "read_timeout": 120},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_sse.call_args.kwargs
            assert call_kwargs["read_timeout"] == 120

    def test_sse_with_http_client(self):
        """Test SSE server with provided http_client."""
        mock_client = MagicMock()
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080", "http_client": mock_client},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_sse.call_args.kwargs
            assert call_kwargs["http_client"] is mock_client

    def test_sse_with_headers_creates_http_client(self):
        """Test SSE server with headers creates http client."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer token"},
            },
        )

        mock_http_client = MagicMock()
        with (
            patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse,
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_http_client,
            ),
        ):
            mock_sse.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_sse.call_args.kwargs
            assert call_kwargs["http_client"] is mock_http_client


# ============================================================================
# _create_server Tests - STDIO
# ============================================================================


class TestCreateServerStdio:
    """Tests for STDIO server creation."""

    def test_stdio_requires_command(self):
        """Test that STDIO server requires command in config."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={},  # Missing command
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "command" in server._error_message.lower()

    def test_stdio_with_string_args(self):
        """Test STDIO server with string args (split into list)."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "args": "-m server --port 8080"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["args"] == ["-m", "server", "--port", "8080"]

    def test_stdio_with_list_args(self):
        """Test STDIO server with list args."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "args": ["-m", "server"]},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["args"] == ["-m", "server"]

    def test_stdio_with_env(self):
        """Test STDIO server with environment variables."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "env": {"MY_VAR": "value"}},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["env"] == {"MY_VAR": "value"}

    def test_stdio_with_cwd(self):
        """Test STDIO server with working directory."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "cwd": "/some/path"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["cwd"] == "/some/path"

    def test_stdio_default_timeout(self):
        """Test STDIO server has default 60s timeout."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python"},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["timeout"] == 60

    def test_stdio_custom_timeout(self):
        """Test STDIO server with custom timeout."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "timeout": 120},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["timeout"] == 120

    def test_stdio_with_read_timeout(self):
        """Test STDIO server with read_timeout."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python", "read_timeout": 300},
        )

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
        ) as mock_stdio:
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_stdio.call_args.kwargs
            assert call_kwargs["read_timeout"] == 300


# ============================================================================
# _create_server Tests - HTTP
# ============================================================================


class TestCreateServerHTTP:
    """Tests for HTTP server creation."""

    def test_http_requires_url(self):
        """Test that HTTP server requires url in config."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="http",
            config={},  # Missing url
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()

    def test_http_with_timeout(self):
        """Test HTTP server with timeout option."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="http",
            config={"url": "http://localhost:8080", "timeout": 45},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
        ) as mock_http:
            mock_http.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_http.call_args.kwargs
            assert call_kwargs["timeout"] == 45

    def test_http_with_read_timeout(self):
        """Test HTTP server with read_timeout option."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="http",
            config={"url": "http://localhost:8080", "read_timeout": 200},
        )

        with patch(
            "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"
        ) as mock_http:
            mock_http.return_value = MagicMock()
            ManagedMCPServer(config)

            call_kwargs = mock_http.call_args.kwargs
            assert call_kwargs["read_timeout"] == 200


# ============================================================================
# _create_server Tests - Unsupported Type
# ============================================================================


class TestCreateServerUnsupported:
    """Tests for unsupported server types."""

    def test_unsupported_type_raises_error(self):
        """Test that unsupported server type sets ERROR state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="unknown",
            config={"url": "http://localhost:8080"},
        )

        server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert "unsupported" in server._error_message.lower()


# ============================================================================
# _get_http_client Tests
# ============================================================================


class TestGetHttpClient:
    """Tests for _get_http_client method."""

    def test_creates_client_with_expanded_headers(self):
        """Test that headers env vars are expanded."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"Authorization": "Bearer $TEST_TOKEN"},
            },
        )

        with (
            patch.dict(os.environ, {"TEST_TOKEN": "secret123"}),
            patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse,
            patch("code_puppy.mcp_.managed_server.create_async_client") as mock_create,
        ):
            mock_sse.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            server = ManagedMCPServer(config)
            server._get_http_client()

            mock_create.assert_called()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["headers"]["Authorization"] == "Bearer secret123"

    def test_creates_client_with_custom_timeout(self):
        """Test that custom timeout is used."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {},
                "timeout": 60,
            },
        )

        with (
            patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse,
            patch("code_puppy.mcp_.managed_server.create_async_client") as mock_create,
        ):
            mock_sse.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            server = ManagedMCPServer(config)
            server._get_http_client()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["timeout"] == 60

    def test_handles_non_string_header_values(self):
        """Test that non-string header values pass through unchanged."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={
                "url": "http://localhost:8080",
                "headers": {"X-Count": 42, "X-String": "value"},
            },
        )

        with (
            patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse,
            patch("code_puppy.mcp_.managed_server.create_async_client") as mock_create,
        ):
            mock_sse.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            server = ManagedMCPServer(config)
            server._get_http_client()

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["headers"]["X-Count"] == 42
            assert call_kwargs["headers"]["X-String"] == "value"


# ============================================================================
# enable/disable Tests
# ============================================================================


class TestEnableDisable:
    """Tests for enable/disable methods."""

    def test_enable_starts_running_server(self):
        """Test that enable transitions server to RUNNING."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        assert server._state == ServerState.STOPPED
        assert server._enabled is False

        server.enable()

        assert server._enabled is True
        assert server._state == ServerState.RUNNING
        assert server._start_time is not None

    def test_disable_stops_running_server(self):
        """Test that disable transitions server to STOPPED."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        assert server._state == ServerState.RUNNING

        server.disable()

        assert server._enabled is False
        assert server._state == ServerState.STOPPED
        assert server._stop_time is not None

    def test_is_enabled_reflects_state(self):
        """Test that is_enabled returns correct state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        assert server.is_enabled() is False
        server.enable()
        assert server.is_enabled() is True
        server.disable()
        assert server.is_enabled() is False


# ============================================================================
# quarantine Tests
# ============================================================================


class TestQuarantine:
    """Tests for quarantine functionality."""

    def test_quarantine_sets_state(self):
        """Test that quarantine sets QUARANTINED state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        server.quarantine(3600)

        assert server._state == ServerState.QUARANTINED
        assert server.is_quarantined() is True

    def test_is_quarantined_when_not_quarantined(self):
        """Test is_quarantined returns False when not quarantined."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        assert server.is_quarantined() is False

    def test_quarantine_expires(self):
        """Test that quarantine expires after duration."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        # Set quarantine to past time
        server._quarantine_until = datetime.now() - timedelta(seconds=1)
        server._state = ServerState.QUARANTINED

        # is_quarantined should now return False and restore state
        assert server.is_quarantined() is False
        assert server._quarantine_until is None
        assert server._state == ServerState.RUNNING  # Restored because enabled

    def test_quarantine_expires_to_stopped_when_disabled(self):
        """Test quarantine expiry sets STOPPED state when disabled."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        # Don't enable - stay disabled
        server._quarantine_until = datetime.now() - timedelta(seconds=1)
        server._state = ServerState.QUARANTINED

        # is_quarantined should now return False and restore state
        assert server.is_quarantined() is False
        assert server._state == ServerState.STOPPED  # Because disabled


# ============================================================================
# get_captured_stderr Tests
# ============================================================================


class TestGetCapturedStderr:
    """Tests for get_captured_stderr method."""

    def test_returns_empty_for_non_stdio_server(self):
        """Test returns empty list for SSE server."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        assert server.get_captured_stderr() == []

    def test_returns_stderr_for_stdio_server(self):
        """Test returns captured stderr for stdio server."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python"},
        )

        # Create a proper mock that passes isinstance check
        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.get_captured_stderr.return_value = ["error line 1", "error line 2"]

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            # Manually set the server to our mock for isinstance to work
            server._pydantic_server = mock_stdio

        result = server.get_captured_stderr()
        assert result == ["error line 1", "error line 2"]


# ============================================================================
# wait_until_ready Tests
# ============================================================================


class TestWaitUntilReady:
    """Tests for wait_until_ready method."""

    @pytest.mark.asyncio
    async def test_non_stdio_returns_true_immediately(self):
        """Test non-stdio servers return True immediately."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        result = await server.wait_until_ready()
        assert result is True

    @pytest.mark.asyncio
    async def test_stdio_waits_for_ready(self):
        """Test stdio server waits for ready."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python"},
        )

        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.wait_until_ready = AsyncMock()

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            server._pydantic_server = mock_stdio

        result = await server.wait_until_ready(timeout=10.0)
        assert result is True
        mock_stdio.wait_until_ready.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_stdio_returns_false_on_exception(self):
        """Test stdio server returns False on exception."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python"},
        )

        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.wait_until_ready = AsyncMock(side_effect=Exception("Timeout"))

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            server._pydantic_server = mock_stdio

        result = await server.wait_until_ready()
        assert result is False


# ============================================================================
# ensure_ready Tests
# ============================================================================


class TestEnsureReady:
    """Tests for ensure_ready method."""

    @pytest.mark.asyncio
    async def test_non_stdio_does_nothing(self):
        """Test ensure_ready does nothing for non-stdio servers."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        # Should not raise
        await server.ensure_ready()

    @pytest.mark.asyncio
    async def test_stdio_calls_ensure_ready(self):
        """Test ensure_ready calls underlying method for stdio."""
        from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            config={"command": "python"},
        )

        mock_stdio = MagicMock(spec=BlockingMCPServerStdio)
        mock_stdio.ensure_ready = AsyncMock()

        with patch(
            "code_puppy.mcp_.managed_server.BlockingMCPServerStdio",
            return_value=mock_stdio,
        ):
            server = ManagedMCPServer(config)
            server._pydantic_server = mock_stdio

        await server.ensure_ready(timeout=15.0)
        mock_stdio.ensure_ready.assert_called_once_with(15.0)


# ============================================================================
# get_status Tests
# ============================================================================


class TestGetStatus:
    """Tests for get_status method."""

    def test_returns_complete_status(self):
        """Test get_status returns all expected fields."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        status = server.get_status()

        assert status["id"] == "test-id"
        assert status["name"] == "test-server"
        assert status["type"] == "sse"
        assert status["state"] == "stopped"
        assert status["enabled"] is False
        assert status["quarantined"] is False
        assert status["quarantine_remaining_seconds"] is None
        assert status["uptime_seconds"] is None
        assert status["start_time"] is None
        assert status["stop_time"] is None
        assert status["error_message"] is None
        assert "config" in status
        assert status["server_available"] is False

    def test_status_with_running_server(self):
        """Test get_status for running server shows uptime."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        status = server.get_status()

        assert status["state"] == "running"
        assert status["enabled"] is True
        assert status["uptime_seconds"] is not None
        assert status["uptime_seconds"] >= 0
        assert status["start_time"] is not None
        assert status["server_available"] is True

    def test_status_with_quarantined_server(self):
        """Test get_status for quarantined server."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        server.enable()
        server.quarantine(3600)
        status = server.get_status()

        assert status["state"] == "quarantined"
        assert status["quarantined"] is True
        assert status["quarantine_remaining_seconds"] is not None
        assert status["quarantine_remaining_seconds"] > 0
        assert status["server_available"] is False

    def test_status_with_error_server(self):
        """Test get_status for server in ERROR state."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={},  # Missing url causes error
        )

        server = ManagedMCPServer(config)
        status = server.get_status()

        assert status["state"] == "error"
        assert status["error_message"] is not None
        assert status["server_available"] is False

    def test_status_config_is_copy(self):
        """Test that status config is a copy (not mutable reference)."""
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )

        with patch("code_puppy.mcp_.managed_server.MCPServerSSE") as mock_sse:
            mock_sse.return_value = MagicMock()
            server = ManagedMCPServer(config)

        status = server.get_status()
        status["config"]["url"] = "modified"

        # Original config should be unchanged
        assert server.config.config["url"] == "http://localhost:8080"
