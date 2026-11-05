"""Thinking shares Termflow Markdown rendering, but stays dim and separated."""

import importlib
import io
import re

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent
from pydantic_ai.messages import TextPart, ThinkingPart, ThinkingPartDelta
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
        # Structured thinking renders in Termflow's dim think box, the
        # same rendering as <think> blocks embedded in assistant text.
        assert plain.count("┌── thinking ──") == 1
        assert "● Thinking" not in plain
        assert "│ Finishing efficiently" in plain
        assert "└──" in plain
        assert "**" not in plain
        assert "\x1b[2m" in rendered
        assert plain.endswith("\n\n")


@pytest.mark.asyncio
async def test_structured_thinking_matches_embedded_think_block(monkeypatch):
    """ThinkingPart output and text-embedded <think> render identical boxes."""
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    monkeypatch.setattr(handler, "get_streaming_console", lambda: console)
    monkeypatch.setattr(handler, "_should_suppress_output", lambda: False)
    monkeypatch.setattr(handler, "_suppress_thinking_stream", lambda: False)
    monkeypatch.setattr(handler, "_fire_stream_event", lambda *args: None)
    monkeypatch.setattr(handler, "is_subagent", lambda: True)
    thinking = ThinkingPart(content="Calibrating the flux capacitor")
    text = TextPart(content="<think>\nCalibrating the flux capacitor\n</think>")

    async def events():
        yield PartStartEvent(index=0, part=thinking)
        yield PartEndEvent(index=0, part=thinking)
        yield PartStartEvent(index=1, part=text)
        yield PartEndEvent(index=1, part=text)

    await handler.event_stream_handler(None, events())
    plain = ANSI.sub("", output.getvalue())
    assert plain.count("┌── thinking ──") == 2
    assert plain.count("│ Calibrating the flux capacitor") == 2
    assert plain.count("└──") == 2
    assert "<think>" not in plain


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_end", [True, False])
@pytest.mark.parametrize(
    "chunks",
    [
        ["First paragraph\n\nSecond paragraph\n\n"],
        ["First paragraph", "\n", "\nSecond", " paragraph", "\n", " \n\t"],
    ],
)
async def test_thinking_trims_only_trailing_whitespace(
    monkeypatch, explicit_end, chunks
):
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=80)
    monkeypatch.setattr(handler, "get_streaming_console", lambda: console)
    monkeypatch.setattr(handler, "_should_suppress_output", lambda: False)
    monkeypatch.setattr(handler, "_suppress_thinking_stream", lambda: False)
    monkeypatch.setattr(handler, "_fire_stream_event", lambda *args: None)
    monkeypatch.setattr(handler, "is_subagent", lambda: True)
    part = ThinkingPart(content=chunks[0])

    async def events():
        yield PartStartEvent(index=0, part=part)
        for chunk in chunks[1:]:
            yield PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta=chunk))
        if explicit_end:
            yield PartEndEvent(index=0, part=part)

    await handler.event_stream_handler(None, events())
    plain = ANSI.sub("", output.getvalue())
    assert "│ First paragraph\n│ \n│ Second paragraph\n└──" in plain


def test_dim_survives_markdown_resets_and_does_not_leak():
    output = io.StringIO()
    writer = DimWriter(output)
    text = "\x1b[1mbold\x1b[0m normal\x1b[22m text"
    assert writer.write(text) == len(text)
    assert "\x1b[0m\x1b[2m normal" in output.getvalue()
    assert "\x1b[22m\x1b[2m text" in output.getvalue()
    assert output.getvalue().endswith("\x1b[0m")
