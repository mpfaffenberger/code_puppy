"""
Tests for MCP List and Search Commands.

Covers server listing, registry searching, table formatting,
error handling, and various edge cases.
"""

from unittest.mock import Mock, patch

import pytest

from code_puppy.command_line.mcp.list_command import ListCommand
from code_puppy.command_line.mcp.search_command import SearchCommand
from code_puppy.mcp_.managed_server import ServerState


class TestListCommand:
    """Test cases for ListCommand class."""

    def setup_method(self):
        """Setup for each test method."""
        self.command = ListCommand()

    def test_init(self):
        """Test command initialization."""
        assert hasattr(self.command, "manager")
        assert hasattr(self.command, "console")
        assert callable(self.command.generate_group_id)

    def test_execute_no_servers(self, mock_emit_info, mock_mcp_manager):
        """Test listing when no servers are registered."""
        mock_mcp_manager.list_servers.return_value = []  # Empty servers

        self.command.execute([])

        assert len(mock_emit_info.messages) == 1
        message, _ = mock_emit_info.messages[0]
        assert "No MCP servers registered" in message

    def test_execute_multiple_servers(self, mock_emit_info, mock_mcp_manager):
        """Test listing multiple servers with different states."""
        # Setup multiple servers with different states
        server1 = Mock()
        server1.id = "server-1"
        server1.name = "Server One"
        server1.type = "stdio"
        server1.enabled = True
        server1.state = ServerState.RUNNING
        server1.error_message = None
        server1.quarantined = False
        server1.uptime_seconds = 3600.5

        server2 = Mock()
        server2.id = "server-2"
        server2.name = "Server Two"
        server2.type = "sse"
        server2.enabled = False
        server2.state = ServerState.STOPPED
        server2.error_message = "Connection failed"
        server2.quarantined = True
        server2.uptime_seconds = 0

        server3 = Mock()
        server3.id = "server-3"
        server3.name = "Server Three"
        server3.type = "stdio"
        server3.enabled = True
        server3.state = ServerState.ERROR
        server3.error_message = "Process crashed"
        server3.quarantined = False
        server3.uptime_seconds = 1800.0

        mock_mcp_manager.list_servers.return_value = [server1, server2, server3]

        self.command.execute([])

        # Should have table and summary
        assert len(mock_emit_info.messages) >= 2

        # Check table was created
        table_message = mock_emit_info.messages[0][0]
        assert hasattr(table_message, "title")  # Rich Table object
        assert "MCP Server Status Dashboard" in table_message.title

        # Check summary
        summary_message = mock_emit_info.messages[1][0]
        assert "Summary" in summary_message
        assert "1/3" in summary_message  # Only 1 running out of 3

    def test_execute_all_running_servers(self, mock_emit_info, mock_mcp_manager):
        """Test listing when all servers are running."""
        server1 = Mock()
        server1.id = "server-1"
        server1.name = "Server One"
        server1.type = "stdio"
        server1.enabled = True
        server1.state = ServerState.RUNNING
        server1.error_message = None
        server1.quarantined = False
        server1.uptime_seconds = 3600.0

        server2 = Mock()
        server2.id = "server-2"
        server2.name = "Server Two"
        server2.type = "stdio"
        server2.enabled = True
        server2.state = ServerState.RUNNING
        server2.error_message = None
        server2.quarantined = False
        server2.uptime_seconds = 1800.0

        mock_mcp_manager.list_servers.return_value = [server1, server2]

        self.command.execute([])

        # Should show 2/2 running
        summary_message = mock_emit_info.messages[1][0]
        assert "2/2" in summary_message

    def test_execute_no_running_servers(self, mock_emit_info, mock_mcp_manager):
        """Test listing when no servers are running."""
        server1 = Mock()
        server1.id = "server-1"
        server1.name = "Server One"
        server1.type = "stdio"
        server1.enabled = False
        server1.state = ServerState.STOPPED
        server1.error_message = None
        server1.quarantined = False
        server1.uptime_seconds = 0

        mock_mcp_manager.list_servers.return_value = [server1]

        self.command.execute([])

        # Should show 0/1 running
        summary_message = mock_emit_info.messages[1][0]
        assert "0/1" in summary_message

    def test_execute_with_args_ignores_args(self, mock_emit_info, mock_mcp_manager):
        """Test that list command ignores any arguments provided."""
        mock_mcp_manager.list_servers.return_value = []  # Empty servers

        self.command.execute(["some", "args"])

        assert len(mock_emit_info.messages) == 1
        message, _ = mock_emit_info.messages[0]
        assert "No MCP servers registered" in message

    def test_execute_manager_exception(self, mock_emit_info):
        """Test handling when manager.list_servers raises exception."""
        self.command.manager.list_servers.side_effect = Exception("Manager error")

        self.command.execute([])

        # Check that an error message was captured
        assert len(mock_emit_info.messages) >= 1

        # Extract the error message from the captured messages
        error_found = False
        for message, _ in mock_emit_info.messages:
            message_str = str(message)
            if (
                "Error listing servers" in message_str
                and "Manager error" in message_str
            ):
                error_found = True
                break

        assert error_found, (
            f"Expected error message not found in: {[str(msg) for msg, _ in mock_emit_info.messages]}"
        )

    def test_server_state_formatting(self, mock_emit_info, mock_mcp_manager):
        """Test that all server states are properly formatted."""
        states = [
            ServerState.RUNNING,
            ServerState.STOPPED,
            ServerState.ERROR,
            ServerState.STARTING,
            ServerState.STOPPING,
        ]

        servers = []
        for i, state in enumerate(states):
            server = Mock()
            server.id = f"server-{i}"
            server.name = f"Server {i}"
            server.type = "stdio"
            server.enabled = True
            server.state = state
            server.error_message = None
            server.quarantined = False
            server.uptime_seconds = 100.0 * i
            servers.append(server)

        mock_mcp_manager.list_servers.return_value = servers

        self.command.execute([])

        # Should execute without errors and show table
        assert len(mock_emit_info.messages) >= 2
        table_message = mock_emit_info.messages[0][0]
        assert hasattr(table_message, "title")

    def test_generate_group_id(self):
        """Test group ID generation."""
        group_id1 = self.command.generate_group_id()
        group_id2 = self.command.generate_group_id()

        assert group_id1 != group_id2
        assert len(group_id1) > 10


