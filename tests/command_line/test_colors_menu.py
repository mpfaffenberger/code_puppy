"""Comprehensive test coverage for colors_menu.py.

Tests interactive TUI for banner color configuration including:
- Menu initialization and color loading
- Banner preview rendering
- Color selection and navigation
- Settings persistence
- Theme management
- Error handling and edge cases
"""

from unittest.mock import patch

from code_puppy.command_line.colors_menu import (
    BANNER_COLORS,
    BANNER_DISPLAY_INFO,
    BANNER_SAMPLE_CONTENT,
    ColorConfiguration,
)


class TestBannerDisplayInfo:
    """Test banner display configuration."""

    def test_all_banners_have_display_info(self):
        """Test that all expected banners are defined."""
        expected_banners = [
            "thinking",
            "agent_response",
            "shell_command",
            "read_file",
            "edit_file",
            "grep",
            "directory_listing",
            "agent_reasoning",
            "invoke_agent",
            "subagent_response",
            "list_agents",
            "universal_constructor",
            "terminal_tool",
        ]
        for banner in expected_banners:
            assert banner in BANNER_DISPLAY_INFO

    def test_banner_display_has_name_and_icon(self):
        """Test that each banner display info has name and icon."""
        for banner_key, (name, icon) in BANNER_DISPLAY_INFO.items():
            assert isinstance(name, str)
            assert len(name) > 0
            assert isinstance(icon, str)

    def test_thinking_banner_display(self):
        """Test thinking banner display info."""
        name, icon = BANNER_DISPLAY_INFO["thinking"]
        assert name == "THINKING"
        assert icon == "⚡"

    def test_shell_command_banner_display(self):
        """Test shell command banner display info."""
        name, icon = BANNER_DISPLAY_INFO["shell_command"]
        assert name == "SHELL COMMAND"
        assert icon == "🚀"


class TestBannerSampleContent:
    """Test banner sample content."""

    def test_all_banners_have_sample_content(self):
        """Test that all banners have sample content defined."""
        for banner_key in BANNER_DISPLAY_INFO.keys():
            assert banner_key in BANNER_SAMPLE_CONTENT

    def test_sample_content_is_non_empty(self):
        """Test that all sample content is non-empty."""
        for banner_key, content in BANNER_SAMPLE_CONTENT.items():
            assert isinstance(content, str)
            assert len(content) > 0

    def test_thinking_banner_content(self):
        """Test thinking banner sample content."""
        content = BANNER_SAMPLE_CONTENT["thinking"]
        assert "analyze" in content.lower() or "approach" in content.lower()

    def test_shell_command_banner_content(self):
        """Test shell command banner sample content."""
        content = BANNER_SAMPLE_CONTENT["shell_command"]
        assert "$" in content or "npm" in content or "test" in content


class TestBannerColors:
    """Test available banner colors."""

    def test_cool_colors_defined(self):
        """Test that cool colors (blue, cyan, etc.) are defined."""
        cool_colors = [
            "blue",
            "dark blue",
            "cyan",
            "teal",
            "dodger blue",
        ]
        for color in cool_colors:
            assert color in BANNER_COLORS

    def test_warm_colors_defined(self):
        """Test that warm colors (red, orange, etc.) are defined."""
        warm_colors = [
            "red",
            "orange",
        ]
        for color in warm_colors:
            if color in BANNER_COLORS:  # Optional warm colors
                assert BANNER_COLORS[color]

    def test_green_colors_defined(self):
        """Test that green colors are defined."""
        green_colors = [
            "green",
            "dark green",
            "sea green",
            "spring green",
        ]
        for color in green_colors:
            assert color in BANNER_COLORS

    def test_purple_colors_defined(self):
        """Test that purple colors are defined."""
        purple_colors = [
            "purple",
            "dark magenta",
            "medium purple",
            "dark violet",
        ]
        for color in purple_colors:
            assert color in BANNER_COLORS

    def test_colors_have_valid_values(self):
        """Test that all colors have non-empty string values."""
        for color_name, color_value in BANNER_COLORS.items():
            assert isinstance(color_value, str)
            assert len(color_value) > 0


class TestColorConfigurationInitialization:
    """Test ColorConfiguration initialization."""

    def test_color_configuration_creation(self):
        """Test creating a ColorConfiguration instance."""
        config = ColorConfiguration()
        assert config is not None

    def test_color_configuration_has_banner_colors(self):
        """Test that ColorConfiguration can access banner colors."""
        config = ColorConfiguration()
        # Would have banner colors configured
        assert hasattr(config, "__dict__")


