"""Tests for theme models and color validation."""

from code_puppy.theming.theme_models import Theme, ThemeColors


class TestThemeColors:
    """Test ThemeColors model functionality."""

    def test_default_values_are_sensible(self):
        """Test that default color values are valid Rich style strings."""
        colors = ThemeColors()

        # All required color slots should be non-empty
        assert colors.error_style == "bold red"
        assert colors.warning_style == "yellow"
        assert colors.success_style == "green"
        assert colors.info_style == "white"
        assert colors.debug_style == "dim"

        # Check UI element colors
        assert colors.header_style == "bold cyan"
        assert colors.prompt_style == "bold green"
        assert colors.accent_style == "cyan"
        assert colors.muted_style == "dim"
        assert colors.highlight_style == "bold yellow"

        # Check agent message colors
        assert colors.reasoning_header_style == "bold magenta"
        assert colors.response_header_style == "bold blue"

        # Check tool output colors
        assert colors.file_path_style == "cyan"
        assert colors.line_number_style == "dim"
        assert colors.command_style == "magenta"

        # Check spinner colors
        assert colors.spinner_style == "bold cyan"
        assert colors.spinner_text_style == "cyan"

        # Check panel colors
        assert colors.panel_border_style == "white"
        assert colors.panel_title_style == "bold white"

        # Check navigation colors
        assert colors.nav_key_style == "bold blue"
        assert colors.nav_text_style == "cyan"

    def test_all_color_slots_populated(self):
        """Test that all color slots have values and are non-empty strings."""
        colors = ThemeColors()

        # Check all color slots are populated
        for attr_name in colors.__dict__:
            assert hasattr(colors, attr_name)
            value = getattr(colors, attr_name)
            assert isinstance(value, str)
            assert len(value) > 0

    def test_color_string_format(self):
        """Test that color strings are in valid Rich style formats."""
        colors = ThemeColors()

        # Valid Rich style formats
        valid_prefixes = ["bold ", "dim ", "italic ", "underline "]
        valid_colors = [
            "red",
            "green",
            "blue",
            "cyan",
            "magenta",
            "yellow",
            "white",
            "black",
        ]

        for attr_name in colors.__dict__:
            color = getattr(colors, attr_name)
            assert isinstance(color, str)
            assert len(color) > 0

            # Should be either a named color, RGB color, or with modifier
            is_valid = any(color == valid_color for valid_color in valid_colors)
            is_valid = is_valid or any(
                color.startswith(prefix) for prefix in valid_prefixes
            )
            is_valid = is_valid or color.startswith("#")  # Hex colors

            assert is_valid, f"Invalid color format '{color}' for {attr_name}"

    def test_custom_color_assignment(self):
        """Test that custom colors can be assigned."""
        custom_colors = ThemeColors(
            error_style="bold #ff0000",
            success_style="#00ff00",
            spinner_style="bold #0000ff",
        )

        assert custom_colors.error_style == "bold #ff0000"
        assert custom_colors.success_style == "#00ff00"
        assert custom_colors.spinner_style == "bold #0000ff"

        # Default values should be used for unspecified colors
        assert custom_colors.warning_style != ""  # Has default


class TestTheme:
    """Test Theme model functionality."""

    def test_theme_creation(self):
        """Test basic theme creation with required fields."""
        colors = ThemeColors()
        theme = Theme(
            name="test-theme",
            display_name="Test Theme",
            description="A test theme for testing",
            colors=colors,
        )

        assert theme.name == "test-theme"
        assert theme.display_name == "Test Theme"
        assert theme.description == "A test theme for testing"
        assert theme.colors == colors

    def test_theme_serialization(self):
        """Test theme can be serialized to dict and back."""
        colors = ThemeColors()
        theme = Theme(
            name="test-theme",
            display_name="Test Theme",
            description="A test theme",
            colors=colors,
        )

        model_dict = theme.model_dump()

        # Check required fields are present
        assert "name" in model_dict
        assert "display_name" in model_dict
        assert "description" in model_dict
        assert "colors" in model_dict

        # Check can deserialize back
        parsed_theme = Theme.model_validate(model_dict)
        assert parsed_theme.name == theme.name
        assert parsed_theme.display_name == theme.display_name
        assert parsed_theme.colors.error_style == theme.colors.error_style

    def test_theme_with_custom_colors(self):
        """Test theme with custom color configuration."""
        custom_colors = {
            "error_style": "bold #ff0000",
            "success_style": "#00ff00",
            "spinner_style": "bold #0000ff",
        }

        theme = Theme(
            name="custom-theme",
            display_name="Custom Theme",
            description="A custom theme",
            colors=custom_colors,
        )

        assert theme.colors.error_style == "bold #ff0000"
        assert theme.colors.success_style == "#00ff00"
        assert theme.colors.spinner_style == "bold #0000ff"

        # Default values should be present for unspecified colors
        assert theme.colors.warning_style != ""

    def test_theme_validation_basic(self):
        """Test theme doesn't crash with valid data."""
        colors = ThemeColors()

        # Should work with valid data
        theme = Theme(
            name="test", display_name="Test", description="A test", colors=colors
        )

        # Should have all required attributes
        assert theme.name == "test"
        assert theme.display_name == "Test"
        assert theme.description == "A test"
        assert theme.colors is not None

    def test_theme_name_validation(self):
        """Test theme name follows expected format."""
        colors = ThemeColors()

        # Valid names
        names = ["simple", "with-dash", "with_underscore", "numeric123"]
        for name in names:
            theme = Theme(
                name=name, display_name="Test", description="Test", colors=colors
            )
            assert theme.name == name
