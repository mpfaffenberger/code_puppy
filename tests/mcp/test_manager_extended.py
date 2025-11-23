"""
Extended tests for MCPManager - comprehensive testing of core functionality.

Tests focus on:
- Server registration and management
- get_mcp_manager() singleton pattern
- Server lifecycle (start/stop)
- Error handling for server failures

Uses simple mocking to keep tests focused and maintainable.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig, ServerState
from code_puppy.mcp_.manager import MCPManager, ServerInfo, get_mcp_manager


class TestMCPManagerExtended:
    """Extended tests for MCPManager functionality."""

    def setup_method(self):
        """Set up fresh manager for each test."""
        # Reset singleton to ensure clean state
        import code_puppy.mcp_.manager

        code_puppy.mcp_.manager._manager_instance = None

    def test_get_mcp_manager_singleton(self):
        """Test singleton pattern - same instance returned."""
        # Reset singleton first
        import code_puppy.mcp_.manager

        code_puppy.mcp_.manager._manager_instance = None

        mgr1 = get_mcp_manager()
        mgr2 = get_mcp_manager()
        mgr3 = MCPManager()

        # First two should be same (singleton)
        assert mgr1 is mgr2
        # Third should be different (new instance)
        assert mgr1 is not mgr3

        # All should be MCPManager instances
        assert isinstance(mgr1, MCPManager)
        assert isinstance(mgr2, MCPManager)
        assert isinstance(mgr3, MCPManager)

    def test_register_server_success(self):
        """Test successful server registration."""
        manager = MCPManager()

        # Mock the registry to avoid actual file operations
        with patch.object(manager.registry, "register", return_value="test-server-id"):
            config = ServerConfig(
                id="",  # Will be auto-generated
                name="test-server",
                type="stdio",
                config={"command": "echo", "args": ["hello"]},
            )

            server_id = manager.register_server(config)

            assert server_id == "test-server-id"
            assert server_id in manager._managed_servers
            assert isinstance(manager._managed_servers[server_id], ManagedMCPServer)

    def test_register_server_failure_cleanup(self):
        """Test that failed registration cleans up properly."""
        manager = MCPManager()

        # Mock registry to register but then fail on server creation
        with (
            patch.object(
                manager.registry, "register", return_value="test-server-id"
            ) as mock_register,
            patch.object(manager.registry, "unregister") as mock_unregister,
        ):
            # Make ManagedMCPServer creation fail
            with patch(
                "code_puppy.mcp_.manager.ManagedMCPServer",
                side_effect=Exception("Creation failed"),
            ):
                config = ServerConfig(
                    id="", name="test-server", type="stdio", config={"command": "echo"}
                )

                with pytest.raises(Exception, match="Creation failed"):
                    manager.register_server(config)

                # Should have registered then unregistered due to failure
                mock_register.assert_called_once()
                mock_unregister.assert_called_once_with("test-server-id")

                # No managed server should exist
                assert "test-server-id" not in manager._managed_servers

    def test_get_server_by_name(self):
        """Test retrieving server by name."""
        manager = MCPManager()

        # Mock registry response
        expected_config = ServerConfig(
            id="test-id", name="test-server", type="stdio", config={"command": "echo"}
        )

        with patch.object(
            manager.registry, "get_by_name", return_value=expected_config
        ):
            result = manager.get_server_by_name("test-server")

            assert result is expected_config
            assert result.name == "test-server"

    def test_get_server_by_name_not_found(self):
        """Test retrieving non-existent server by name."""
        manager = MCPManager()

        with patch.object(manager.registry, "get_by_name", return_value=None):
            result = manager.get_server_by_name("non-existent")

            assert result is None

    def test_update_server_success(self):
        """Test successful server update."""
        manager = MCPManager()

        # Mock registry update
        with patch.object(manager.registry, "update", return_value=True):
            new_config = ServerConfig(
                id="test-id",
                name="updated-server",
                type="stdio",
                config={"command": "echo", "args": ["updated"]},
            )

            result = manager.update_server("test-id", new_config)

            assert result is True

    def test_update_server_not_found(self):
        """Test updating non-existent server."""
        manager = MCPManager()

        with patch.object(manager.registry, "update", return_value=False):
            config = ServerConfig(
                id="non-existent", name="test", type="stdio", config={}
            )

            result = manager.update_server("non-existent", config)

            assert result is False

    def test_get_servers_for_agent_success(self):
        """Test getting servers for agent use - only enabled and non-quarantined."""
        manager = MCPManager()

        # Create mock servers with different states
        mock_server_enabled = Mock()
        mock_server_enabled.is_enabled.return_value = True
        mock_server_enabled.is_quarantined.return_value = False
        mock_server_enabled.get_pydantic_server.return_value = Mock()
        mock_server_enabled.config = Mock()
        mock_server_enabled.config.name = "enabled-server"

        mock_server_disabled = Mock()
        mock_server_disabled.is_enabled.return_value = False
        mock_server_disabled.is_quarantined.return_value = False
        mock_server_disabled.config = Mock()
        mock_server_disabled.config.name = "disabled-server"

        mock_server_quarantined = Mock()
        mock_server_quarantined.is_enabled.return_value = True
        mock_server_quarantined.is_quarantined.return_value = True
        mock_server_quarantined.config = Mock()
        mock_server_quarantined.config.name = "quarantined-server"

        # Add servers to manager
        manager._managed_servers = {
            "enabled": mock_server_enabled,
            "disabled": mock_server_disabled,
            "quarantined": mock_server_quarantined,
        }

        servers = manager.get_servers_for_agent()

        # Should only return enabled, non-quarantined servers
        assert len(servers) == 1
        mock_server_enabled.get_pydantic_server.assert_called_once()
        mock_server_disabled.get_pydantic_server.assert_not_called()
        mock_server_quarantined.get_pydantic_server.assert_not_called()

    def test_get_servers_for_agent_handles_errors(self):
        """Test that errors in getting servers don't crash the method."""
        manager = MCPManager()

        # Create one good server and one that throws errors
        mock_server_good = Mock()
        mock_server_good.is_enabled.return_value = True
        mock_server_good.is_quarantined.return_value = False
        mock_server_good.get_pydantic_server.return_value = Mock()
        mock_server_good.config = Mock()
        mock_server_good.config.name = "good-server"

        mock_server_bad = Mock()
        mock_server_bad.is_enabled.return_value = True
        mock_server_bad.is_quarantined.return_value = False
        mock_server_bad.get_pydantic_server.side_effect = Exception("Server error")
        mock_server_bad.config = Mock()
        mock_server_bad.config.name = "bad-server"

        manager._managed_servers = {
            "good": mock_server_good,
            "bad": mock_server_bad,
        }

        # Mock status tracker to record error
        with patch.object(manager.status_tracker, "record_event"):
            servers = manager.get_servers_for_agent()

            # Should still return the good server despite the bad one failing
            assert len(servers) == 1

            # Error should be recorded
            manager.status_tracker.record_event.assert_called_once_with(
                "bad",
                "agent_access_error",
                {
                    "error": "Server error",
                    "message": "Error accessing server for agent: Server error",
                },
            )

    @pytest.mark.asyncio
    async def test_start_server_success(self):
        """Test successful server start."""
        manager = MCPManager()

        # Create mock server
        mock_server = Mock()
        mock_server.enable = Mock()
        mock_server.config = Mock()
        mock_server.config.name = "test-server"

        manager._managed_servers = {"test-id": mock_server}

        # Mock lifecycle manager
        mock_lifecycle = AsyncMock()
        mock_lifecycle.start_server.return_value = True

        with (
            patch(
                "code_puppy.mcp_.manager.get_lifecycle_manager",
                return_value=mock_lifecycle,
            ),
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(
                manager.status_tracker, "record_start_time"
            ) as mock_record_start,
            patch.object(manager.status_tracker, "record_event"),
        ):
            result = await manager.start_server("test-id")

            assert result is True
            mock_server.enable.assert_called_once()
            mock_set_status.assert_called_once_with("test-id", ServerState.RUNNING)
            mock_record_start.assert_called_once_with("test-id")
            mock_lifecycle.start_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_server_not_found(self):
        """Test starting non-existent server."""
        manager = MCPManager()

        result = await manager.start_server("non-existent")

        assert result is False

    @pytest.mark.asyncio
    async def test_start_server_handles_lifecycle_failure(self):
        """Test that lifecycle manager failure doesn't prevent server enable."""
        manager = MCPManager()

        mock_server = Mock()
        mock_server.enable = Mock()
        mock_server.config = Mock()
        mock_server.config.name = "test-server"

        manager._managed_servers = {"test-id": mock_server}

        # Mock lifecycle manager to fail
        mock_lifecycle = AsyncMock()
        mock_lifecycle.start_server.side_effect = Exception("Lifecycle failed")

        with (
            patch(
                "code_puppy.mcp_.manager.get_lifecycle_manager",
                return_value=mock_lifecycle,
            ),
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(manager.status_tracker, "record_start_time"),
        ):
            result = await manager.start_server("test-id")

            # Should still succeed (server enabled even if process start failed)
            assert result is True
            mock_server.enable.assert_called_once()
            mock_set_status.assert_called_once_with("test-id", ServerState.RUNNING)

    def test_start_server_sync_success(self):
        """Test synchronous server start."""
        manager = MCPManager()

        mock_server = Mock()
        mock_server.enable = Mock()
        mock_server.config = Mock()
        mock_server.config.name = "test-server"

        manager._managed_servers = {"test-id": mock_server}

        with (
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(
                manager.status_tracker, "record_start_time"
            ) as mock_record_start,
        ):
            result = manager.start_server_sync("test-id")

            assert result is True
            mock_server.enable.assert_called_once()
            mock_set_status.assert_called_once_with("test-id", ServerState.RUNNING)
            mock_record_start.assert_called_once_with("test-id")

    @pytest.mark.asyncio
    async def test_stop_server_success(self):
        """Test successful server stop."""
        manager = MCPManager()

        mock_server = Mock()
        mock_server.disable = Mock()
        mock_server.config = Mock()
        mock_server.config.name = "test-server"

        manager._managed_servers = {"test-id": mock_server}

        # Mock lifecycle manager
        mock_lifecycle = AsyncMock()
        mock_lifecycle.stop_server.return_value = True

        with (
            patch(
                "code_puppy.mcp_.manager.get_lifecycle_manager",
                return_value=mock_lifecycle,
            ),
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(
                manager.status_tracker, "record_stop_time"
            ) as mock_record_stop,
        ):
            result = await manager.stop_server("test-id")

            assert result is True
            mock_server.disable.assert_called_once()
            mock_set_status.assert_called_once_with("test-id", ServerState.STOPPED)
            mock_record_stop.assert_called_once_with("test-id")
            mock_lifecycle.stop_server.assert_called_once()

    def test_stop_server_sync_success(self):
        """Test synchronous server stop."""
        manager = MCPManager()

        mock_server = Mock()
        mock_server.disable = Mock()
        mock_server.config = Mock()
        mock_server.config.name = "test-server"

        manager._managed_servers = {"test-id": mock_server}

        with (
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(
                manager.status_tracker, "record_stop_time"
            ) as mock_record_stop,
        ):
            result = manager.stop_server_sync("test-id")

            assert result is True
            mock_server.disable.assert_called_once()
            mock_set_status.assert_called_once_with("test-id", ServerState.STOPPED)
            mock_record_stop.assert_called_once_with("test-id")

    def test_reload_server_success(self):
        """Test successful server reload."""
        manager = MCPManager()

        # Mock existing server
        old_server = Mock()
        old_server.config = Mock()
        old_server.config.name = "old-server"
        manager._managed_servers = {"test-id": old_server}

        # Mock registry config
        config = ServerConfig(
            id="test-id",
            name="reloaded-server",
            type="stdio",
            config={"command": "echo"},
        )

        with (
            patch.object(manager.registry, "get", return_value=config),
            patch("code_puppy.mcp_.manager.ManagedMCPServer") as mock_managed_class,
            patch.object(manager.status_tracker, "set_status") as mock_set_status,
            patch.object(manager.status_tracker, "record_event"),
        ):
            new_mock_server = Mock()
            mock_managed_class.return_value = new_mock_server

            result = manager.reload_server("test-id")

            assert result is True
            # Old server should be removed, new one added
            assert manager._managed_servers["test-id"] is new_mock_server
            mock_set_status.assert_called_once_with("test-id", ServerState.STOPPED)

    def test_reload_server_not_found(self):
        """Test reloading non-existent server."""
        manager = MCPManager()

        with patch.object(manager.registry, "get", return_value=None):
            result = manager.reload_server("non-existent")

            assert result is False

    def test_remove_server_success(self):
        """Test successful server removal."""
        manager = MCPManager()

        # Add server to managed servers
        mock_server = Mock()
        manager._managed_servers = {"test-id": mock_server}

        # Mock registry
        config = ServerConfig(id="test-id", name="test-server", type="stdio", config={})

        with (
            patch.object(manager.registry, "get", return_value=config),
            patch.object(
                manager.registry, "unregister", return_value=True
            ) as mock_unregister,
            patch.object(manager.status_tracker, "record_event") as mock_record_event,
        ):
            result = manager.remove_server("test-id")

            assert result is True
            assert "test-id" not in manager._managed_servers
            mock_unregister.assert_called_once_with("test-id")
            mock_record_event.assert_called_once_with(
                "test-id", "removed", {"message": "Server removed"}
            )

    def test_remove_server_not_found(self):
        """Test removing non-existent server."""
        manager = MCPManager()

        with (
            patch.object(manager.registry, "get", return_value=None),
            patch.object(manager.registry, "unregister", return_value=False),
        ):
            result = manager.remove_server("non-existent")

            assert result is False

    def test_get_server_status_success(self):
        """Test getting comprehensive server status."""
        manager = MCPManager()

        # Mock server
        mock_server = Mock()
        mock_server.get_status.return_value = {
            "id": "test-id",
            "name": "test-server",
            "state": "running",
            "enabled": True,
        }

        manager._managed_servers = {"test-id": mock_server}

        # Mock status tracker
        with (
            patch.object(
                manager.status_tracker,
                "get_server_summary",
                return_value={
                    "state": "running",
                    "metadata": {"test": "value"},
                    "recent_events_count": 5,
                    "uptime": timedelta(hours=1),
                    "last_event_time": datetime.now(),
                },
            ),
            patch.object(manager.status_tracker, "get_events", return_value=[]),
        ):
            status = manager.get_server_status("test-id")

            assert status["id"] == "test-id"
            assert status["name"] == "test-server"
            assert status["tracker_state"] == "running"
            assert status["recent_events_count"] == 5

    def test_get_server_status_not_found(self):
        """Test getting status for non-existent server."""
        manager = MCPManager()

        status = manager.get_server_status("non-existent")

        assert status["exists"] is False
        assert "error" in status

    def test_list_servers_success(self):
        """Test listing all servers with their info."""
        manager = MCPManager()

        # Create mock servers
        mock_server1 = Mock()
        mock_server1.get_status.return_value = {
            "state": "running",
            "error_message": None,
        }
        mock_server1.config = Mock()
        mock_server1.config.name = "server1"
        mock_server1.config.type = "stdio"
        mock_server1.is_enabled.return_value = True
        mock_server1.is_quarantined.return_value = False

        mock_server2 = Mock()
        mock_server2.get_status.return_value = {
            "state": "stopped",
            "error_message": "Some error",
        }
        mock_server2.config = Mock()
        mock_server2.config.name = "server2"
        mock_server2.config.type = "sse"
        mock_server2.is_enabled.return_value = False
        mock_server2.is_quarantined.return_value = True

        manager._managed_servers = {"id1": mock_server1, "id2": mock_server2}

        # Mock status tracker
        with (
            patch.object(
                manager.status_tracker, "get_uptime", return_value=timedelta(hours=2)
            ),
            patch.object(
                manager.status_tracker,
                "get_server_summary",
                return_value={"start_time": datetime.now()},
            ),
            patch.object(manager.status_tracker, "get_metadata", return_value=None),
        ):
            servers = manager.list_servers()

            assert len(servers) == 2
            assert all(isinstance(server, ServerInfo) for server in servers)

            # Check first server
            server1 = next(s for s in servers if s.id == "id1")
            assert server1.name == "server1"
            assert server1.type == "stdio"
            assert server1.enabled is True
            assert server1.quarantined is False
            assert server1.state == ServerState.RUNNING

            # Check second server
            server2 = next(s for s in servers if s.id == "id2")
            assert server2.name == "server2"
            assert server2.type == "sse"
            assert server2.enabled is False
            assert server2.quarantined is True
            assert server2.state == ServerState.STOPPED
            assert server2.error_message == "Some error"

    def test_list_servers_handles_errors(self):
        """Test that errors in listing servers don't crash the method."""
        manager = MCPManager()

        # Create one good server and one that throws errors
        mock_server_good = Mock()
        mock_server_good.get_status.return_value = {"state": "running"}
        mock_server_good.config = Mock()
        mock_server_good.config.name = "good-server"
        mock_server_good.config.type = "stdio"
        mock_server_good.is_enabled.return_value = True
        mock_server_good.is_quarantined.return_value = False

        mock_server_bad = Mock()
        mock_server_bad.get_status.side_effect = Exception("Status error")
        mock_server_bad.config = Mock()
        mock_server_bad.config.name = "bad-server"
        mock_server_bad.config.type = "stdio"
        mock_server_bad.is_enabled.return_value = False
        mock_server_bad.is_quarantined.return_value = False

        manager._managed_servers = {"good": mock_server_good, "bad": mock_server_bad}

        # Mock registry to return config for bad server
        bad_config = ServerConfig(id="bad", name="bad-server", type="stdio", config={})

        with (
            patch.object(manager.status_tracker, "get_uptime", return_value=None),
            patch.object(manager.status_tracker, "get_server_summary", return_value={}),
            patch.object(manager.status_tracker, "get_metadata", return_value=None),
            patch.object(manager.registry, "get", return_value=bad_config),
        ):
            servers = manager.list_servers()

            # Should still return both servers, with bad one in error state
            assert len(servers) == 2

            good_server = next(s for s in servers if s.id == "good")
            assert good_server.state == ServerState.RUNNING

            bad_server = next(s for s in servers if s.id == "bad")
            assert bad_server.state == ServerState.ERROR
            assert "Status error" in bad_server.error_message

    def test_initialization_loads_existing_servers(self):
        """Test that manager initializes servers from registry on startup."""
        # Mock registry to return some configs
        configs = [
            ServerConfig(
                id="server1", name="server1", type="stdio", config={"command": "echo"}
            ),
            ServerConfig(
                id="server2",
                name="server2",
                type="sse",
                config={"url": "http://localhost:8080"},
            ),
        ]

        with patch("code_puppy.mcp_.manager.ServerRegistry") as mock_registry_class:
            mock_registry = Mock()
            mock_registry.list_all.return_value = configs
            mock_registry_class.return_value = mock_registry

            with (
                patch("code_puppy.mcp_.manager.ManagedMCPServer") as mock_managed_class,
                patch("code_puppy.mcp_.manager.ServerStatusTracker"),
            ):
                manager = MCPManager()

                # Should have created managed servers for all configs
                assert mock_managed_class.call_count == 2
                assert "server1" in manager._managed_servers
                assert "server2" in manager._managed_servers

                # All servers should start as STOPPED
                manager.status_tracker.set_status.assert_any_call(
                    "server1", ServerState.STOPPED
                )
                manager.status_tracker.set_status.assert_any_call(
                    "server2", ServerState.STOPPED
                )

    def test_initialization_handles_server_creation_failures(self):
        """Test that initialization handles individual server creation failures."""
        configs = [
            ServerConfig(
                id="good-server",
                name="good-server",
                type="stdio",
                config={"command": "echo"},
            ),
            ServerConfig(
                id="bad-server",
                name="bad-server",
                type="stdio",
                config={"command": "bad"},
            ),
        ]

        with patch("code_puppy.mcp_.manager.ServerRegistry") as mock_registry_class:
            mock_registry = Mock()
            mock_registry.list_all.return_value = configs
            mock_registry_class.return_value = mock_registry

            # Make second server creation fail
            def side_effect(config):
                if config.id == "bad-server":
                    raise Exception("Creation failed")
                return Mock()

            with (
                patch(
                    "code_puppy.mcp_.manager.ManagedMCPServer", side_effect=side_effect
                ),
                patch(
                    "code_puppy.mcp_.manager.ServerStatusTracker"
                ) as mock_tracker_class,
            ):
                mock_tracker = Mock()
                mock_tracker_class.return_value = mock_tracker

                manager = MCPManager()

                # Should have created only the good server
                assert "good-server" in manager._managed_servers
                assert "bad-server" not in manager._managed_servers

                # Bad server should be marked as ERROR
                mock_tracker.set_status.assert_any_call("bad-server", ServerState.ERROR)
                mock_tracker.record_event.assert_called_once()

                # Check the error event details
                call_args = mock_tracker.record_event.call_args
                assert call_args[0][0] == "bad-server"  # server_id
                assert call_args[0][1] == "initialization_error"  # event_type
                assert "Creation failed" in call_args[0][2]["error"]  # error message
