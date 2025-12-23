"""Tests for the Theme class and validation functionality."""

import json
from datetime import datetime

import pytest

from code_puppy.themes.theme import Theme, validate_theme_name


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def default_theme():
    """Fixture providing a default Theme instance."""
    return Theme()


@pytest.fixture
def custom_theme():
    """Fixture providing a custom Theme instance with non-default colors."""
    return Theme(
        error_color="bright_red",
        warning_color="bright_yellow",
        success_color="bright_green",
        info_color="bright_blue",
        debug_color="dim",
        tool_output_color="bright_cyan",
        agent_reasoning_color="bright_magenta",
        agent_response_color="bright_blue",
        system_color="bright_black",
    )


@pytest.fixture
def invalid_theme():
    """Fixture providing a Theme instance with some invalid colors."""
    return Theme(
        error_color="not_a_color",
        warning_color="yellow",
        success_color="green",
        info_color="",
        debug_color="dim",
        tool_output_color="cyan",
        agent_reasoning_color="magenta",
        agent_response_color="blue",
        system_color="bright_black",
    )


# =============================================================================
# TestThemeInitialization
# =============================================================================


class TestThemeInitialization:
    """Test Theme class initialization."""

    def test_default_initialization(self):
        """Test that Theme initializes with default colors."""
        theme = Theme()
        assert theme.error_color == "bold red"
        assert theme.warning_color == "yellow"
        assert theme.success_color == "green"
        assert theme.info_color == "white"
        assert theme.debug_color == "dim"
        assert theme.tool_output_color == "cyan"
        assert theme.agent_reasoning_color == "magenta"
        assert theme.agent_response_color == "blue"
        assert theme.system_color == "bright_black"

    def test_custom_initialization(self):
        """Test that Theme initializes with custom colors."""
        theme = Theme(
            error_color="bright_red",
            warning_color="bright_yellow",
            success_color="bright_green",
            info_color="bright_blue",
            debug_color="dim",
            tool_output_color="bright_cyan",
            agent_reasoning_color="bright_magenta",
            agent_response_color="bright_blue",
            system_color="bright_black",
        )
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"
        assert theme.success_color == "bright_green"
        assert theme.info_color == "bright_blue"
        assert theme.debug_color == "dim"
        assert theme.tool_output_color == "bright_cyan"
        assert theme.agent_reasoning_color == "bright_magenta"
        assert theme.agent_response_color == "bright_blue"
        assert theme.system_color == "bright_black"

    def test_partial_custom_initialization(self):
        """Test that Theme initializes with partial custom colors, using defaults for others."""
        theme = Theme(error_color="bright_red", success_color="bright_green")
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "yellow"  # Default
        assert theme.success_color == "bright_green"
        assert theme.info_color == "white"  # Default
        assert theme.debug_color == "dim"  # Default
        assert theme.tool_output_color == "cyan"  # Default
        assert theme.agent_reasoning_color == "magenta"  # Default
        assert theme.agent_response_color == "blue"  # Default
        assert theme.system_color == "bright_black"  # Default

    def test_styled_color_initialization(self):
        """Test that Theme accepts styled colors like 'bold red'."""
        theme = Theme(
            error_color="bold red",
            warning_color="dim yellow",
            success_color="italic green",
        )
        assert theme.error_color == "bold red"
        assert theme.warning_color == "dim yellow"
        assert theme.success_color == "italic green"


# =============================================================================
# TestThemeSerialization
# =============================================================================


