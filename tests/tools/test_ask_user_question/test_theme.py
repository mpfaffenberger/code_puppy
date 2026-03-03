"""Tests for ask_user_question theme module."""

from unittest.mock import patch

from code_puppy.tools.ask_user_question.theme import (
    RichColors,
    TUIColors,
    _apply_config_overrides,
    _get_config_value,
    get_rich_colors,
    get_tui_colors,
)


class TestTUIColors:
    """Tests for TUIColors defaults."""

    def test_defaults(self):
        c = TUIColors()
        assert c.header_bold == "bold cyan"
        assert c.header_dim == "fg:ansicyan dim"
        assert c.cursor_active == "fg:ansigreen bold"
        assert c.cursor_inactive == "fg:ansiwhite"
        assert c.selected == "fg:ansicyan"
        assert c.selected_check == "fg:ansigreen"
        assert c.text_normal == ""
        assert c.text_dim == "fg:ansiwhite dim"
        assert c.text_warning == "fg:ansiyellow bold"
        assert c.help_key == "fg:ansigreen"
        assert c.help_text == "fg:ansiwhite dim"
        assert c.error == "fg:ansired"


class TestRichColors:
    """Tests for RichColors defaults."""

    def test_defaults(self):
        c = RichColors()
        assert c.header == "bold cyan"
        assert c.progress == "dim"
        assert c.cursor == "green bold"
        assert c.selected == "cyan"
        assert c.description == "dim"
        assert c.input_label == "bold yellow"
        assert c.input_text == "green"
        assert c.input_hint == "dim"
        assert c.help_border == "bold cyan"
        assert c.help_title == "bold cyan"
        assert c.help_section == "bold"
        assert c.help_key == "green"
        assert c.help_close == "dim"
        assert c.timeout_warning == "bold yellow"


class TestGetConfigValue:
    """Tests for _get_config_value."""

    def test_import_error_returns_none(self):
        import code_puppy.tools.ask_user_question.theme as theme_mod

        # Reset cached getter
        old = theme_mod._config_getter
        theme_mod._config_getter = None
        try:
            with patch.dict("sys.modules", {"code_puppy.config": None}):
                # Force re-import failure
                theme_mod._config_getter = None
                result = _get_config_value("anything")
                assert result is None
        finally:
            theme_mod._config_getter = old

    def test_uses_config_get_value(self):
        import code_puppy.tools.ask_user_question.theme as theme_mod

        old = theme_mod._config_getter
        theme_mod._config_getter = None
        try:

            def mock_get(key):
                return f"val_{key}"

            with patch("code_puppy.tools.ask_user_question.theme._config_getter", None):
                with patch("code_puppy.config.get_value", mock_get):
                    theme_mod._config_getter = None
                    result = _get_config_value("test_key")
                    assert result == "val_test_key"
        finally:
            theme_mod._config_getter = old


class TestApplyConfigOverrides:
    """Tests for _apply_config_overrides."""

    def test_no_overrides_returns_default(self):
        default = TUIColors()
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value=None,
        ):
            result = _apply_config_overrides(default, {"header_bold": "some_key"})
        assert result is default

    def test_with_overrides(self):
        default = TUIColors()
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value="red bold",
        ):
            result = _apply_config_overrides(default, {"header_bold": "some_key"})
        assert result.header_bold == "red bold"
        assert result.cursor_active == default.cursor_active  # unchanged

    def test_empty_string_not_applied(self):
        """Empty string is falsy, so it should not override."""
        default = TUIColors()
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value="",
        ):
            result = _apply_config_overrides(default, {"header_bold": "key"})
        assert result is default


class TestGetTuiColors:
    def test_returns_tui_colors(self):
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value=None,
        ):
            result = get_tui_colors()
        assert isinstance(result, TUIColors)

    def test_applies_overrides(self):
        def fake_config(key):
            if key == "tui_header_color":
                return "magenta"
            return None

        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            side_effect=fake_config,
        ):
            result = get_tui_colors()
        assert result.header_bold == "magenta"


class TestGetRichColors:
    def test_returns_rich_colors(self):
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value=None,
        ):
            result = get_rich_colors()
        assert isinstance(result, RichColors)

    def test_applies_overrides(self):
        def fake_config(key):
            if key == "tui_rich_header_color":
                return "yellow"
            return None

        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            side_effect=fake_config,
        ):
            result = get_rich_colors()
        assert result.header == "yellow"
