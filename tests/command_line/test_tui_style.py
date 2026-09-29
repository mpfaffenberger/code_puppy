"""Tests for theme-derived termflow menu styling."""

import json
from unittest.mock import patch

from code_puppy.command_line.tui_style import menu_style, themed

MODULE = "code_puppy.command_line.tui_style"


def _palette_json():
    ansi = ["#000000"] * 16
    ansi[12] = "#b06be8"
    ansi[9] = "#ff7fa8"
    return json.dumps({"bg": "#1c0630", "fg": "#f0e3ff", "ansi": ansi})


def test_menu_style_derives_from_persisted_palette():
    with patch(f"{MODULE}.get_value", return_value=_palette_json()):
        style = menu_style()
    assert style is not None
    assert style.bright == "#b06be8"
    assert style.error == "#ff7fa8"
    assert style.dark == "#1c0630"


def test_menu_style_none_without_palette():
    with patch(f"{MODULE}.get_value", return_value=""):
        assert menu_style() is None
    with patch(f"{MODULE}.get_value", return_value="not json{"):
        assert menu_style() is None
    with patch(f"{MODULE}.get_value", side_effect=RuntimeError("no config")):
        assert menu_style() is None


def test_themed_applies_style_only_when_available():
    from termflow.tui import MenuBuilder, MenuItem

    with patch(f"{MODULE}.get_value", return_value=_palette_json()):
        builder = themed(MenuBuilder("t").items([MenuItem("x")]))
    assert builder._kwargs["style"].bright == "#b06be8"

    with patch(f"{MODULE}.get_value", return_value=""):
        builder = themed(MenuBuilder("t").items([MenuItem("x")]))
    assert "style" not in builder._kwargs
