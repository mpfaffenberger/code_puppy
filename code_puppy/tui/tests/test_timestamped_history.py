import unittest
from unittest.mock import MagicMock, patch

from code_puppy.config import save_command_to_history
from code_puppy.tui.app import CodePuppyTUI
from code_puppy.tui.components.custom_widgets import CustomTextArea


class TestTimestampedHistory(unittest.TestCase):
    def setUp(self):
        self.app = CodePuppyTUI()

    @patch("code_puppy.tui.app.save_command_to_history")
    def test_action_send_message_uses_timestamp_function(self, mock_save_command):
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
        mock_save_command.assert_called_once_with("test command")
        self.app.add_user_message.assert_called_once_with("test command")

    @patch("datetime.datetime")
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_save_command_uses_iso_timestamp(self, mock_file, mock_datetime):
        # Setup
        mock_now = MagicMock()
        mock_now.isoformat.return_value = "2023-01-01T12:34:56"
        mock_datetime.now.return_value = mock_now

        # Call function
        save_command_to_history("test command")

        # Assertions
        mock_file().write.assert_called_once_with(
            "\n# 2023-01-01T12:34:56\ntest command\n"
        )
        mock_now.isoformat.assert_called_once_with(timespec="seconds")


if __name__ == "__main__":
    unittest.main()
