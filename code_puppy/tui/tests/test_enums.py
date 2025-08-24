import unittest

from code_puppy.tui.models.enums import MessageType


class TestMessageType(unittest.TestCase):
    def test_enum_values(self):
        self.assertEqual(MessageType.USER.value, "user")
        self.assertEqual(MessageType.AGENT.value, "agent")
        self.assertEqual(MessageType.SYSTEM.value, "system")
        self.assertEqual(MessageType.ERROR.value, "error")


if __name__ == "__main__":
    unittest.main()
