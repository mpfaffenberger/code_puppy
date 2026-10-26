"""Tool chrome follows the theme's agent-name ANSI palette slot."""

from rich.console import Console

from code_puppy.messaging.tool_output import format_tool_call


def test_tool_bullet_and_argument_keys_use_agent_accent():
    summary = format_tool_call("read_file", {"file_path": "example.py"})
    console = Console()
    for offset in (0, summary.plain.index("file_path")):
        style = summary.get_style_at_offset(console, offset)
        assert style.color.number == 12
        assert style.bgcolor is None
    assert summary.get_style_at_offset(console, summary.plain.index("example.py")).dim
