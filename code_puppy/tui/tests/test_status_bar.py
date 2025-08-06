import unittest
from unittest.mock import MagicMock, patch

from code_puppy.tui.components.status_bar import StatusBar


class TestStatusBar(unittest.TestCase):
    def setUp(self):
        self.status_bar = StatusBar()

    def test_compose(self):
        widgets = list(self.status_bar.compose())
        self.assertGreaterEqual(len(widgets), 1)

    @patch(
        "code_puppy.tui.components.status_bar.StatusBar.app",
        new_callable=lambda: MagicMock(),
    )
    def test_update_status(self, mock_app_property):
        # Mock the query_one method to avoid DOM dependency
        mock_status_widget = MagicMock()
        self.status_bar.query_one = MagicMock(return_value=mock_status_widget)

        # Mock the app.size to avoid app dependency
        mock_app_property.size.width = 80

        # Should not raise
        self.status_bar.update_status()

        # Verify that update was called on the status widget (may be called multiple times)
        self.assertTrue(mock_status_widget.update.called)

    @patch(
        "code_puppy.tui.components.status_bar.StatusBar.app",
        new_callable=lambda: MagicMock(),
    )
    def test_watchers(self, mock_app_property):
        # Mock the query_one method to avoid DOM dependency
        mock_status_widget = MagicMock()
        self.status_bar.query_one = MagicMock(return_value=mock_status_widget)

        # Mock the app.size to avoid app dependency
        mock_app_property.size.width = 80

        # Should call update_status without error
        self.status_bar.watch_current_model()
        self.status_bar.watch_puppy_name()
        self.status_bar.watch_connection_status()
        self.status_bar.watch_agent_status()
        self.status_bar.watch_progress_visible()


if __name__ == "__main__":
    unittest.main()
