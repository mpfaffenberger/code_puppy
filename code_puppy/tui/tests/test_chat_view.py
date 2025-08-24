import unittest
from datetime import datetime
from unittest.mock import patch

from code_puppy.tui.components.chat_view import ChatView
from code_puppy.tui.models.chat_message import ChatMessage
from code_puppy.tui.models.enums import MessageType


class TestChatView(unittest.TestCase):
    def setUp(self):
        self.chat_view = ChatView()

    @patch.object(ChatView, "mount")
    def test_add_message_user(self, mock_mount):
        msg = ChatMessage(
            id="test-user-1",
            type=MessageType.USER,
            content="Hello",
            timestamp=datetime.now(),
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)
        mock_mount.assert_called_once()

    @patch.object(ChatView, "mount")
    def test_add_message_agent(self, mock_mount):
        msg = ChatMessage(
            id="test-agent-1",
            type=MessageType.AGENT,
            content="Hi there!",
            timestamp=datetime.now(),
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)
        mock_mount.assert_called_once()

    @patch.object(ChatView, "mount")
    def test_add_message_system(self, mock_mount):
        msg = ChatMessage(
            id="test-system-1",
            type=MessageType.SYSTEM,
            content="System message",
            timestamp=datetime.now(),
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)
        mock_mount.assert_called_once()

    @patch.object(ChatView, "mount")
    def test_add_message_error(self, mock_mount):
        msg = ChatMessage(
            id="test-error-1",
            type=MessageType.ERROR,
            content="Error occurred",
            timestamp=datetime.now(),
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)
        mock_mount.assert_called_once()

    @patch.object(ChatView, "mount")
    @patch.object(ChatView, "query")
    def test_clear_messages(self, mock_query, mock_mount):
        # Mock the query method to return empty iterables
        mock_query.return_value = []

        msg = ChatMessage(
            id="test-clear-1",
            type=MessageType.USER,
            content="Hello",
            timestamp=datetime.now(),
        )
        self.chat_view.add_message(msg)
        self.chat_view.clear_messages()
        self.assertEqual(len(self.chat_view.messages), 0)
        # Verify that query was called to find widgets to remove
        self.assertTrue(mock_query.called)

    def test_render_agent_message_with_syntax(self):
        prefix = "Agent: "
        content = "Some text\n```python\nprint('hi')\n```"
        group = self.chat_view._render_agent_message_with_syntax(prefix, content)
        self.assertIsNotNone(group)


if __name__ == "__main__":
    unittest.main()