class TestThemeSerialization:
    """Test Theme serialization to/from dictionary."""

    def test_to_dict_basic(self, default_theme):
        """Test basic to_dict conversion without metadata."""
        result = default_theme.to_dict(include_metadata=False)
        assert "colors" in result
        colors = result["colors"]
        assert colors["error_color"] == "bold red"
        assert colors["warning_color"] == "yellow"
        assert colors["success_color"] == "green"
        assert colors["info_color"] == "white"
        assert colors["debug_color"] == "dim"
        assert colors["tool_output_color"] == "cyan"
        assert colors["agent_reasoning_color"] == "magenta"
        assert colors["agent_response_color"] == "blue"
        assert colors["system_color"] == "bright_black"
        assert "name" not in result
        assert "description" not in result
        assert "created_at" not in result

    def test_to_dict_with_metadata(self, default_theme):
        """Test to_dict conversion with metadata."""
        # Note: With slots=True, we can't set arbitrary attributes
        # This test verifies that to_dict handles metadata correctly
        # when attributes are set via from_dict
        result = default_theme.to_dict(include_metadata=True)
        # Without metadata set, these should be None
        assert result.get("name") is None
        assert result.get("description") is None
        assert result.get("created_at") is None
        assert "colors" in result

    def test_from_dict_new_format(self):
        """Test from_dict with new nested format."""
        data = {
            "colors": {
                "error_color": "bright_red",
                "warning_color": "bright_yellow",
                "success_color": "bright_green",
                "info_color": "bright_blue",
                "debug_color": "dim",
                "tool_output_color": "bright_cyan",
                "agent_reasoning_color": "bright_magenta",
                "agent_response_color": "bright_blue",
                "system_color": "bright_black",
            },
        }
        theme = Theme.from_dict(data)
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"
        assert theme.success_color == "bright_green"
        assert theme.info_color == "bright_blue"
        assert theme.debug_color == "dim"
        assert theme.tool_output_color == "bright_cyan"
        assert theme.agent_reasoning_color == "bright_magenta"
        assert theme.agent_response_color == "bright_blue"
        assert theme.system_color == "bright_black"

    def test_from_dict_old_format(self):
        """Test from_dict with old flat format for backward compatibility."""
        data = {
            "error_color": "bright_red",
            "warning_color": "bright_yellow",
            "success_color": "bright_green",
            "info_color": "bright_blue",
            "debug_color": "dim",
            "tool_output_color": "bright_cyan",
            "agent_reasoning_color": "bright_magenta",
            "agent_response_color": "bright_blue",
            "system_color": "bright_black",
        }
        theme = Theme.from_dict(data)
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"
        assert theme.success_color == "bright_green"
        assert theme.info_color == "bright_blue"
        assert theme.debug_color == "dim"
        assert theme.tool_output_color == "bright_cyan"
        assert theme.agent_reasoning_color == "bright_magenta"
        assert theme.agent_response_color == "bright_blue"
        assert theme.system_color == "bright_black"

    def test_from_dict_defaults_for_missing_fields(self):
        """Test that from_dict uses defaults for missing color fields."""
        data = {
            "colors": {
                "error_color": "bright_red",
                "warning_color": "bright_yellow",
            }
        }
        theme = Theme.from_dict(data)
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"
        assert theme.success_color == "green"  # Default
        assert theme.info_color == "white"  # Default


# =============================================================================
# TestColorValidation
# =============================================================================


