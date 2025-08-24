import unittest

from code_puppy.tui.components.custom_widgets import CustomTextArea


class DummyEvent:
    def __init__(self, key):
        self.key = key


class TestCustomTextArea(unittest.TestCase):
    def setUp(self):
        self.text_area = CustomTextArea()

    def test_message_sent_on_enter(self):
        # Simulate pressing Enter
        event = DummyEvent("enter")
        # Should not raise
        self.text_area._on_key(event)

    def test_message_sent_class(self):
        msg = CustomTextArea.MessageSent()
        self.assertIsInstance(msg, CustomTextArea.MessageSent)


if __name__ == "__main__":
    unittest.main()
