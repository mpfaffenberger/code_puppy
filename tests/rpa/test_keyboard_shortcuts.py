"""Tests for keyboard shortcuts module.

These tests verify keyboard shortcut functionality with mocked keyboard inputs.
No real keyboard events are sent during testing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Only import if pyautogui is available
try:
    from code_puppy.tools.rpa.keyboard_shortcuts import (
        parse_shortcut,
        validate_shortcut,
    )
    SHORTCUTS_AVAILABLE = True
except ImportError:
    SHORTCUTS_AVAILABLE = False


@pytest.mark.skipif(not SHORTCUTS_AVAILABLE, reason="keyboard_shortcuts not available")
class TestParseShortcut:
    """Test shortcut parsing."""

    def test_parse_single_key(self):
        """Test parsing single key."""
        modifiers, key = parse_shortcut("a")
        assert modifiers == []
        assert key == "a"

    def test_parse_ctrl_key(self):
        """Test parsing Ctrl+key."""
        modifiers, key = parse_shortcut("ctrl+c")
        assert "ctrl" in modifiers
        assert key == "c"

    def test_parse_cmd_key(self):
        """Test parsing Cmd+key."""
        modifiers, key = parse_shortcut("cmd+s")
        assert "cmd" in modifiers or "command" in modifiers
        assert key == "s"

    def test_parse_shift_key(self):
        """Test parsing Shift+key."""
        modifiers, key = parse_shortcut("shift+a")
        assert "shift" in modifiers
        assert key == "a"

    def test_parse_alt_key(self):
        """Test parsing Alt+key."""
        modifiers, key = parse_shortcut("alt+f4")
        assert "alt" in modifiers
        assert key == "f4"

    def test_parse_multiple_modifiers(self):
        """Test parsing multiple modifiers."""
        modifiers, key = parse_shortcut("ctrl+shift+s")
        assert "ctrl" in modifiers
        assert "shift" in modifiers
        assert key == "s"

    def test_parse_case_insensitive(self):
        """Test parsing is case-insensitive."""
        modifiers1, key1 = parse_shortcut("CTRL+C")
        modifiers2, key2 = parse_shortcut("ctrl+c")
        assert set(modifiers1) == set(modifiers2)
        assert key1.lower() == key2.lower()

    def test_parse_whitespace_handling(self):
        """Test parsing handles whitespace."""
        modifiers, key = parse_shortcut(" ctrl + c ")
        assert "ctrl" in modifiers
        assert key == "c"


@pytest.mark.skipif(not SHORTCUTS_AVAILABLE, reason="keyboard_shortcuts not available")
class TestValidateShortcut:
    """Test shortcut validation."""

    def test_validate_valid_shortcut(self):
        """Test validating valid shortcut."""
        assert validate_shortcut("ctrl+c") is True

    def test_validate_single_key(self):
        """Test validating single key."""
        assert validate_shortcut("a") is True

    def test_validate_function_key(self):
        """Test validating function keys."""
        assert validate_shortcut("f1") is True
        assert validate_shortcut("f12") is True

    def test_validate_special_keys(self):
        """Test validating special keys."""
        assert validate_shortcut("enter") is True
        assert validate_shortcut("escape") is True
        assert validate_shortcut("tab") is True
        assert validate_shortcut("space") is True

    def test_validate_empty_shortcut(self):
        """Test validating empty shortcut."""
        assert validate_shortcut("") is False

    def test_validate_invalid_modifier(self):
        """Test validating invalid modifier."""
        assert validate_shortcut("invalid+c") is False

    def test_validate_only_modifiers(self):
        """Test validating shortcut with only modifiers."""
        assert validate_shortcut("ctrl+shift") is False
