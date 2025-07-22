import unittest
from datetime import datetime

from code_puppy.tui.components.chat_view import ChatView
from code_puppy.tui.models.chat_message import ChatMessage
from code_puppy.tui.models.enums import MessageType


class TestChatView(unittest.TestCase):
    def setUp(self):
        self.chat_view = ChatView()

    def test_add_message_user(self):
        msg = ChatMessage(
            type=MessageType.USER, content="Hello", timestamp=datetime.now()
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)

    def test_add_message_agent(self):
        msg = ChatMessage(
            type=MessageType.AGENT, content="Hi there!", timestamp=datetime.now()
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)

    def test_add_message_system(self):
        msg = ChatMessage(
            type=MessageType.SYSTEM, content="System message", timestamp=datetime.now()
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)

    def test_add_message_error(self):
        msg = ChatMessage(
            type=MessageType.ERROR, content="Error occurred", timestamp=datetime.now()
        )
        self.chat_view.add_message(msg)
        self.assertIn(msg, self.chat_view.messages)

    def test_clear_messages(self):
        msg = ChatMessage(
            type=MessageType.USER, content="Hello", timestamp=datetime.now()
        )
        self.chat_view.add_message(msg)
        self.chat_view.clear_messages()
        self.assertEqual(len(self.chat_view.messages), 0)

    def test_render_agent_message_with_syntax(self):
        prefix = "Agent: "
        content = "Some text\n```python\nprint('hi')\n```"
        group = self.chat_view._render_agent_message_with_syntax(prefix, content)
        self.assertIsNotNone(group)


if __name__ == "__main__":
    unittest.main()