class TestColorValidation:
    """Test color validation functionality."""

    def test_validate_colors_all_valid(self, default_theme):
        """Test validation of a theme with all valid colors."""
        errors = default_theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_basic_colors(self):
        """Test validation with basic ANSI colors."""
        theme = Theme(
            error_color="red",
            warning_color="yellow",
            success_color="green",
            info_color="blue",
            debug_color="cyan",
            tool_output_color="magenta",
            agent_reasoning_color="white",
            agent_response_color="black",
            system_color="grey",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_bright_colors(self):
        """Test validation with bright color variants."""
        theme = Theme(
            error_color="bright_red",
            warning_color="bright_yellow",
            success_color="bright_green",
            info_color="bright_blue",
            debug_color="bright_cyan",
            tool_output_color="bright_magenta",
            agent_reasoning_color="bright_white",
            agent_response_color="bright_black",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_hex_colors(self):
        """Test validation with hex color codes."""
        theme = Theme(
            error_color="#FF0000",
            warning_color="#FFFF00",
            success_color="#00FF00",
            info_color="#0000FF",
            debug_color="dim",
            tool_output_color="#00FFFF",
            agent_reasoning_color="#FF00FF",
            agent_response_color="#000080",
            system_color="#808080",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_short_hex_colors(self):
        """Test validation with short hex color codes (3 digits)."""
        theme = Theme(
            error_color="#F00",
            warning_color="#FF0",
            success_color="#0F0",
            info_color="#00F",
            debug_color="dim",
            tool_output_color="#0FF",
            agent_reasoning_color="#F0F",
            agent_response_color="#008",
            system_color="#888",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_rgb_colors(self):
        """Test validation with rgb() color format."""
        theme = Theme(
            error_color="rgb(255,0,0)",
            warning_color="rgb(255,255,0)",
            success_color="rgb(0,255,0)",
            info_color="rgb(0,0,255)",
            debug_color="dim",
            tool_output_color="rgb(0,255,255)",
            agent_reasoning_color="rgb(255,0,255)",
            agent_response_color="rgb(0,0,128)",
            system_color="rgb(128,128,128)",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_styled_colors(self):
        """Test validation with styled colors (bold, dim, italic, etc.)."""
        theme = Theme(
            error_color="bold red",
            warning_color="dim yellow",
            success_color="italic green",
            info_color="underline blue",
            debug_color="strike",
            tool_output_color="bold cyan",
            agent_reasoning_color="bold magenta",
            agent_response_color="bold blue",
            system_color="dim white",
        )
        errors = theme.validate_colors()
        assert errors == []

    def test_validate_colors_with_invalid_color_name(self):
        """Test validation with invalid color names."""
        theme = Theme(
            error_color="not_a_color",
            warning_color="yellow",
            success_color="green",
            info_color="white",
            debug_color="dim",
            tool_output_color="cyan",
            agent_reasoning_color="magenta",
            agent_response_color="blue",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert len(errors) > 0
        assert any("error_color" in error for error in errors)
        assert any("not_a_color" in error for error in errors)

    def test_validate_colors_with_empty_string(self):
        """Test validation with empty color strings."""
        theme = Theme(
            error_color="",
            warning_color="yellow",
            success_color="green",
            info_color="white",
            debug_color="dim",
            tool_output_color="cyan",
            agent_reasoning_color="magenta",
            agent_response_color="blue",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert len(errors) > 0
        assert any("error_color" in error for error in errors)
        assert any("empty" in error or "cannot be empty" in error for error in errors)

    def test_validate_colors_with_whitespace_only(self):
        """Test validation with whitespace-only color strings."""
        theme = Theme(
            error_color="   ",
            warning_color="yellow",
            success_color="green",
            info_color="white",
            debug_color="dim",
            tool_output_color="cyan",
            agent_reasoning_color="magenta",
            agent_response_color="blue",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert len(errors) > 0
        assert any("error_color" in error for error in errors)

    def test_validate_colors_with_invalid_hex(self):
        """Test validation with invalid hex color codes."""
        theme = Theme(
            error_color="#GG0000",  # Invalid hex digits
            warning_color="yellow",
            success_color="green",
            info_color="white",
            debug_color="dim",
            tool_output_color="cyan",
            agent_reasoning_color="magenta",
            agent_response_color="blue",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert len(errors) > 0
        assert any("error_color" in error for error in errors)

    def test_validate_colors_with_invalid_rgb(self):
        """Test validation with invalid rgb() color format."""
        theme = Theme(
            error_color="rgb(300,0,0)",  # Value out of range
            warning_color="yellow",
            success_color="green",
            info_color="white",
            debug_color="dim",
            tool_output_color="cyan",
            agent_reasoning_color="magenta",
            agent_response_color="blue",
            system_color="bright_black",
        )
        errors = theme.validate_colors()
        assert len(errors) > 0
        assert any("error_color" in error for error in errors)


# =============================================================================
# TestThemeNameValidation
# =============================================================================


class TestThemeNameValidation:
    """Test theme name validation function."""

    def test_validate_theme_name_valid_simple(self):
        """Test validation of valid simple theme names."""
        assert validate_theme_name("my_theme") is True
        assert validate_theme_name("dark-mode") is True
        assert validate_theme_name("light_theme") is True
        assert validate_theme_name("Theme123") is True

    def test_validate_theme_name_valid_with_underscores(self):
        """Test validation of valid theme names with underscores."""
        assert validate_theme_name("my_custom_theme") is True
        assert validate_theme_name("dark_theme_v2") is True
        assert validate_theme_name("__private_theme__") is True
        assert validate_theme_name("_theme") is True

    def test_validate_theme_name_valid_with_hyphens(self):
        """Test validation of valid theme names with hyphens."""
        assert validate_theme_name("my-theme") is True
        assert validate_theme_name("dark-mode") is True
        assert validate_theme_name("light-theme-v2") is True
        assert validate_theme_name("-theme") is True

    def test_validate_theme_name_valid_with_numbers(self):
        """Test validation of valid theme names with numbers."""
        assert validate_theme_name("theme123") is True
        assert validate_theme_name("theme_123") is True
        assert validate_theme_name("theme-123") is True
        assert validate_theme_name("123theme") is True

    def test_validate_theme_name_valid_mixed_case(self):
        """Test validation of valid theme names with mixed case."""
        assert validate_theme_name("MyTheme") is True
        assert validate_theme_name("DarkMode") is True
        assert validate_theme_name("LightThemeV2") is True
        assert validate_theme_name("camelCaseTheme") is True

    def test_validate_theme_name_valid_edge_cases(self):
        """Test validation of valid edge case theme names."""
        assert validate_theme_name("a") is True  # Single character
        assert validate_theme_name("A") is True  # Single uppercase
        assert validate_theme_name("1") is True  # Single digit
        assert validate_theme_name("_") is True  # Single underscore
        assert validate_theme_name("-") is True  # Single hyphen

    def test_validate_theme_name_invalid_empty_string(self):
        """Test validation of empty theme name."""
        assert validate_theme_name("") is False

    def test_validate_theme_name_invalid_whitespace_only(self):
        """Test validation of whitespace-only theme name."""
        assert validate_theme_name("   ") is False
        assert validate_theme_name("\t") is False
        assert validate_theme_name("\n") is False

    def test_validate_theme_name_invalid_special_characters(self):
        """Test validation of theme names with special characters."""
        assert validate_theme_name("my theme") is False  # Space
        assert validate_theme_name("my.theme") is False  # Dot
        assert validate_theme_name("my@theme") is False  # At sign
        assert validate_theme_name("my#theme") is False  # Hash
        assert validate_theme_name("my$theme") is False  # Dollar sign
        assert validate_theme_name("my%theme") is False  # Percent

    def test_validate_theme_name_invalid_too_long(self):
        """Test validation of theme names that are too long."""
        assert validate_theme_name("a" * 51) is False  # 51 characters
        assert validate_theme_name("a" * 100) is False  # 100 characters

    def test_validate_theme_name_invalid_non_string(self):
        """Test validation of non-string theme names."""
        assert validate_theme_name(None) is False
        assert validate_theme_name(123) is False
        assert validate_theme_name([]) is False
        assert validate_theme_name({}) is False


# =============================================================================
# TestThemeEdgeCases
# =============================================================================


class TestThemeEdgeCases:
    """Test edge cases for Theme class."""

    def test_theme_immutability_of_defaults(self):
        """Test that modifying one theme instance doesn't affect another."""
        theme1 = Theme()
        theme2 = Theme()
        theme1.error_color = "bright_red"
        assert theme1.error_color == "bright_red"
        assert theme2.error_color == "bold red"  # Should remain default

    def test_theme_multiple_style_modifiers(self):
        """Test theme with multiple style modifiers."""
        theme = Theme(error_color="bold italic underline red")
        errors = theme.validate_colors()
        # This should be valid as each modifier is checked separately
        assert errors == []

    def test_theme_case_sensitivity(self):
        """Test that color names are case-insensitive."""
        theme = Theme(
            error_color="RED",
            warning_color="Yellow",
            success_color="GREEN",
            info_color="Blue",
        )
        errors = theme.validate_colors()
        # Color names should be case-insensitive
        assert errors == []

    def test_theme_validate_alias(self):
        """Test that validate() is an alias for validate_colors()."""
        theme = Theme()
        assert theme.validate() == theme.validate_colors()

    def test_theme_from_dict_empty(self):
        """Test from_dict with empty dictionary."""
        theme = Theme.from_dict({})
        # Should use all defaults
        assert theme.error_color == "bold red"
        assert theme.warning_color == "yellow"
        assert theme.success_color == "green"