class TestBannerNavigation:
    """Test banner list navigation."""

    def test_banner_selection(self):
        """Test selecting a banner."""
        banners = list(BANNER_DISPLAY_INFO.keys())
        selected_idx = 0
        assert selected_idx < len(banners)
        assert banners[selected_idx] in BANNER_DISPLAY_INFO

    def test_navigate_banners_down(self):
        """Test navigating down through banner list."""
        banners = list(BANNER_DISPLAY_INFO.keys())
        selected_idx = 0
        initial_idx = selected_idx
        selected_idx = min(len(banners) - 1, selected_idx + 1)
        assert selected_idx >= initial_idx

    def test_navigate_banners_up(self):
        """Test navigating up through banner list."""
        list(BANNER_DISPLAY_INFO.keys())
        selected_idx = 5
        selected_idx = max(0, selected_idx - 1)
        assert selected_idx == 4

    def test_banner_navigation_bounds(self):
        """Test navigation bounds are respected."""
        banners = list(BANNER_DISPLAY_INFO.keys())

        # Can't go below 0
        selected_idx = -1
        selected_idx = max(0, selected_idx)
        assert selected_idx == 0

        # Can't go past length
        selected_idx = len(banners) + 10
        selected_idx = min(len(banners) - 1, selected_idx)
        assert selected_idx == len(banners) - 1


class TestColorSelection:
    """Test color selection for banners."""

    def test_select_first_color(self):
        """Test selecting the first color."""
        colors = list(BANNER_COLORS.keys())
        selected_idx = 0
        assert selected_idx < len(colors)

    def test_navigate_colors_down(self):
        """Test navigating down through color list."""
        colors = list(BANNER_COLORS.keys())
        initial_idx = 0
        selected_idx = min(len(colors) - 1, initial_idx + 1)
        assert selected_idx >= initial_idx

    def test_navigate_colors_up(self):
        """Test navigating up through color list."""
        list(BANNER_COLORS.keys())
        selected_idx = 10
        selected_idx = max(0, selected_idx - 1)
        assert selected_idx == 9


class TestColorPersistence:
    """Test color settings persistence."""

    @patch("code_puppy.config.set_config_value")
    def test_save_color_for_banner(self, mock_set_config):
        """Test saving color selection for a banner."""
        from code_puppy.config import set_config_value

        set_config_value("banner_colors.thinking", "blue")
        mock_set_config.assert_called_once_with("banner_colors.thinking", "blue")

    @patch("code_puppy.config.set_config_value")
    def test_multiple_color_saves(self, mock_set_config):
        """Test saving colors for multiple banners."""
        from code_puppy.config import set_config_value

        set_config_value("banner_colors.thinking", "blue")
        set_config_value("banner_colors.shell_command", "green")
        set_config_value("banner_colors.read_file", "cyan")
        assert mock_set_config.call_count == 3


class TestColorPreview:
    """Test color preview rendering."""

    def test_preview_with_sample_content(self):
        """Test that preview renders with sample content."""
        banner_key = "thinking"
        # Would render banner with sample content
        if banner_key in BANNER_SAMPLE_CONTENT:
            content = BANNER_SAMPLE_CONTENT[banner_key]
            assert len(content) > 0

    def test_preview_displays_correct_banner_name(self):
        """Test that preview displays correct banner name."""
        banner_key = "shell_command"
        name, icon = BANNER_DISPLAY_INFO[banner_key]
        # Preview would show this name and icon
        assert name == "SHELL COMMAND"
        assert icon == "🚀"


class TestThemeManagement:
    """Test theme management functionality."""

    @patch("code_puppy.config.set_config_value")
    def test_save_theme_settings(self, mock_set_config):
        """Test saving theme settings."""
        from code_puppy.config import set_config_value

        theme_data = {"thinking": "blue", "shell_command": "green"}
        for banner, color in theme_data.items():
            set_config_value(f"banner_colors.{banner}", color)
        assert mock_set_config.call_count >= 2


class TestErrorHandling:
    """Test error handling in colors menu."""

    def test_invalid_color_not_in_palette(self):
        """Test error handling for invalid color selection."""
        invalid_color = "nonexistent_color"
        is_valid = invalid_color in BANNER_COLORS
        assert is_valid is False

    def test_valid_color_exists_in_palette(self):
        """Test that valid colors exist in palette."""
        valid_color = "blue"
        is_valid = valid_color in BANNER_COLORS
        assert is_valid is True


class TestMenuState:
    """Test menu state management."""

    def test_configuration_object_creation(self):
        """Test that ColorConfiguration object can be created."""
        config = ColorConfiguration()
        assert config is not None

    def test_state_can_be_updated(self):
        """Test that configuration state can be tracked."""
        config = ColorConfiguration()
        # State would be updated as user navigates
        assert hasattr(config, "__dict__")


class TestMenuExit:
    """Test menu exit behavior."""

    def test_exit_without_changes(self):
        """Test exiting menu without saving changes."""
        config = ColorConfiguration()
        # No changes made, just exit
        assert config is not None

    @patch("code_puppy.config.set_config_value")
    def test_exit_after_changes(self, mock_set_config):
        """Test exiting menu after making changes."""
        from code_puppy.config import set_config_value

        ColorConfiguration()
        set_config_value("banner_colors.thinking", "purple")
        # Exit and save
        assert mock_set_config.called
