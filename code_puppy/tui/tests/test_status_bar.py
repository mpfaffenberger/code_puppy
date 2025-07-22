import unittest

from code_puppy.tui.components.status_bar import StatusBar


class TestStatusBar(unittest.TestCase):
    def setUp(self):
        self.status_bar = StatusBar()

    def test_compose(self):
        widgets = list(self.status_bar.compose())
        self.assertGreaterEqual(len(widgets), 1)

    def test_update_status(self):
        # Should not raise
        self.status_bar.update_status()

    def test_watchers(self):
        # Should call update_status without error
        self.status_bar.watch_current_model()
        self.status_bar.watch_puppy_name()
        self.status_bar.watch_connection_status()
        self.status_bar.watch_agent_status()
        self.status_bar.watch_progress_visible()


if __name__ == "__main__":
    unittest.main()
