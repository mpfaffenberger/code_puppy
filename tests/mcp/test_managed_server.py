"""
Tests for ManagedMCPServer.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from code_puppy.mcp_.managed_server import (
    ManagedMCPServer,
    ServerConfig,
    ServerState,
    _expand_env_vars,
    process_tool_call,
)

SSE = "code_puppy.mcp_.managed_server.MCPServerSSE"
STDIO = "code_puppy.mcp_.managed_server.BlockingMCPServerStdio"
HTTP = "code_puppy.mcp_.managed_server.MCPServerStreamableHTTP"


def _server(srv_type, inner, patch_target=SSE, enabled=True):
    config = ServerConfig(
        id="test-id", name="test-server", type=srv_type, enabled=enabled, config=inner
    )
    with patch(patch_target) as mock_cls:
        mock_cls.return_value = MagicMock()
        server = ManagedMCPServer(config)
    return server, mock_cls


def _sse(inner=None, enabled=True):
    """Build an SSE-backed server with the standard config."""
    return _server("sse", inner or {"url": "http://x"}, enabled=enabled)


def _stdio(inner=None, spec=True):
    """Build a stdio-backed server whose blocking server is mocked."""
    from code_puppy.mcp_.blocking_startup import BlockingMCPServerStdio

    mock = MagicMock(spec=BlockingMCPServerStdio) if spec else MagicMock()
    with patch(STDIO, return_value=mock):
        server = ManagedMCPServer(
            ServerConfig(
                id="test-id",
                name="test-server",
                type="stdio",
                config=inner or {"command": "python"},
            )
        )
    return server, mock


# --- env-var expansion + tool prefixes ---


@pytest.mark.asyncio
async def test_managed_server_header_env_expansion_mocked():
    """Test that headers with env vars are expanded correctly (using mocks)."""

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
        patch(HTTP, return_value=mock_http_server) as mock_constructor,
    ):
        ManagedMCPServer(server_config)

        mock_constructor.assert_called_once()
        call_kwargs = mock_constructor.call_args.kwargs

        assert call_kwargs["headers"]["Authorization"] == "Bearer secret-123"
        assert call_kwargs["headers"]["X-Custom"] == "FixedValue"
        assert call_kwargs["url"] == "http://test.com"
        assert call_kwargs["tool_prefix"] == "test-server"


@pytest.mark.parametrize(
    "name,type,inner,target,prefix,env",
    [
        (
            "filesystem",
            "stdio",
            {"command": "python", "tool_prefix": "repo"},
            STDIO,
            "filesystem_repo",
            None,
        ),
        ("docs", "sse", {"url": "http://localhost:8080/sse"}, SSE, "docs", None),
        (
            "github",
            "http",
            {"url": "http://localhost:8080/mcp", "tool_prefix": "$MCP_SCOPE"},
            HTTP,
            "github_issues",
            {"MCP_SCOPE": "issues"},
        ),
    ],
)
def test_tool_prefix_nests_server_name(name, type, inner, target, prefix, env):
    """Configured MCP prefixes are nested under the server name."""
    config = ServerConfig(id="test-id", name=name, type=type, config=inner)
    with (
        patch.dict(os.environ, env or {}),
        patch(target) as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        ManagedMCPServer(config)
    assert mock_cls.call_args.kwargs["tool_prefix"] == prefix


@pytest.mark.parametrize(
    "value,expected",
    [
        ("$MY_VAR", "expanded_value"),
        ("${MY_VAR}", "expanded_value"),
        ("Bearer $MY_VAR", "Bearer expanded_value"),
        ("plain text", "plain text"),
        (
            {
                "Authorization": "Bearer $API_KEY",
                "Host": "$HOST",
                "Static": "no-change",
            },
            {
                "Authorization": "Bearer secret123",
                "Host": "example.com",
                "Static": "no-change",
            },
        ),
        (
            {"headers": {"Auth": "Bearer $KEY"}, "args": ["--key=$KEY"]},
            {"headers": {"Auth": "Bearer secret"}, "args": ["--key=secret"]},
        ),
        (["$ARG1", "static", "$ARG2"], ["value1", "static", "value2"]),
        (42, 42),
        (3.14, 3.14),
        (True, True),
        (None, None),
    ],
)
def test_expand_env_vars(value, expected):
    """Env var expansion handles strings, dicts, lists and non-strings."""
    with patch.dict(
        os.environ,
        {
            "MY_VAR": "expanded_value",
            "API_KEY": "secret123",
            "HOST": "example.com",
            "ARG1": "value1",
            "ARG2": "value2",
            "KEY": "secret",
        },
    ):
        assert _expand_env_vars(value) == expected


class TestManagedMCPServerEnableFromConfig:
    """ManagedMCPServer._enabled should be initialised from ServerConfig.enabled."""

    def _make_config(self, enabled: bool) -> ServerConfig:
        return ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            enabled=enabled,
            config={"command": "echo", "args": []},
        )

    def test_enabled_true_in_config_makes_server_enabled(self):
        server = ManagedMCPServer(self._make_config(enabled=True))
        assert server.is_enabled() is True

    def test_enabled_false_in_config_makes_server_disabled(self):
        server = ManagedMCPServer(self._make_config(enabled=False))
        assert server.is_enabled() is False

    def test_enabled_flag_and_tracker_state_are_independent(self):
        server = ManagedMCPServer(self._make_config(enabled=True))
        assert server.is_enabled() is True
        assert server._state == ServerState.STOPPED

    def test_enable_disable_still_work_as_runtime_overrides(self):
        server = ManagedMCPServer(self._make_config(enabled=False))
        assert server.is_enabled() is False
        server.enable()
        assert server.is_enabled() is True
        server.disable()
        assert server.is_enabled() is False


# --- process_tool_call (also touches get_banner_color + coerce guards) ---


class TestProcessToolCall:
    @pytest.mark.asyncio
    async def test_emits_info_and_calls_tool(self):
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

        mock_console.print.assert_called_once()
        assert "test_tool" in mock_console.print.call_args[0][0]
        mock_call_tool.assert_called_once_with(
            "test_tool", {"arg1": "value1"}, {"deps": mock_ctx.deps}
        )
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_with_empty_args(self):
        mock_ctx = Mock()
        mock_ctx.deps = None
        mock_call_tool = AsyncMock(return_value="result")

        with patch("rich.console.Console"):
            result = await process_tool_call(
                ctx=mock_ctx, call_tool=mock_call_tool, name="t", tool_args={}
            )

        mock_call_tool.assert_called_once_with("t", {}, {"deps": None})
        assert result == "result"


# --- init / get_pydantic_server ---


class TestManagedMCPServerInit:
    def test_init_handles_create_server_error(self):
        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="sse",
            config={"url": "http://localhost:8080"},
        )
        with patch(SSE, side_effect=Exception("Connection failed")):
            server = ManagedMCPServer(config)
        assert server._state == ServerState.ERROR
        assert server._error_message == "Connection failed"
        assert server._pydantic_server is None


class TestGetPydanticServer:
    def test_raises_when_server_is_none(self):
        server, _ = _server("sse", {"url": "http://localhost:8080"})
        server._pydantic_server = None
        with pytest.raises(RuntimeError, match="is not available"):
            server.get_pydantic_server()

    def test_raises_when_disabled(self):
        server, _ = _server("sse", {"url": "http://localhost:8080"})
        server._enabled = False
        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()

    def test_raises_when_quarantined(self):
        server, _ = _server("sse", {"url": "http://localhost:8080"})
        server.quarantine(3600)
        with pytest.raises(RuntimeError, match="disabled or quarantined"):
            server.get_pydantic_server()

    def test_returns_server_when_enabled(self):
        server, _ = _server("sse", {"url": "http://localhost:8080"})
        mock_pydantic = server._pydantic_server
        server.enable()
        assert server.get_pydantic_server() is mock_pydantic


# --- _create_server option handling ---


class TestCreateServerSSE:
    def test_requires_url(self):
        server = ManagedMCPServer(
            ServerConfig(id="test-id", name="test-server", type="sse", config={})
        )
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()

    @pytest.mark.parametrize(
        "inner,key,expected",
        [
            ({"url": "http://x", "timeout": 30}, "timeout", 30),
            ({"url": "http://x", "read_timeout": 120}, "read_timeout", 120),
        ],
    )
    def test_options_passed_through(self, inner, key, expected):
        _, mock_sse = _server("sse", inner)
        assert mock_sse.call_args.kwargs[key] == expected

    def test_explicit_http_client_passed_through(self):
        mock_client = MagicMock()
        _, mock_sse = _server("sse", {"url": "http://x", "http_client": mock_client})
        assert mock_sse.call_args.kwargs["http_client"] is mock_client

    def test_headers_create_http_client(self):
        mock_http_client = MagicMock()
        with (
            patch(SSE) as mock_sse,
            patch(
                "code_puppy.mcp_.managed_server.create_async_client",
                return_value=mock_http_client,
            ),
        ):
            mock_sse.return_value = MagicMock()
            ManagedMCPServer(
                ServerConfig(
                    id="test-id",
                    name="test-server",
                    type="sse",
                    config={
                        "url": "http://x",
                        "headers": {"Authorization": "Bearer t"},
                    },
                )
            )
        assert mock_sse.call_args.kwargs["http_client"] is mock_http_client


class TestCreateServerStdio:
    def test_requires_command(self):
        server = ManagedMCPServer(
            ServerConfig(id="test-id", name="test-server", type="stdio", config={})
        )
        assert server._state == ServerState.ERROR
        assert "command" in server._error_message.lower()

    @pytest.mark.parametrize(
        "inner,key,expected",
        [
            (
                {"command": "python", "args": "-m server --port 8080"},
                "args",
                ["-m", "server", "--port", "8080"],
            ),
            ({"command": "python", "args": ["-m", "server"]}, "args", ["-m", "server"]),
            (
                {"command": "python", "env": {"MY_VAR": "value"}},
                "env",
                {"MY_VAR": "value"},
            ),
            ({"command": "python", "cwd": "/some/path"}, "cwd", "/some/path"),
            ({"command": "python"}, "timeout", 60),
            ({"command": "python", "timeout": 120}, "timeout", 120),
            ({"command": "python", "read_timeout": 300}, "read_timeout", 300),
        ],
    )
    def test_options_passed_through(self, inner, key, expected):
        _, mock_stdio = _server("stdio", inner, patch_target=STDIO)
        assert mock_stdio.call_args.kwargs[key] == expected

    @staticmethod
    def _stdio_env(ca_bundle, inner_config):
        config = ServerConfig(
            id="test-id", name="test-server", type="stdio", config=inner_config
        )
        with (
            patch(
                "code_puppy.mcp_.managed_server.get_cert_bundle_path",
                return_value=ca_bundle,
            ),
            patch(STDIO) as mock_stdio,
        ):
            mock_stdio.return_value = MagicMock()
            ManagedMCPServer(config)
        return mock_stdio.call_args.kwargs["env"]

    def test_bundle_injected_when_resolved(self):
        env = self._stdio_env("/tmp/ca.pem", {"command": "uvx", "args": ["x"]})
        assert env["SSL_CERT_FILE"] == "/tmp/ca.pem"
        assert env["REQUESTS_CA_BUNDLE"] == "/tmp/ca.pem"

    def test_bundle_merges_with_config_env(self):
        env = self._stdio_env(
            "/tmp/ca.pem",
            {"command": "uvx", "args": ["x"], "env": {"MY_TOKEN": "secret"}},
        )
        assert env["MY_TOKEN"] == "secret"
        assert env["SSL_CERT_FILE"] == "/tmp/ca.pem"

    def test_config_env_pin_wins(self):
        env = self._stdio_env(
            "/tmp/ca.pem",
            {"command": "uvx", "args": ["x"], "env": {"SSL_CERT_FILE": "/pinned.pem"}},
        )
        assert env["SSL_CERT_FILE"] == "/pinned.pem"

    def test_no_bundle_leaves_env_untouched(self):
        assert self._stdio_env(None, {"command": "uvx", "args": ["x"]}) is None


class TestCreateServerHTTP:
    def test_requires_url(self):
        server = ManagedMCPServer(
            ServerConfig(id="test-id", name="test-server", type="http", config={})
        )
        assert server._state == ServerState.ERROR
        assert "url" in server._error_message.lower()

    @pytest.mark.parametrize(
        "inner,key,expected",
        [
            ({"url": "http://x", "timeout": 45}, "timeout", 45),
            ({"url": "http://x", "read_timeout": 200}, "read_timeout", 200),
        ],
    )
    def test_options_passed_through(self, inner, key, expected):
        _, mock_http = _server("http", inner, patch_target=HTTP)
        assert mock_http.call_args.kwargs[key] == expected


class TestCreateServerUnsupported:
    def test_unsupported_type_raises_error(self):
        server = ManagedMCPServer(
            ServerConfig(
                id="test-id",
                name="test-server",
                type="unknown",
                config={"url": "http://localhost:8080"},
            )
        )
        assert server._state == ServerState.ERROR
        assert "unsupported" in server._error_message.lower()


# --- _get_http_client / enable / disable / quarantine ---


class TestGetHttpClient:
    @pytest.mark.parametrize(
        "headers,expected_headers",
        [
            (
                {"Authorization": "Bearer $TEST_TOKEN"},
                {"Authorization": "Bearer secret123"},
            ),
            (
                {"X-Count": 42, "X-String": "value"},
                {"X-Count": 42, "X-String": "value"},
            ),
        ],
        ids=["expanded", "non-string-values"],
    )
    def test_creates_client_with_headers(self, headers, expected_headers):
        with (
            patch.dict(os.environ, {"TEST_TOKEN": "secret123"}),
            patch(SSE) as mock_sse,
            patch("code_puppy.mcp_.managed_server.create_async_client") as mock_create,
        ):
            mock_sse.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            server = ManagedMCPServer(
                ServerConfig(
                    id="test-id",
                    name="test-server",
                    type="sse",
                    config={"url": "http://x", "headers": headers},
                )
            )
            server._get_http_client()
        assert mock_create.call_args.kwargs["headers"] == expected_headers

    def test_creates_client_with_custom_timeout(self):
        with (
            patch(SSE) as mock_sse,
            patch("code_puppy.mcp_.managed_server.create_async_client") as mock_create,
        ):
            mock_sse.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            server = ManagedMCPServer(
                ServerConfig(
                    id="test-id",
                    name="test-server",
                    type="sse",
                    config={"url": "http://x", "headers": {}, "timeout": 60},
                )
            )
            server._get_http_client()
        assert mock_create.call_args.kwargs["timeout"] == 60


class TestQuarantine:
    def test_quarantine_sets_state(self):
        server, _ = _sse()
        server.enable()
        server.quarantine(3600)
        assert server._state == ServerState.QUARANTINED
        assert server.is_quarantined() is True

    def test_is_quarantined_when_not_quarantined(self):
        server, _ = _sse()
        assert server.is_quarantined() is False

    def test_quarantine_expires(self):
        server, _ = _sse()
        server.enable()
        server._quarantine_until = datetime.now() - timedelta(seconds=1)
        server._state = ServerState.QUARANTINED
        assert server.is_quarantined() is False
        assert server._quarantine_until is None
        assert server._state == ServerState.RUNNING

    def test_quarantine_expires_to_stopped_when_disabled(self):
        server, _ = _sse(enabled=False)
        server._quarantine_until = datetime.now() - timedelta(seconds=1)
        server._state = ServerState.QUARANTINED
        assert server.is_quarantined() is False
        assert server._state == ServerState.STOPPED


# --- stderr / ready / status ---


class TestGetCapturedStderr:
    def test_returns_empty_for_non_stdio_server(self):
        server, _ = _sse()
        assert server.get_captured_stderr() == []

    def test_returns_stderr_for_stdio_server(self):
        server, mock_stdio = _stdio()
        mock_stdio.get_captured_stderr.return_value = ["error line 1", "error line 2"]
        assert server.get_captured_stderr() == ["error line 1", "error line 2"]


class TestWaitUntilReady:
    @pytest.mark.asyncio
    async def test_non_stdio_returns_true_immediately(self):
        server, _ = _sse()
        assert await server.wait_until_ready() is True

    @pytest.mark.asyncio
    async def test_stdio_waits_for_ready(self):
        server, mock_stdio = _stdio()
        mock_stdio.wait_until_ready = AsyncMock()
        assert await server.wait_until_ready(timeout=10.0) is True
        mock_stdio.wait_until_ready.assert_called_once_with(10.0)

    @pytest.mark.asyncio
    async def test_stdio_returns_false_on_exception(self):
        server, mock_stdio = _stdio()
        mock_stdio.wait_until_ready = AsyncMock(side_effect=Exception("Timeout"))
        assert await server.wait_until_ready() is False


class TestEnsureReady:
    @pytest.mark.asyncio
    async def test_non_stdio_does_nothing(self):
        server, _ = _sse()
        await server.ensure_ready()

    @pytest.mark.asyncio
    async def test_stdio_calls_ensure_ready(self):
        server, mock_stdio = _stdio()
        mock_stdio.ensure_ready = AsyncMock()
        await server.ensure_ready(timeout=15.0)
        mock_stdio.ensure_ready.assert_called_once_with(15.0)


class TestGetStatus:
    def test_returns_complete_status(self):
        server, _ = _sse(enabled=False)
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
        server, _ = _sse()
        server.enable()
        status = server.get_status()
        assert status["state"] == "running"
        assert status["enabled"] is True
        assert status["uptime_seconds"] is not None
        assert status["start_time"] is not None
        assert status["server_available"] is True

    def test_status_with_quarantined_server(self):
        server, _ = _sse()
        server.enable()
        server.quarantine(3600)
        status = server.get_status()
        assert status["state"] == "quarantined"
        assert status["quarantined"] is True
        assert status["quarantine_remaining_seconds"] is not None
        assert status["quarantine_remaining_seconds"] > 0
        assert status["server_available"] is False

    def test_status_with_error_server(self):
        server = ManagedMCPServer(
            ServerConfig(id="test-id", name="test-server", type="sse", config={})
        )
        status = server.get_status()
        assert status["state"] == "error"
        assert status["error_message"] is not None
        assert status["server_available"] is False

    def test_status_config_is_copy(self):
        server, _ = _sse()
        status = server.get_status()
        status["config"]["url"] = "modified"
        assert server.config.config["url"] == "http://x"
