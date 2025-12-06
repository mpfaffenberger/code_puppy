"""Tests for the ACP (Agent Client Protocol) module.

These tests verify the JSON-RPC transport layer and handlers work correctly.
"""

import pytest

from code_puppy.acp.handlers import (
    PROTOCOL_VERSION,
    handle_initialize,
    handle_session_new,
)
from code_puppy.acp.main import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    NOT_INITIALIZED,
    PARSE_ERROR,
    ACPDispatcher,
    ACPTransport,
)
from code_puppy.acp.state import (
    create_session,
    get_session,
    get_state,
    remove_session,
    reset_state,
)


class TestACPState:
    """Tests for the ACP state management module."""

    def setup_method(self):
        """Reset state before each test."""
        reset_state()

    def test_get_state_creates_singleton(self):
        """get_state() should return the same instance on repeated calls."""
        state1 = get_state()
        state2 = get_state()
        assert state1 is state2

    def test_initial_state(self):
        """Initial state should have expected defaults."""
        state = get_state()
        assert state.initialized is False
        assert state.protocol_version == 1
        assert state.client_capabilities == {}
        assert state.sessions == {}

    def test_reset_state(self):
        """reset_state() should clear the singleton."""
        state1 = get_state()
        state1.initialized = True
        reset_state()
        state2 = get_state()
        assert state2.initialized is False
        assert state1 is not state2

    def test_create_session(self):
        """create_session() should add a session to state."""
        session = create_session("test-session", "/home/user/project")
        assert session.session_id == "test-session"
        assert session.cwd == "/home/user/project"
        assert session.agent_name == "code-puppy"
        assert session.message_history == []

        # Should be in state
        state = get_state()
        assert "test-session" in state.sessions

    def test_get_session(self):
        """get_session() should return session by ID."""
        create_session("my-session", "/tmp")
        session = get_session("my-session")
        assert session is not None
        assert session.session_id == "my-session"

    def test_get_session_not_found(self):
        """get_session() should return None for unknown session."""
        session = get_session("nonexistent")
        assert session is None

    def test_remove_session(self):
        """remove_session() should remove a session from state."""
        create_session("to-remove", "/tmp")
        assert get_session("to-remove") is not None

        result = remove_session("to-remove")
        assert result is True
        assert get_session("to-remove") is None

    def test_remove_session_not_found(self):
        """remove_session() should return False for unknown session."""
        result = remove_session("nonexistent")
        assert result is False


class TestACPHandlers:
    """Tests for ACP method handlers."""

    def setup_method(self):
        """Reset state before each test."""
        reset_state()

    @pytest.mark.asyncio
    async def test_handle_initialize(self):
        """initialize handler should negotiate protocol and set state."""
        params = {
            "protocolVersion": 1,
            "clientCapabilities": {"someFeature": True},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }

        result = await handle_initialize(params)

        # Check response structure
        assert result["protocolVersion"] == 1
        assert "agentCapabilities" in result
        assert "agentInfo" in result
        assert result["agentInfo"]["name"] == "code-puppy"
        assert "authMethods" in result

        # Check state was updated
        state = get_state()
        assert state.initialized is True
        assert state.client_capabilities == {"someFeature": True}

    @pytest.mark.asyncio
    async def test_handle_initialize_version_negotiation(self):
        """initialize should negotiate to minimum protocol version."""
        # Client supports version 5, we support 1, should negotiate to 1
        params = {"protocolVersion": 5}
        result = await handle_initialize(params)
        assert result["protocolVersion"] == min(5, PROTOCOL_VERSION)

    @pytest.mark.asyncio
    async def test_handle_session_new(self):
        """session/new handler should create a session."""
        params = {
            "sessionId": "new-session",
            "cwd": "/home/user/myproject",
        }

        # Create a mock send_notification callback
        notifications = []

        async def mock_send_notification(method, params):
            notifications.append((method, params))

        result = await handle_session_new(params, mock_send_notification)

        # Should return empty dict on success
        assert result == {}

        # Session should exist
        session = get_session("new-session")
        assert session is not None
        assert session.cwd == "/home/user/myproject"

        # Should have sent available_commands notification
        assert len(notifications) > 0
        assert notifications[0][0] == "session/update"

    @pytest.mark.asyncio
    async def test_handle_session_new_with_mcp_servers(self):
        """session/new should store MCP server configs."""
        params = {
            "sessionId": "mcp-session",
            "cwd": "/tmp",
            "mcpServers": [{"name": "test-server", "command": "test"}],
        }

        # Create a mock send_notification callback
        async def mock_send_notification(method, params):
            pass

        await handle_session_new(params, mock_send_notification)

        session = get_session("mcp-session")
        assert session.mcp_servers == [{"name": "test-server", "command": "test"}]