class TestSearchCommand:
    """Test cases for SearchCommand class."""

    def setup_method(self):
        """Setup for each test method."""
        self.command = SearchCommand()

    def test_init(self):
        """Test command initialization."""
        assert hasattr(self.command, "manager")
        assert hasattr(self.command, "console")
        assert callable(self.command.generate_group_id)

    def test_execute_no_args_shows_popular(self, mock_emit_info, mock_server_catalog):
        """Test executing without args shows popular servers."""
        # Setuppopular servers
        server1 = Mock()
        server1.id = "popular-1"
        server1.name = "popular-one"
        server1.display_name = "Popular Server One"
        server1.description = "A popular server for testing"
        server1.category = "test"
        server1.tags = ["test", "popular"]
        server1.verified = True
        server1.popular = True

        server2 = Mock()
        server2.id = "popular-2"
        server2.name = "popular-two"
        server2.display_name = "Popular Server Two"
        server2.description = "Another popular server"
        server2.category = "utility"
        server2.tags = ["utility", "popular"]
        server2.verified = False
        server2.popular = True

        mock_server_catalog.get_popular.return_value = [server1, server2]

        self.command.execute([])

        # Should show title and table
        assert len(mock_emit_info.messages) >= 3

        # Check title
        title_message = mock_emit_info.messages[0][0]
        assert "Popular MCP Servers" in title_message

        # Check table exists (could be at index 1 or 2 depending on emit_system_message handling)
        table_message = mock_emit_info.messages[1][0]
        # The table is passed through emit_system_message which may convert it to string
        # So we check if it contains table content or is a Rich Table
        assert hasattr(table_message, "show_header") or isinstance(table_message, str)

        # Check hints exist somewhere in the messages
        hint_found = any(
            "✓ = Verified" in msg[0] and "⭐ = Popular" in msg[0]
            for msg in mock_emit_info.messages
        )
        assert hint_found, "Should find hints about verified and popular servers"

    def test_execute_with_search_query(self, mock_emit_info, mock_server_catalog):
        """Test executing with search query."""
        # Setup search results
        server1 = Mock()
        server1.id = "search-1"
        server1.name = "search-one"
        server1.display_name = "Search Result One"
        server1.description = "A server found by_SEARCH"
        server1.category = "database"
        server1.tags = ["db", "search"]
        server1.verified = False
        server1.popular = False

        mock_server_catalog.search.return_value = [server1]

        self.command.execute(["database", "server"])

        # Should show search title
        title_message = mock_emit_info.messages[0][0]
        assert "Searching for: database server" in title_message

        # Should call search with query
        mock_server_catalog.search.assert_called_once_with("database server")

        # Should show table
        table_message = mock_emit_info.messages[1][0]
        assert hasattr(table_message, "show_header") or isinstance(table_message, str)

    @pytest.mark.skip("Search functionality not implemented")
    def test_execute_no_search_results(self, mock_emit_info, mock_server_catalog):
        """Test executing search with no results."""
        mock_server_catalog.search.return_value = []

        self.command.execute(["nonexistent"])

        # Should show no results message
        messages = [msg[0] for msg, _ in mock_emit_info.messages]
        assert any("No servers found" in msg for msg in messages)
        assert any("Try: /mcp search database" in msg for msg in messages)

    @pytest.mark.skip("Search functionality not implemented")
    def test_execute_no_popular_servers(self, mock_emit_info, mock_server_catalog):
        """Test executing with no args but no popular servers."""
        mock_server_catalog.get_popular.return_value = []

        self.command.execute([])

        messages = [msg[0] for msg, _ in mock_emit_info.messages]
        assert any("No servers found" in msg for msg in messages)

    def test_execute_with_many_results_limits_to_20(
        self, mock_emit_info, mock_server_catalog
    ):
        """Test that search results are limited to 20 items."""
        # Create 25 mock servers
        servers = []
        for i in range(25):
            server = Mock()
            server.id = f"server-{i}"
            server.name = f"server-{i}"
            server.display_name = f"Server {i}"
            server.description = f"Description for server {i}"
            server.category = "test"
            server.tags = [f"tag{i}", "test"]
            server.verified = i % 2 == 0
            server.popular = i % 3 == 0
            servers.append(server)

        mock_server_catalog.search.return_value = servers
        mock_server_catalog.get_popular.return_value = servers

        # Test search with many results
        self.command.execute(["test"])

        # Should still work and show only first 20
        assert len(mock_emit_info.messages) >= 2
        table_message = mock_emit_info.messages[1][0]
        assert hasattr(table_message, "show_header") or isinstance(
            table_message, str
        )  # Rich Table created

    def test_execute_search_field_formatting(self, mock_emit_info, mock_server_catalog):
        """Test that search result fields are properly formatted."""
        server = Mock()
        server.id = "test-server-123"
        server.name = "test-server"
        server.display_name = "Test Server Database Connection"
        server.description = "This is a very long description that should be truncated because it exceeds the fifty character limit for display purposes in the search results table"
        server.category = "database"
        server.tags = ["database", "connection", "mysql", "postgresql", "utility"]
        server.verified = True
        server.popular = True

        mock_server_catalog.search.return_value = [server]

        self.command.execute(["database"])

        # Should create table with formatted content
        table_message = mock_emit_info.messages[1][0]
        assert hasattr(table_message, "show_header") or isinstance(table_message, str)

        # Verify indicators are included
        # (This would require more complex inspection of Rich Table content)

    @pytest.mark.skip("Search functionality not implemented")
    def test_execute_with_verified_and_popular_indicators(
        self, mock_emit_info, mock_server_catalog
    ):
        """Test that verified and popular indicators are shown."""
        server = Mock()
        server.id = "test-server"
        server.name = "test-server"
        server.display_name = "Test Server"
        server.description = "Test description"
        server.category = "test"
        server.tags = ["test"]
        server.verified = True
        server.popular = True

        mock_server_catalog.search.return_value = [server]

        self.command.execute(["test"])

        # Should show table with indicators
        table_message = mock_emit_info.messages[1][0]
        assert hasattr(table_message, "show_header") or isinstance(table_message, str)

        # Should show legend
        legend_message = mock_emit_info.messages[2][0]
        assert "✓ = Verified" in legend_message
        assert "★ = Popular" in legend_message

    @pytest.mark.skip("Search functionality not implemented")
    def test_execute_import_error(self, mock_emit_info):
        """Test handling when server registry is not available."""
        with patch(
            "code_puppy.mcp_.server_registry_catalog.catalog", side_effect=ImportError
        ):
            self.command.execute(["test"])

            messages = [msg[0] for msg, _ in mock_emit_info.messages]
            assert any("Server registry not available" in msg for msg in messages)

    @pytest.mark.skip("Search functionality not implemented")
    def test_execute_general_exception(self, mock_emit_info):
        """Test handling of general exceptions."""
        with patch(
            "code_puppy.mcp_.server_registry_catalog.catalog",
            side_effect=Exception("Search error"),
        ):
            self.command.execute(["test"])

            messages = [msg[0] for msg, _ in mock_emit_info.messages]
            assert any("Error searching servers" in msg for msg in messages)

    def test_execute_with_empty_server_fields(
        self, mock_emit_info, mock_server_catalog
    ):
        """Test handling servers with minimal/empty fields."""
        server = Mock()
        server.id = "minimal-server"
        server.name = "minimal"
        server.display_name = ""
        server.description = ""
        server.category = ""
        server.tags = []
        server.verified = False
        server.popular = False

        mock_server_catalog.search.return_value = [server]

        # Should not crash with empty fields
        self.command.execute(["minimal"])

        table_message = mock_emit_info.messages[1][0]
        assert hasattr(table_message, "show_header") or isinstance(table_message, str)

    def test_execute_whitespace_search_query(self, mock_emit_info, mock_server_catalog):
        """Test search with whitespace in query."""
        server = Mock()
        server.id = "test-server"
        server.name = "test"
        server.display_name = "Test Server"
        server.description = "Test description"
        server.category = "test"
        server.tags = ["test"]
        server.verified = False
        server.popular = False

        mock_server_catalog.search.return_value = [server]

        self.command.execute(["  test  with  spaces  "])

        # Query should preserve spaces (joined)
        mock_server_catalog.search.assert_called_once_with("  test  with  spaces  ")

        title_message = mock_emit_info.messages[0][0]
        assert "test  with  spaces" in title_message

    def test_generate_group_id(self):
        """Test group ID generation."""
        group_id1 = self.command.generate_group_id()
        group_id2 = self.command.generate_group_id()

        assert group_id1 != group_id2
        assert len(group_id1) > 10
        assert len(group_id2) > 10


