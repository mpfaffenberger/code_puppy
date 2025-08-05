"""
Tests for the history navigation in the sidebar component.
"""

import pytest
from textual.app import App

from code_puppy.tui.components.command_history_modal import CommandHistoryModal
from code_puppy.tui.components.sidebar import Sidebar


class TestSidebarHistoryNavigation:
    """Tests for the history navigation functionality in the sidebar."""

    @pytest.fixture
    def sidebar(self):
        """Create a sidebar instance for testing."""
        sidebar = Sidebar()
        return sidebar

    async def test_navigation_index_tracking(self, sidebar):
        """Test that the index tracking works correctly for navigation."""
        # Setup test data
        sidebar.history_entries = [
            {"command": "command1", "timestamp": "2023-01-01T10:00:00Z"},
            {"command": "command2", "timestamp": "2023-01-01T11:00:00Z"},
            {"command": "command3", "timestamp": "2023-01-01T12:00:00Z"},
        ]
        sidebar.current_history_index = 0

        # Test navigation to next command
        assert sidebar.navigate_to_next_command() is True
        assert sidebar.current_history_index == 1

        # Test navigation to next command again
        assert sidebar.navigate_to_next_command() is True
        assert sidebar.current_history_index == 2

        # Test navigation at the end of the list
        assert sidebar.navigate_to_next_command() is False
        assert sidebar.current_history_index == 2  # Index shouldn't change

        # Test navigation to previous command
        assert sidebar.navigate_to_previous_command() is True
        assert sidebar.current_history_index == 1

        # Test navigation to previous command again
        assert sidebar.navigate_to_previous_command() is True
        assert sidebar.current_history_index == 0

        # Test navigation at the beginning of the list
        assert sidebar.navigate_to_previous_command() is False
        assert sidebar.current_history_index == 0  # Index shouldn't change

    async def test_get_current_command_entry(self, sidebar):
        """Test that the current command entry is retrieved correctly."""
        # Setup test data
        sidebar.history_entries = [
            {"command": "command1", "timestamp": "2023-01-01T10:00:00Z"},
            {"command": "command2", "timestamp": "2023-01-01T11:00:00Z"},
        ]

        # Test getting entry at index 0
        sidebar.current_history_index = 0
        entry = sidebar.get_current_command_entry()
        assert entry["command"] == "command1"
        assert entry["timestamp"] == "2023-01-01T10:00:00Z"

        # Test getting entry at index 1
        sidebar.current_history_index = 1
        entry = sidebar.get_current_command_entry()
        assert entry["command"] == "command2"
        assert entry["timestamp"] == "2023-01-01T11:00:00Z"

        # Test getting entry with invalid index
        sidebar.current_history_index = 99
        entry = sidebar.get_current_command_entry()
        assert entry == {"command": "", "timestamp": ""}

        # Test getting entry with empty history entries
        sidebar.history_entries = []
        sidebar.current_history_index = 0
        entry = sidebar.get_current_command_entry()
        assert entry == {"command": "", "timestamp": ""}

    class TestApp(App):
        """Test app for simulating modal and sidebar interaction."""

        def compose(self):
            """Create the app layout."""
            self.sidebar = Sidebar()
            yield self.sidebar

    async def test_modal_navigation_integration(self, monkeypatch):
        """Test that the modal uses the sidebar's navigation methods."""
        app = self.TestApp()
        async with app.run_test() as pilot:
            # Setup test data in sidebar
            app.sidebar.history_entries = [
                {"command": "command1", "timestamp": "2023-01-01T10:00:00Z"},
                {"command": "command2", "timestamp": "2023-01-01T11:00:00Z"},
                {"command": "command3", "timestamp": "2023-01-01T12:00:00Z"},
            ]
            app.sidebar.current_history_index = 0

            # Create and mount the modal
            modal = CommandHistoryModal()
            modal.sidebar = app.sidebar
            app.push_screen(modal)
            await pilot.pause()

            # Test initial state
            assert modal.command == "command1"
            assert modal.timestamp == "2023-01-01T10:00:00Z"

            # Test navigation down
            await pilot.press("down")
            assert app.sidebar.current_history_index == 1
            assert modal.command == "command2"
            assert modal.timestamp == "2023-01-01T11:00:00Z"

            # Test navigation down again
            await pilot.press("down")
            assert app.sidebar.current_history_index == 2
            assert modal.command == "command3"
            assert modal.timestamp == "2023-01-01T12:00:00Z"

            # Test navigation up
            await pilot.press("up")
            assert app.sidebar.current_history_index == 1
            assert modal.command == "command2"
            assert modal.timestamp == "2023-01-01T11:00:00Z"
