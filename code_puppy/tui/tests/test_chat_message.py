import unittest
from datetime import datetime

from code_puppy.tui.models.chat_message import ChatMessage
from code_puppy.tui.models.enums import MessageType


class TestChatMessage(unittest.TestCase):
    def test_chat_message_defaults(self):
        msg = ChatMessage(
            id="1", type=MessageType.USER, content="hi", timestamp=datetime.now()
        )
        self.assertEqual(msg.metadata, {})

    def test_chat_message_with_metadata(self):
        meta = {"foo": "bar"}
        msg = ChatMessage(
            id="2",
            type=MessageType.AGENT,
            content="hello",
            timestamp=datetime.now(),
            metadata=meta,
        )
        self.assertEqual(msg.metadata, meta)


if __name__ == "__main__":
    unittest.main()
