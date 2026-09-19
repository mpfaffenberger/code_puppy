"""Thinking shares Termflow Markdown rendering, but stays dim and separated."""

import importlib
import io
import re

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent
from pydantic_ai.messages import ThinkingPart, ThinkingPartDelta
from rich.console import Console

from code_puppy.agents.thinking_output import DimWriter

handler = importlib.import_module("code_puppy.agents.event_stream_handler")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_end", [True, False])
@pytest.mark.parametrize("suppressed", [True, False])
async def test_thinking_markdown(monkeypatch, explicit_end, suppressed):
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    monkeypatch.setattr(handler, "get_streaming_console", lambda: console)
    monkeypatch.setattr(handler, "_should_suppress_output", lambda: False)
    monkeypatch.setattr(handler, "_suppress_thinking_stream", lambda: suppressed)
    monkeypatch.setattr(handler, "_fire_stream_event", lambda *args: None)
    monkeypatch.setattr(handler, "is_subagent", lambda: True)
    part = ThinkingPart(content="**Finishing")

    async def events():
        yield PartStartEvent(index=0, part=part)
        yield PartDeltaEvent(
            index=0, delta=ThinkingPartDelta(content_delta=" efficiently**")
        )
        if explicit_end:
            yield PartEndEvent(index=0, part=part)

    await handler.event_stream_handler(None, events())
    rendered = output.getvalue()
    plain = ANSI.sub("", rendered)
    if suppressed:
        assert not plain.strip()
    else:
        assert plain.count("● Thinking") == 1
        assert "Thinking  Finishing efficiently" in plain
        from rich.text import Text
        from code_puppy.messaging.tool_output import format_tool_call

        styled = Text.from_ansi(rendered)
        tool = format_tool_call("read_file", None)
        heading_offset = styled.plain.index("Thinking")
        actual = styled.get_style_at_offset(console, heading_offset)
        expected = tool.get_style_at_offset(console, 2)
        assert actual.color.number == 6
        assert actual.bold == expected.bold
        marker = styled.get_style_at_offset(console, heading_offset - 2)
        assert marker.color.number == 6
        assert tool.get_style_at_offset(console, 0).color.number == 5
        assert not marker.dim
        assert not styled.get_style_at_offset(console, heading_offset).dim
        assert "**" not in plain
        assert "\x1b[2m" in rendered
        assert plain.endswith("\n\n")


def test_dim_survives_markdown_resets_and_does_not_leak():
    output = io.StringIO()
    writer = DimWriter(output)
    text = "\x1b[1mbold\x1b[0m normal\x1b[22m text"
    assert writer.write(text) == len(text)
    assert "\x1b[0m\x1b[2m normal" in output.getvalue()
    assert "\x1b[22m\x1b[2m text" in output.getvalue()
    assert output.getvalue().endswith("\x1b[0m")
