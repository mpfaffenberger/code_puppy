import unittest
from code_puppy.tui.screens.disclaimer import DisclaimerScreen

class TestDisclaimerScreen(unittest.TestCase):
    def setUp(self):
        self.screen = DisclaimerScreen()

    def test_get_disclaimer_content(self):
        content = self.screen.get_disclaimer_content()
        self.assertIn("Prompt responsibly", content)

    def test_compose(self):
        widgets = list(self.screen.compose())
        self.assertGreaterEqual(len(widgets), 1)

if __name__ == "__main__":
    unittest.main()
