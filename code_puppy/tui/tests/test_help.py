import unittest
from code_puppy.tui.screens.help import HelpScreen

class TestHelpScreen(unittest.TestCase):
    def setUp(self):
        self.screen = HelpScreen()

    def test_get_help_content(self):
        content = self.screen.get_help_content()
        self.assertIn("Code Puppy TUI", content)

    def test_compose(self):
        widgets = list(self.screen.compose())
        self.assertGreaterEqual(len(widgets), 1)

if __name__ == "__main__":
    unittest.main()
