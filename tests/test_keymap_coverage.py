"""Test coverage for code_puppy/keymap.py.

This module tests keyboard shortcut configuration including:
- Cancel agent key retrieval and validation
- Character code mapping
- Display name formatting
- Windows platform defaults
"""

from unittest.mock import patch

import pytest

from code_puppy.keymap import (
    DEFAULT_CANCEL_AGENT_KEY,
    KEY_CODES,
    VALID_CANCEL_KEYS,
    KeymapError,
    sigint_fallback_cancels,
    get_cancel_agent_char_code,
    get_cancel_agent_display_name,
    get_cancel_agent_key,
    validate_cancel_agent_key,
)


class TestKeymapConstants:
    """Test keymap constants are properly defined."""

    def test_key_codes_contains_ctrl_keys(self):
        """KEY_CODES should contain all ctrl+letter combinations."""
        assert "ctrl+c" in KEY_CODES
        assert "ctrl+k" in KEY_CODES
        assert "ctrl+q" in KEY_CODES
        assert "escape" in KEY_CODES

    def test_key_codes_values_are_control_chars(self):
        """KEY_CODES values should be control characters."""
        assert KEY_CODES["ctrl+c"] == "\x03"
        assert KEY_CODES["ctrl+k"] == "\x0b"
        assert KEY_CODES["escape"] == "\x1b"

    def test_valid_cancel_keys_is_subset_of_key_codes(self):
        """All valid cancel keys should exist in KEY_CODES."""
        for key in VALID_CANCEL_KEYS:
            assert key in KEY_CODES

    def test_default_cancel_agent_key_is_valid(self):
        """Default cancel key should be in valid keys."""
        assert DEFAULT_CANCEL_AGENT_KEY in VALID_CANCEL_KEYS


class TestKeymapError:
    """Test KeymapError exception."""

    def test_keymap_error_is_exception(self):
        """KeymapError should be an Exception subclass."""
        assert issubclass(KeymapError, Exception)

    def test_keymap_error_with_message(self):
        """KeymapError should preserve error message."""
        error = KeymapError("Invalid key configuration")
        assert str(error) == "Invalid key configuration"

    def test_keymap_error_can_be_raised(self):
        """KeymapError should be raisable."""
        with pytest.raises(KeymapError, match="test error"):
            raise KeymapError("test error")


class TestGetCancelAgentKey:
    """Test get_cancel_agent_key function."""

    @patch("code_puppy.config.get_value")
    def test_returns_default_when_config_is_none(self, mock_get_value):
        """Should return default (ctrl+c) when config value is None —
        on every platform."""
        mock_get_value.return_value = None

        result = get_cancel_agent_key()

        assert result == DEFAULT_CANCEL_AGENT_KEY

    @patch("code_puppy.config.get_value")
    def test_returns_default_when_config_is_empty(self, mock_get_value):
        """Should return default when config value is empty string."""
        mock_get_value.return_value = "   "  # Whitespace only

        result = get_cancel_agent_key()

        assert result == DEFAULT_CANCEL_AGENT_KEY

    @patch("code_puppy.keymap._is_windows")
    @patch("code_puppy.config.get_value")
    def test_windows_default_is_ctrl_c(self, mock_get_value, mock_is_windows):
        """Windows: unconfigured default is ctrl+c too — raw \\x03 via
        the key listener, with buffer-first absorption. Ctrl+K stays
        the editor's kill-to-end."""
        mock_is_windows.return_value = True
        mock_get_value.return_value = None

        result = get_cancel_agent_key()

        assert result == "ctrl+c"

    @patch("code_puppy.config.get_value")
    def test_explicit_config_beats_default(self, mock_get_value):
        """An explicit cancel_agent_key in puppy.cfg beats the default."""
        mock_get_value.return_value = "ctrl+q"

        result = get_cancel_agent_key()

        assert result == "ctrl+q"

    @patch("code_puppy.config.get_value")
    def test_returns_configured_key_normalized(self, mock_get_value):
        """Should return configured key, stripped and lowercased."""
        mock_get_value.return_value = "  CTRL+K  "  # With whitespace and uppercase

        result = get_cancel_agent_key()

        assert result == "ctrl+k"


