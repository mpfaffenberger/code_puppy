"""
Tests for ToolsScreen TUI component.
"""

from unittest.mock import mock_open, patch

from code_puppy.tui.screens.tools import ToolsScreen


class TestToolsScreen:
    """Test cases for ToolsScreen functionality."""

    def test_tools_screen_initialization(self):
        """Test that ToolsScreen can be initialized."""
        screen = ToolsScreen()
        assert screen is not None
        assert isinstance(screen, ToolsScreen)

    def test_get_tools_content_success(self):
        """Test successful loading of TOOLS.md content."""
        mock_content = "# 🛠️ Available Tools\n\nThis is test content."

        with patch("builtins.open", mock_open(read_data=mock_content)):
            screen = ToolsScreen()
            content = screen.get_tools_content()

        assert content == mock_content

    def test_get_tools_content_file_not_found(self):
        """Test handling when TOOLS.md file is not found."""
        with patch("builtins.open", side_effect=FileNotFoundError("No such file")):
            screen = ToolsScreen()
            content = screen.get_tools_content()

        # Should return fallback content with error message
        assert "Had trouble loading TOOLS.md (No such file)" in content
        assert "Available Tools" in content
        assert "File Operations" in content

    def test_get_tools_content_io_error(self):
        """Test handling of IOError when reading TOOLS.md."""
        with patch("builtins.open", side_effect=IOError("Permission denied")):
            screen = ToolsScreen()
            content = screen.get_tools_content()

        assert "Had trouble loading TOOLS.md (Permission denied)" in content
        assert "Available Tools" in content

    def test_get_tools_content_os_error(self):
        """Test handling of OSError when reading TOOLS.md."""
        with patch("builtins.open", side_effect=OSError("File system error")):
            screen = ToolsScreen()
            content = screen.get_tools_content()

        assert "Had trouble loading TOOLS.md (File system error)" in content
        assert "Available Tools" in content

    def test_pathlib_path_resolution(self):
        """Test that pathlib is used for proper path resolution."""
        mock_content = "# Test content"

        with patch("builtins.open", mock_open(read_data=mock_content)) as mock_file:
            screen = ToolsScreen()
            screen.get_tools_content()

        # Verify that open was called with a Path object (converted to string)
        mock_file.assert_called_once()
        called_path = str(mock_file.call_args[0][0])

        # Should end with the correct relative path
        assert called_path.endswith("tools/TOOLS.md")
        # Should not be the old hardcoded path
        assert called_path != "code_puppy/tools/TOOLS.md"

    @patch("pathlib.Path")
    def test_path_construction_logic(self, mock_path_class):
        """Test the specific pathlib path construction logic."""
        # Mock the Path class and its methods
        mock_current_dir = mock_path_class.return_value.parent
        # We don't need to use this variable, just verify Path is called
        _ = mock_current_dir.parent.parent / "tools" / "TOOLS.md"

        # Mock the file reading
        with patch("builtins.open", mock_open(read_data="test")):
            screen = ToolsScreen()
            screen.get_tools_content()

        # Verify Path(__file__) was called
        mock_path_class.assert_called()

    def test_fallback_content_structure(self):
        """Test that fallback content has expected structure."""
        with patch("builtins.open", side_effect=FileNotFoundError("test")):
            screen = ToolsScreen()
            content = screen.get_tools_content()

        # Check for key sections in fallback content
        assert "🐶 Woof!" in content
        assert "File Operations" in content
        assert "list_files" in content
        assert "edit_file" in content
        assert "Search & Analysis" in content
        assert "System Operations" in content
        assert "DRY" in content
        assert "SOLID" in content

    def test_screen_composition(self):
        """Test that screen has compose method and can be called."""
        screen = ToolsScreen()

        # Verify the compose method exists and is callable
        assert hasattr(screen, "compose")
        assert callable(screen.compose)

        # Test that get_tools_content works independently
        with patch.object(screen, "get_tools_content", return_value="# Test"):
            content = screen.get_tools_content()
            assert content == "# Test"

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
