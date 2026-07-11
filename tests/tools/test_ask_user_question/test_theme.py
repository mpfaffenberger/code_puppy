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
        assert c.header_bold == "class:tui.header"
        assert c.header_dim == "class:tui.help"
        assert c.cursor_active == "class:tui.success"
        assert c.cursor_inactive == "class:tui.body"
        assert c.selected == "class:tui.selected"
        assert c.selected_check == "class:tui.success"
        assert c.text_normal == "class:tui.body"
        assert c.text_dim == "class:tui.muted"
        assert c.text_warning == "class:tui.warning"
        assert c.help_key == "class:tui.help-key"
        assert c.help_text == "class:tui.help"
        assert c.error == "class:tui.error"
        assert all(style.startswith("class:tui.") for style in c)


class TestRichColors:
    """Tests for RichColors defaults."""

    def test_defaults(self):
        c = RichColors()
        assert c.header == "bold cyan"
        assert c.progress == "italic"
        assert c.cursor == "green bold"
        assert c.selected == "cyan"
        assert c.description == "italic"
        assert c.input_label == "bold yellow"
        assert c.input_text == "green"
        assert c.input_hint == "italic"
        assert c.help_border == "bold cyan"
        assert c.help_title == "bold cyan"
        assert c.help_section == "bold"
        assert c.help_key == "green"
        assert c.help_close == "italic"
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

    def test_legacy_overrides_do_not_bypass_shared_theme(self):
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value="magenta",
        ) as get_config:
            result = get_tui_colors()

        assert result == TUIColors()
        get_config.assert_not_called()


class TestGetRichColors:
    def test_returns_rich_colors(self):
        with patch(
            "code_puppy.tools.ask_user_question.theme._get_config_value",
            return_value=None,
        ):
            result = get_rich_colors()
        assert isinstance(result, RichColors)

    def test_uses_shared_muted_color_in_rich_panel(self):
        with patch(
            "code_puppy.plugins.theme.prompt_toolkit_theme.get_style_rules",
            return_value={"tui.muted": "fg:#586e75"},
        ):
            result = get_rich_colors()

        assert result.description == "#586e75 italic"
        assert result.progress == "#586e75 italic"
        assert result.header == RichColors().header