class TestValidateCancelAgentKey:
    """Test validate_cancel_agent_key function."""

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_valid_key_does_not_raise(self, mock_get_key):
        """Should not raise for valid keys."""
        for key in VALID_CANCEL_KEYS:
            mock_get_key.return_value = key
            # Should not raise
            validate_cancel_agent_key()

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_invalid_key_raises_keymap_error(self, mock_get_key):
        """Should raise KeymapError for invalid keys."""
        mock_get_key.return_value = "ctrl+z"  # Not in VALID_CANCEL_KEYS

        with pytest.raises(KeymapError) as exc_info:
            validate_cancel_agent_key()

        assert "ctrl+z" in str(exc_info.value)
        assert "Invalid cancel_agent_key" in str(exc_info.value)

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_error_message_lists_valid_options(self, mock_get_key):
        """Error message should list valid key options."""
        mock_get_key.return_value = "invalid"

        with pytest.raises(KeymapError) as exc_info:
            validate_cancel_agent_key()

        error_msg = str(exc_info.value)
        # Check that at least some valid keys are mentioned
        assert "ctrl+c" in error_msg or "ctrl+k" in error_msg


class TestSigintFallbackCancels:
    """Test sigint_fallback_cancels function.

    Ctrl+C is a pure keybinding everywhere — the key listener always
    owns cancel. This function only decides whether an OUT-OF-BAND
    SIGINT (kill -INT, piped stdin, cooked-mode gaps) cancels the run.
    """

    @patch("code_puppy.keymap._is_windows")
    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_true_for_ctrl_c_on_posix(self, mock_get_key, mock_is_windows):
        """Fallback SIGINT cancels when ^C IS the cancel gesture (POSIX)."""
        mock_get_key.return_value = "ctrl+c"
        mock_is_windows.return_value = False

        result = sigint_fallback_cancels()

        assert result is True

    @patch("code_puppy.keymap._is_windows")
    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_false_for_ctrl_c_on_windows(self, mock_get_key, mock_is_windows):
        """Windows never routes cancel through SIGINT — the console runs
        with processed input stripped, so ^C arrives as a raw byte for
        the key listener; a SIGINT means the console mode regressed and
        earns repair (reset + re-clamp), not a cancel."""
        mock_get_key.return_value = "ctrl+c"
        mock_is_windows.return_value = True

        result = sigint_fallback_cancels()

        assert result is False

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_false_for_ctrl_k(self, mock_get_key):
        """A SIGINT is not the cancel gesture when cancel is remapped."""
        mock_get_key.return_value = "ctrl+k"

        result = sigint_fallback_cancels()

        assert result is False

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_false_for_ctrl_q(self, mock_get_key):
        """A SIGINT is not the cancel gesture when cancel is remapped."""
        mock_get_key.return_value = "ctrl+q"

        result = sigint_fallback_cancels()

        assert result is False


class TestGetCancelAgentCharCode:
    """Test get_cancel_agent_char_code function."""

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_correct_char_code_for_ctrl_c(self, mock_get_key):
        """Should return correct character code for ctrl+c."""
        mock_get_key.return_value = "ctrl+c"

        result = get_cancel_agent_char_code()

        assert result == "\x03"

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_returns_correct_char_code_for_ctrl_k(self, mock_get_key):
        """Should return correct character code for ctrl+k."""
        mock_get_key.return_value = "ctrl+k"

        result = get_cancel_agent_char_code()

        assert result == "\x0b"

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_raises_for_unknown_key(self, mock_get_key):
        """Should raise KeymapError for unknown key."""
        mock_get_key.return_value = "unknown_key"

        with pytest.raises(KeymapError) as exc_info:
            get_cancel_agent_char_code()

        assert "unknown_key" in str(exc_info.value)
        assert "no character code mapping" in str(exc_info.value)


class TestGetCancelAgentDisplayName:
    """Test get_cancel_agent_display_name function."""

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_formats_ctrl_c_correctly(self, mock_get_key):
        """Should format ctrl+c as Ctrl+C."""
        mock_get_key.return_value = "ctrl+c"

        result = get_cancel_agent_display_name()

        assert result == "Ctrl+C"

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_formats_ctrl_k_correctly(self, mock_get_key):
        """Should format ctrl+k as Ctrl+K."""
        mock_get_key.return_value = "ctrl+k"

        result = get_cancel_agent_display_name()

        assert result == "Ctrl+K"

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_formats_escape_correctly(self, mock_get_key):
        """Should format escape as ESCAPE."""
        mock_get_key.return_value = "escape"

        result = get_cancel_agent_display_name()

        assert result == "ESCAPE"

    @patch("code_puppy.keymap.get_cancel_agent_key")
    def test_formats_other_keys_uppercase(self, mock_get_key):
        """Should uppercase non-ctrl keys."""
        mock_get_key.return_value = "somekey"

        result = get_cancel_agent_display_name()

        assert result == "SOMEKEY"