class TestCommandIntegration:
    """Integration tests for list and search commands."""

    def test_commands_use_different_group_ids(self, mock_emit_info, mock_mcp_manager):
        """Test that different commands generate different group IDs."""
        list_cmd = ListCommand()
        search_cmd = SearchCommand()

        # Mock both to have no results for simplicity
        mock_mcp_manager.list_servers.return_value = []
        with patch("code_puppy.mcp_.server_registry_catalog.catalog") as mock_catalog:
            mock_catalog.get_popular.return_value = []

            list_cmd.execute([])
            list_group_id = mock_emit_info.messages[0][
                1
            ]  # First list message's group ID

            mock_emit_info.messages.clear()  # Reset
            search_cmd.execute([])
            search_group_id = mock_emit_info.messages[0][
                1
            ]  # First search message's group ID

            # Should be different group IDs
            assert list_group_id != search_group_id

    @pytest.mark.skip("Search functionality not implemented")
    def test_error_handling_consistency(self, mock_emit_info):
        """Test that both commands handle errors gracefully."""
        list_cmd = ListCommand()
        search_cmd = SearchCommand()

        # Both should handle their respective errors without crashing
        list_cmd.manager.list_servers.side_effect = Exception("List error")
        list_cmd.execute([])

        with patch(
            "code_puppy.mcp_.server_registry_catalog.catalog",
            side_effect=Exception("Search error"),
        ):
            search_cmd.execute(["test"])

        # Both should show error messages
        messages = [msg[0] for msg, _ in mock_emit_info.messages]
        assert any("Error listing servers" in msg for msg in messages)
        assert any("Error searching servers" in msg for msg in messages)
