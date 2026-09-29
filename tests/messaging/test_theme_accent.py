"""Explicit palette RGB must win over terminal ANSI and Rich remaps."""

import json

from rich.console import Console
from rich.text import Text

from code_puppy.messaging.theme_accent import agent_accent, agent_accent_sgr
from code_puppy.messaging.tool_output import format_tool_call
from code_puppy.messaging.status_line import render_status_line


def test_sunset_uses_dark_red_not_normal_blue_purple(monkeypatch):
    palette = ["#000000"] * 16
    palette[4] = "#7d3c98"
    palette[12] = "#a93226"
    monkeypatch.setattr(
        "code_puppy.config.get_value", lambda key: json.dumps({"ansi": palette})
    )
    assert agent_accent() == "#a93226"
    assert agent_accent_sgr() == "38;2;169;50;38"
    tool = format_tool_call("grep", {"pattern": "hello"})
    console = Console()
    for offset in (0, tool.plain.index("pattern")):
        assert tool.get_style_at_offset(console, offset).color.triplet == (169, 50, 38)
    status = Text.from_ansi(
        render_status_line("Streamed ~3,209 tokens | Working", "", 80)
    )
    assert status.get_style_at_offset(
        console, status.plain.index("3,209")
    ).color.triplet == (169, 50, 38)


def test_invalid_palette_falls_back(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: "invalid")
    assert agent_accent() == "bright_blue"
    assert agent_accent_sgr() == "94"
