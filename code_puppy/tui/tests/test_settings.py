import unittest
from code_puppy.tui.screens.settings import SettingsScreen

class TestSettingsScreen(unittest.TestCase):
    def setUp(self):
        self.screen = SettingsScreen()

    def test_compose(self):
        widgets = list(self.screen.compose())
        self.assertGreaterEqual(len(widgets), 1)

    def test_load_model_options_fallback(self):
        class DummySelect:
            def set_options(self, options):
                self.options = options
        select = DummySelect()
        # Should fallback to default if file not found
        self.screen.load_model_options(select)
        self.assertTrue(hasattr(select, 'options'))
        self.assertGreaterEqual(len(select.options), 1)

if __name__ == "__main__":
    unittest.main()
