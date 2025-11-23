"""
Shared fixtures and utilities for MCP command tests.

Provides common mocks and test infrastructure to avoid duplication
across MCP command test files.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import pytest

from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig, ServerState


@dataclass
class MockServerInfo:
    """Mock server information for testing."""

    id: str
    name: str
    type: str = "stdio"
    enabled: bool = True
    state: ServerState = ServerState.STOPPED
    error_message: Optional[str] = None
    quarantined: bool = False
    uptime_seconds: float = 0.0


class MockMCPManager:
    """Mock MCP manager for testing."""

    def __init__(self):
        self.servers: Dict[str, MockServerInfo] = {}
        self.call_history = []
        # Make these Mock methods for proper testing
        self.list_servers = Mock()
        self.get_server_status = Mock()

    def add_mock_server(self, server_info: MockServerInfo):
        """Add a mock server to the manager."""
        self.servers[server_info.id] = server_info
        # Update the list_servers return value when servers change
        self._update_list_servers_return()

    def _update_list_servers_return(self):
        """Update the list_servers mock return value based on current servers."""
        servers = []
        for server_info in self.servers.values():
            mock_server = Mock(spec=ManagedMCPServer)
            mock_server.id = server_info.id
            mock_server.name = server_info.name
            mock_server.type = server_info.type
            mock_server.enabled = server_info.enabled
            mock_server.state = server_info.state
            mock_server.error_message = server_info.error_message
            mock_server.quarantined = server_info.quarantined
            mock_server.uptime_seconds = server_info.uptime_seconds
            servers.append(mock_server)
        self.list_servers.return_value = servers

    def _get_server_status_impl(self, server_id: str) -> Dict[str, Any]:
        """Get detailed status for a server."""
        if server_id not in self.servers:
            return {"exists": False}

        server_info = self.servers[server_id]
        return {
            "exists": True,
            "id": server_id,
            "type": server_info.type,
            "state": server_info.state.value,
            "enabled": server_info.enabled,
            "error_message": server_info.error_message,
            "quarantined": server_info.quarantined,
            "tracker_uptime": server_info.uptime_seconds,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

    def get_server_status(self, server_id: str) -> Dict[str, Any]:
        """Mock wrapper that delegates to the real implementation."""
        return self._get_server_status_impl(server_id)

    def start_server_sync(self, server_id: str) -> bool:
        """Mock start server."""
        self.call_history.append(f"start_{server_id}")
        if server_id in self.servers:
            self.servers[server_id].enabled = True
            self.servers[server_id].state = ServerState.RUNNING
            return True
        return False

    def stop_server_sync(self, server_id: str) -> bool:
        """Mock stop server."""
        self.call_history.append(f"stop_{server_id}")
        if server_id in self.servers:
            self.servers[server_id].enabled = False
            self.servers[server_id].state = ServerState.STOPPED
            return True
        return False

    def reload_server(self, server_id: str) -> bool:
        """Mock reload server."""
        self.call_history.append(f"reload_{server_id}")
        return server_id in self.servers

    def register_server(self, config: ServerConfig) -> Optional[str]:
        """Mock register server."""
        self.call_history.append("register_server")
        return config.id


@pytest.fixture
def mock_mcp_manager():
    """Provide a mock MCP manager for testing."""
    manager = MockMCPManager()

    # Add some default test servers
    manager.add_mock_server(
        MockServerInfo(
            id="test-server-1", name="test-server", state=ServerState.STOPPED
        )
    )
    manager.add_mock_server(
        MockServerInfo(
            id="test-server-2",
            name="another-server",
            state=ServerState.RUNNING,
            enabled=True,
        )
    )
    manager.add_mock_server(
        MockServerInfo(
            id="failed-server",
            name="failed-server",
            state=ServerState.ERROR,
            error_message="Connection failed",
            enabled=False,
        )
    )

    return manager


@pytest.fixture
def mock_emit_info():
    """Mock emit_info function."""
    messages = []

    def capture(message, message_group=None):
        messages.append((message, message_group))

    # Create patches for each module
    patches = [
        patch(
            "code_puppy.command_line.mcp.start_command.emit_info", side_effect=capture
        ),
        patch(
            "code_puppy.command_line.mcp.stop_command.emit_info", side_effect=capture
        ),
        patch(
            "code_puppy.command_line.mcp.restart_command.emit_info", side_effect=capture
        ),
        patch(
            "code_puppy.command_line.mcp.list_command.emit_info", side_effect=capture
        ),
        patch(
            "code_puppy.command_line.mcp.search_command.emit_info", side_effect=capture
        ),
        patch(
            "code_puppy.command_line.mcp.status_command.emit_info", side_effect=capture
        ),
    ]

    # Start all patches
    for p in patches:
        p.start()

    try:
        # Create mock objects with shared messages list
        mock_start = patches[0]
        mock_stop = patches[1]
        mock_restart = patches[2]
        mock_list = patches[3]
        mock_search = patches[4]
        mock_status = patches[5]

        # All mocks share the same messages list
        mock_start.messages = messages
        mock_stop.messages = messages
        mock_restart.messages = messages
        mock_list.messages = messages
        mock_search.messages = messages
        mock_status.messages = messages

        # Return any one of them since they all share the same messages
        yield mock_start
    finally:
        # Stop all patches
        for p in patches:
            p.stop()


@pytest.fixture
def mock_emit_prompt():
    """Mock emit_prompt function."""
    responses = []

    def capture_response(prompt):
        if responses:
            return responses.pop(0)
        return "test-response"

    with patch(
        "code_puppy.messaging.emit_prompt", side_effect=capture_response
    ) as mock:
        mock.set_responses = lambda resp_list: responses.extend(resp_list)
        yield mock


@pytest.fixture
def mock_tui_mode():
    """Mock TUI mode state."""
    with patch("code_puppy.tui_state.is_tui_mode") as mock:
        mock.return_value = False
        yield mock


@pytest.fixture
def mock_get_current_agent():
    """Mock get_current_agent function."""
    mock_agent = Mock()
    mock_agent.reload_code_generation_agent = Mock()

    with patch("code_puppy.agents.get_current_agent", return_value=mock_agent) as mock:
        mock.agent = mock_agent
        yield mock


@pytest.fixture
def mock_reload_mcp_servers():
    """Mock reload_mcp_servers function."""
    with patch("code_puppy.agent.reload_mcp_servers") as mock:
        yield mock


@pytest.fixture
def mock_server_catalog():
    """Mock server registry catalog."""
    mock_server = Mock()
    mock_server.id = "test-server-id"
    mock_server.name = "test-server"
    mock_server.display_name = "Test Server"
    mock_server.description = "A test server for unit testing"
    mock_server.category = "test"
    mock_server.tags = ["test", "mock"]
    mock_server.verified = True
    mock_server.popular = False
    mock_server.get_environment_vars.return_value = ["TEST_VAR"]
    mock_server.get_command_line_args.return_value = []

    mock_catalog = Mock()
    mock_catalog.get_by_id.return_value = mock_server
    mock_catalog.search.return_value = [mock_server]
    mock_catalog.get_popular.return_value = [mock_server]

    with patch("code_puppy.mcp_.server_registry_catalog.catalog", mock_catalog):
        yield mock_catalog


@pytest.fixture
def temp_mcp_servers_file():
    """Provide a temporary mcp_servers.json file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"mcp_servers": {}}, f)
        temp_path = f.name

    try:
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest.fixture
def mock_mcp_servers_file(temp_mcp_servers_file):
    """Mock MCP_SERVERS_FILE to use temporary file."""
    with patch("code_puppy.config.MCP_SERVERS_FILE", temp_mcp_servers_file):
        yield temp_mcp_servers_file


@pytest.fixture(autouse=True)
def mock_get_mcp_manager(mock_mcp_manager):
    """Automatically mock get_mcp_manager for all MCP tests."""
    # Patch where get_mcp_manager is USED (in base.py), not where it's defined
    with patch(
        "code_puppy.command_line.mcp.base.get_mcp_manager",
        return_value=mock_mcp_manager,
    ):
        yield mock_mcp_manager


@pytest.fixture
def sample_json_config():
    """Sample valid JSON configuration for testing."""
    return {
        "name": "test-server",
        "type": "stdio",
        "command": "echo",
        "args": ["hello"],
        "env": {"TEST": "value"},
    }


@pytest.fixture
def mock_async_lifecycle():
    """Mock async lifecycle manager."""
    mock_lifecycle = Mock()
    mock_lifecycle.is_running.return_value = True

    with patch(
        "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager",
        return_value=mock_lifecycle,
    ):
        yield mock_lifecycle
