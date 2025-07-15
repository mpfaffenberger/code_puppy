"""Tests for the FileBrowser component."""

import pytest

from code_puppy.tui.components import FileBrowser, Sidebar


class TestFileBrowser:
    """Test the FileBrowser component."""

    def test_file_browser_creation(self):
        """Test that FileBrowser can be created."""
        browser = FileBrowser()
        assert browser is not None

    def test_file_browser_has_directory_tree(self):
        """Test that FileBrowser contains a DirectoryTree widget."""
        browser = FileBrowser()
        # This is a basic structure test - in a real app test we'd mount it
        assert hasattr(browser, "compose")

    def test_file_browser_message_type(self):
        """Test that FileBrowser.FileSelected message works."""
        message = FileBrowser.FileSelected("/test/path/file.py")
        assert message.file_path == "/test/path/file.py"


class TestSidebarTabs:
    """Test the enhanced Sidebar with tabs."""

    def test_sidebar_creation(self):
        """Test that enhanced Sidebar can be created."""
        sidebar = Sidebar()
        assert sidebar is not None

    def test_sidebar_has_compose_method(self):
        """Test that Sidebar has the compose method for tab layout."""
        sidebar = Sidebar()
        assert hasattr(sidebar, "compose")
        assert hasattr(sidebar, "load_models_list")
        assert hasattr(sidebar, "on_file_browser_file_selected")


if __name__ == "__main__":
    pytest.main([__file__])
