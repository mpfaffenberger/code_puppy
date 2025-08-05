import unittest
from unittest.mock import MagicMock, patch

from code_puppy.config import COMMAND_HISTORY_FILE
from code_puppy.tui.app import CodePuppyTUI
from code_puppy.tui.components.custom_widgets import CustomTextArea


class TestCommandHistory(unittest.TestCase):
    def setUp(self):
        self.app = CodePuppyTUI()

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_action_send_message_saves_to_history(self, mock_open):
        # Setup test mocks
        self.app.query_one = MagicMock()
        input_field_mock = MagicMock(spec=CustomTextArea)
        input_field_mock.text = "test command"
        self.app.query_one.return_value = input_field_mock

        # Mock other methods to prevent full execution
        self.app.add_user_message = MagicMock()
        self.app._update_submit_cancel_button = MagicMock()
        self.app.run_worker = MagicMock()

        # Execute
        self.app.action_send_message()

        # Assertions
        mock_open.assert_called_once_with(COMMAND_HISTORY_FILE, "a")
        mock_open().write.assert_called_once_with("test command\n")
        self.app.add_user_message.assert_called_once_with("test command")

    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_action_send_message_empty_command(self, mock_open):
        # Setup test mocks
        self.app.query_one = MagicMock()
        input_field_mock = MagicMock(spec=CustomTextArea)
        input_field_mock.text = "   "  # Empty or whitespace-only command
        self.app.query_one.return_value = input_field_mock

        # Mock other methods
        self.app.add_user_message = MagicMock()

        # Execute
        self.app.action_send_message()

        # Assertions - nothing should happen with empty commands
        mock_open.assert_not_called()
        self.app.add_user_message.assert_not_called()

    @patch("builtins.open")
    def test_action_send_message_handles_error(self, mock_open):
        # Setup test mocks
        self.app.query_one = MagicMock()
        input_field_mock = MagicMock(spec=CustomTextArea)
        input_field_mock.text = "test command"
        self.app.query_one.return_value = input_field_mock

        # Mock other methods to prevent full execution
        self.app.add_user_message = MagicMock()
        self.app._update_submit_cancel_button = MagicMock()
        self.app.run_worker = MagicMock()
        self.app.add_error_message = MagicMock()

        # Make open throw an exception
        mock_open.side_effect = Exception("File error")

        # Execute
        self.app.action_send_message()

        # Assertions
        self.app.add_error_message.assert_called_once()
        # Message should still be processed despite error saving to history
        self.app.add_user_message.assert_called_once_with("test command")


if __name__ == "__main__":
    unittest.main()
