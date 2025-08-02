"""
Tests for ToolsScreen TUI component.
"""

from unittest.mock import patch

from code_puppy.tools.tools_content import tools_content
from code_puppy.tui.screens.tools import ToolsScreen


class TestToolsScreen:
    """Test cases for ToolsScreen functionality."""

    def test_tools_screen_initialization(self):
        """Test that ToolsScreen can be initialized."""
        screen = ToolsScreen()
        assert screen is not None
        assert isinstance(screen, ToolsScreen)

    def test_tools_content_import(self):
        """Test that tools_content is imported correctly."""
        # Verify that tools_content is a non-empty string
        assert isinstance(tools_content, str)
        assert len(tools_content) > 0
        assert "File Operations" in tools_content
        assert "Search & Analysis" in tools_content

    def test_screen_composition(self):
        """Test that screen has compose method and can be called."""
        screen = ToolsScreen()

        # Verify the compose method exists and is callable
        assert hasattr(screen, "compose")
        assert callable(screen.compose)

    def test_markdown_widget_receives_tools_content(self):
        """Test that Markdown widget receives tools_content."""
        # Instead of actually executing compose, verify the tools.py implementation
        # directly by examining the source code
        import inspect

        source = inspect.getsource(ToolsScreen.compose)

        # Check that the compose method references tools_content
        assert "tools_content" in source
        # Check that Markdown is created with tools_content
        assert "yield Markdown(tools_content" in source

    def test_dismiss_functionality(self):
        """Test that dismiss button works correctly."""
        screen = ToolsScreen()

        # Mock the dismiss method
        with patch.object(screen, "dismiss") as mock_dismiss:
            screen.dismiss_tools()

        mock_dismiss.assert_called_once()

    def test_escape_key_dismisses(self):
        """Test that escape key dismisses the screen."""
        screen = ToolsScreen()

        # Create a mock key event
        class MockKeyEvent:
            key = "escape"

        with patch.object(screen, "dismiss") as mock_dismiss:
            screen.on_key(MockKeyEvent())

        mock_dismiss.assert_called_once()

    def test_non_escape_key_ignored(self):
        """Test that non-escape keys don't dismiss the screen."""
        screen = ToolsScreen()

        class MockKeyEvent:
            key = "enter"

        with patch.object(screen, "dismiss") as mock_dismiss:
            screen.on_key(MockKeyEvent())

        mock_dismiss.assert_not_called()
