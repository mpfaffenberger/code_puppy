"""Tests for ask-user-question theme callback integration."""

from prompt_toolkit.styles import Style

from code_puppy.tools.ask_user_question.theme import RichColors, get_rich_colors


def test_rich_colors_use_muted_role_from_prompt_toolkit_callback(monkeypatch):
    resolved_style = Style.from_dict({"tui.muted": "fg:#93a1a1"})
    monkeypatch.setattr(
        "code_puppy.callbacks.on_prompt_toolkit_style",
        lambda: resolved_style,
    )

    colors = get_rich_colors()

    assert colors.progress == "93a1a1 italic"
    assert colors.question_hint == "93a1a1 italic"
    assert colors.description == "93a1a1 italic"
    assert colors.input_hint == "93a1a1 italic"
    assert colors.help_close == "93a1a1 italic"


def test_rich_colors_preserve_defaults_without_plugin_style(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.callbacks.on_prompt_toolkit_style",
        lambda: None,
    )

    assert get_rich_colors() == RichColors()
