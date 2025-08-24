import unittest
from unittest.mock import MagicMock, patch

from textual.widgets import ListItem, ListView

from code_puppy.tui.components.command_history_modal import CommandHistoryModal
from code_puppy.tui.components.sidebar import Sidebar
from code_puppy.tui.models.command_history import HistoryFileReader


class TestSidebarHistory(unittest.TestCase):
    def setUp(self):
        # Create a sidebar
        self.sidebar = Sidebar()

        # Mock history_list
        self.mock_history_list = MagicMock(spec=ListView)
        self.mock_history_list.children = []
        self.sidebar.query_one = MagicMock(return_value=self.mock_history_list)

        # Mock the app's push_screen method without trying to set the app property
        self.mock_push_screen = MagicMock()

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
        # Just verify append was called, don't try to access complex children structure
        self.assertTrue(self.mock_history_list.append.called)

    @patch.object(HistoryFileReader, "read_history")
    def test_load_command_history_exception(self, mock_read_history):
        # Force an exception
        mock_read_history.side_effect = Exception("Test error")

        # Call the method
        self.sidebar.load_command_history()

        # Check that an error message was added
        self.mock_history_list.append.assert_called_once()
        # Just verify append was called, don't try to access complex children structure
        self.assertTrue(self.mock_history_list.append.called)

    @patch.object(HistoryFileReader, "read_history")
    def test_load_command_history_filters_cli_commands(self, mock_read_history):
        # Mock history with CLI commands mixed with regular commands
        mock_read_history.return_value = [
            {
                "timestamp": "2024-01-01T10:00:00Z",
                "command": "How do I create a function?",
            },
            {"timestamp": "2024-01-01T10:01:00Z", "command": "/help"},
            {"timestamp": "2024-01-01T10:02:00Z", "command": "Write a Python script"},
            {"timestamp": "2024-01-01T10:04:00Z", "command": "/exit"},
            {"timestamp": "2024-01-01T10:05:00Z", "command": "Debug this error"},
            {"timestamp": "2024-01-01T10:06:00Z", "command": "/m gpt-4"},
            {"timestamp": "2024-01-01T10:07:00Z", "command": "Explain this code"},
        ]

        # Call the method
        self.sidebar.load_command_history()

        # Verify that CLI commands were filtered out
        # Should have 4 non-CLI commands: "How do I create a function?", "Write a Python script", "Debug this error", "Explain this code"
        self.assertEqual(len(self.sidebar.history_entries), 4)

        # Verify the filtered commands are the correct ones
        commands = [entry["command"] for entry in self.sidebar.history_entries]
        expected_commands = [
            "How do I create a function?",
            "Write a Python script",
            "Debug this error",
            "Explain this code",
        ]
        self.assertEqual(commands, expected_commands)

        # Verify CLI commands are not in the filtered list
        for entry in self.sidebar.history_entries:
            command = entry["command"]
            self.assertFalse(
                any(
                    command.startswith(cli_cmd)
                    for cli_cmd in {
                        "/help",
                        "/exit",
                        "/m",
                        "/motd",
                        "/show",
                        "/set",
                        "/tools",
                    }
                )
            )

    @patch(
        "code_puppy.tui.components.sidebar.Sidebar.app",
        new_callable=lambda: MagicMock(),
    )
    def test_on_key_enter(self, mock_app_property):
        # Create a mock highlighted child with a command entry
        mock_item = MagicMock(spec=ListItem)
        mock_item.command_entry = {
            "timestamp": "2023-01-01T12:34:56",
            "command": "Test command",
        }

        self.mock_history_list.highlighted_child = mock_item
        self.mock_history_list.has_focus = True
        self.mock_history_list.index = 0

        # Create a mock Key event
        mock_event = MagicMock()
        mock_event.key = "enter"

        # Call the method
        self.sidebar.on_key(mock_event)

        # Check that push_screen was called with CommandHistoryModal
        mock_app_property.push_screen.assert_called_once()
        args, kwargs = mock_app_property.push_screen.call_args
        self.assertIsInstance(args[0], CommandHistoryModal)

        # Check that event propagation was stopped
        mock_event.stop.assert_called_once()
        mock_event.prevent_default.assert_called_once()


if __name__ == "__main__":
    unittest.main()
