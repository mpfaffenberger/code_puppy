"""Tests for ask-user-question theme callback integration."""

from code_puppy.tools.ask_user_question.theme import RichColors, get_rich_colors


def test_rich_colors_use_muted_role_from_termflow_palette(monkeypatch):
    class FakeStyle:
        grey = "#93a1a1"

    monkeypatch.setattr(
        "code_puppy.command_line.tui_style.menu_style",
        lambda: FakeStyle(),
    )

    colors = get_rich_colors()

    assert colors.progress == "#93a1a1 italic"
    assert colors.question_hint == "#93a1a1 italic"
    assert colors.description == "#93a1a1 italic"
    assert colors.input_hint == "#93a1a1 italic"
    assert colors.help_close == "#93a1a1 italic"


def test_rich_colors_preserve_named_color(monkeypatch):
    class FakeStyle:
        grey = "ansired"

    monkeypatch.setattr(
        "code_puppy.command_line.tui_style.menu_style",
        lambda: FakeStyle(),
    )

    assert get_rich_colors().progress == "ansired italic"


def test_rich_colors_preserve_defaults_for_empty_grey(monkeypatch):
    class FakeStyle:
        grey = ""

    monkeypatch.setattr(
        "code_puppy.command_line.tui_style.menu_style",
        lambda: FakeStyle(),
    )

    assert get_rich_colors() == RichColors()


def test_rich_colors_preserve_defaults_without_plugin_style(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.tui_style.menu_style",
        lambda: None,
    )

    assert get_rich_colors() == RichColors()