class TestACPDispatcher:
    """Tests for the ACP message dispatcher."""

    def setup_method(self):
        """Reset state before each test."""
        reset_state()

    @pytest.mark.asyncio
    async def test_dispatch_requires_jsonrpc_version(self):
        """Dispatcher should reject messages without jsonrpc: 2.0."""
        transport = ACPTransport()
        dispatcher = ACPDispatcher(transport)

        sent_messages = []

        async def capture_message(msg):
            sent_messages.append(msg)

        transport.write_message = capture_message

        # Missing jsonrpc field
        await dispatcher.dispatch({"id": 1, "method": "initialize"})

        assert len(sent_messages) == 1
        assert "error" in sent_messages[0]
        assert sent_messages[0]["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_dispatch_requires_method(self):
        """Dispatcher should reject messages without method."""
        transport = ACPTransport()
        dispatcher = ACPDispatcher(transport)

        sent_messages = []

        async def capture_message(msg):
            sent_messages.append(msg)

        transport.write_message = capture_message

        # Missing method field
        await dispatcher.dispatch({"jsonrpc": "2.0", "id": 1})

        assert len(sent_messages) == 1
        assert "error" in sent_messages[0]
        assert sent_messages[0]["error"]["code"] == INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_dispatch_rejects_uninitialized(self):
        """Dispatcher should reject non-initialize methods before init."""
        transport = ACPTransport()
        dispatcher = ACPDispatcher(transport)

        sent_messages = []

        async def capture_message(msg):
            sent_messages.append(msg)

        transport.write_message = capture_message

        # Try session/new before initialize
        await dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "session/new",
                "params": {"sessionId": "test", "cwd": "/tmp"},
            }
        )

        assert len(sent_messages) == 1
        assert "error" in sent_messages[0]
        assert sent_messages[0]["error"]["code"] == NOT_INITIALIZED

    @pytest.mark.asyncio
    async def test_dispatch_initialize_success(self):
        """Dispatcher should handle initialize correctly."""
        transport = ACPTransport()
        dispatcher = ACPDispatcher(transport)

        sent_messages = []

        async def capture_message(msg):
            sent_messages.append(msg)

        transport.write_message = capture_message

        await dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": 1},
            }
        )

        assert len(sent_messages) == 1
        assert "result" in sent_messages[0]
        assert sent_messages[0]["id"] == 1
        assert sent_messages[0]["result"]["protocolVersion"] == 1

    @pytest.mark.asyncio
    async def test_dispatch_unknown_method(self):
        """Dispatcher should return METHOD_NOT_FOUND for unknown methods."""
        transport = ACPTransport()
        dispatcher = ACPDispatcher(transport)

        sent_messages = []

        async def capture_message(msg):
            sent_messages.append(msg)

        transport.write_message = capture_message

        # First initialize
        await dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": 1},
            }
        )

        # Then try unknown method
        await dispatcher.dispatch(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "unknown/method",
                "params": {},
            }
        )

        assert len(sent_messages) == 2
        assert "error" in sent_messages[1]
        assert sent_messages[1]["error"]["code"] == METHOD_NOT_FOUND


class TestJSONRPCErrorCodes:
    """Verify JSON-RPC error codes are correct per spec."""

    def test_parse_error_code(self):
        assert PARSE_ERROR == -32700

    def test_invalid_request_code(self):
        assert INVALID_REQUEST == -32600

    def test_method_not_found_code(self):
        assert METHOD_NOT_FOUND == -32601

    def test_invalid_params_code(self):
        assert INVALID_PARAMS == -32602

    def test_not_initialized_is_application_error(self):
        # Application-defined server errors are in range -32000 to -32099
        # (per JSON-RPC 2.0 spec, reserved for implementation-defined errors)
        assert -32099 <= NOT_INITIALIZED <= -32000
