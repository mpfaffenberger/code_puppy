import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import ListItem, ListView

from code_puppy.tui.components.command_history_modal import CommandHistoryModal
from code_puppy.tui.components.sidebar import Sidebar
from code_puppy.tui.models.command_history import HistoryFileReader


class TestSidebarHistory(unittest.TestCase):
    def setUp(self):
        # Mock the app object and patch the Sidebar's push_screen method directly
        self.mock_app = MagicMock()

        # Create a sidebar
        self.sidebar = Sidebar()

        # Mock the sidebar methods that would use the app
        self.sidebar.app_push_screen = MagicMock()

        # Patch the method that needs access to app
        def mock_push_screen(screen, *args, **kwargs):
            self.mock_app.push_screen(screen, *args, **kwargs)

        # Add a patch for the app.push_screen method
        self.sidebar.app = MagicMock()
        self.sidebar.app.push_screen = mock_push_screen

        # Mock history_list
        self.mock_history_list = MagicMock(spec=ListView)
        self.mock_history_list.children = []
        self.sidebar.query_one = MagicMock(return_value=self.mock_history_list)

    @patch.object(HistoryFileReader, "read_history")
    def test_load_command_history(self, mock_read_history):
        # Mock the history entries
        mock_entries = [
            {"timestamp": "2023-01-01T12:34:56", "command": "First command"},
            {"timestamp": "2023-01-01T13:45:00", "command": "Second command"},
        ]
        mock_read_history.return_value = mock_entries

        # Call the method
        self.sidebar.load_command_history()

        # Check that ListView.append was called for each entry
        self.assertEqual(self.mock_history_list.append.call_count, 2)

        # Check that ListView.clear was called
        self.mock_history_list.clear.assert_called_once()

    @patch.object(HistoryFileReader, "read_history")
    def test_load_command_history_empty(self, mock_read_history):
        # Mock empty history
        mock_read_history.return_value = []

        # Call the method
        self.sidebar.load_command_history()

        # Check that an empty message was added
        self.mock_history_list.append.assert_called_once()
        args, kwargs = self.mock_history_list.append.call_args
        self.assertIn("No command history", args[0].children[0].renderable)

    @patch.object(HistoryFileReader, "read_history")
    def test_load_command_history_exception(self, mock_read_history):
        # Force an exception
        mock_read_history.side_effect = Exception("Test error")

        # Call the method
        self.sidebar.load_command_history()

        # Check that an error message was added
        self.mock_history_list.append.assert_called_once()
        args, kwargs = self.mock_history_list.append.call_args
        self.assertIn("Error loading history", args[0].children[0].renderable)

    def test_on_key_enter(self):
        # Create a mock highlighted child with a command entry
        mock_item = MagicMock(spec=ListItem)
        mock_item.command_entry = {
            "timestamp": "2023-01-01T12:34:56",
            "command": "Test command",
        }

        self.mock_history_list.highlighted_child = mock_item
        self.mock_history_list.has_focus = True

        # Create a mock Key event
        mock_event = MagicMock()
        mock_event.key = "enter"

        # Call the method
        self.sidebar.on_key(mock_event)

        # Check that push_screen was called with CommandHistoryModal
        self.mock_app.push_screen.assert_called_once()
        args, kwargs = self.mock_app.push_screen.call_args
        self.assertIsInstance(args[0], CommandHistoryModal)
        self.assertEqual(args[0].command, "Test command")
        self.assertEqual(args[0].timestamp, "2023-01-01T12:34:56")

        # Check that event propagation was stopped
        mock_event.stop.assert_called_once()
        mock_event.prevent_default.assert_called_once()


if __name__ == "__main__":
    unittest.main()
