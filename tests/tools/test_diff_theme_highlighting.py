"""Theme propagation tests for file-modification diff syntax highlighting."""

from types import SimpleNamespace

from rich.color import Color
from rich.console import Console

from code_puppy.tools.common import _highlight_code_line


class _ThemedHighlighter:
    def highlight_line(self, code: str, language: str) -> str:
        assert language == "python"
        return f"\x1b[38;2;12;34;56m{code}\x1b[0m"


def test_diff_syntax_uses_termflow_theme_callback(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.callbacks.on_termflow_highlighter",
        lambda _default: _ThemedHighlighter(),
    )
    lexer = SimpleNamespace(aliases=["python"])

    result = _highlight_code_line("return 42", "#102030", lexer)
    rendered_style = result.get_style_at_offset(Console(), 0)

    assert result.plain == "return 42"
    assert rendered_style.color == Color.from_rgb(12, 34, 56)
    assert rendered_style.bgcolor == Color.parse("#102030")


def test_diff_syntax_applies_theme_line_tints(monkeypatch):
    highlighter = _ThemedHighlighter()
    highlighter.diff_line_tints = {
        "added": (10, 20, 30),
        "removed": (-5, -10, -15),
    }
    monkeypatch.setattr(
        "code_puppy.callbacks.on_termflow_highlighter",
        lambda _default: highlighter,
    )
    lexer = SimpleNamespace(aliases=["python"])

    added = _highlight_code_line("added", "#102030", lexer, "added")
    removed = _highlight_code_line("removed", "#301020", lexer, "removed")

    console = Console()
    assert (
        added.get_style_at_offset(console, 0).color.triplet
        == Color.from_rgb(22, 54, 86).triplet
    )
    assert (
        removed.get_style_at_offset(console, 0).color.triplet
        == Color.from_rgb(7, 24, 41).triplet
    )
