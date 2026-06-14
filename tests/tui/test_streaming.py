"""Live response streaming: formatted markdown rendered in place.

The in-progress response streams as markdown into a ``Markdown`` widget inside
the ``#stream-scroll`` container (visibility toggled via the ``visible`` class).
On completion it's promoted into the ``#log`` scrollback and the stream hides.
"""

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Markdown, RichLog

from code_puppy.messaging import AgentResponseMessage
from code_puppy.tui.app import build_app


class _Delta:
    def __init__(self, text):
        self.content_delta = text


@pytest.mark.asyncio
async def test_text_deltas_stream_formatted_markdown():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        scroll = app.query_one("#stream-scroll", VerticalScroll)
        widget = app.query_one("#stream", Markdown)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "TextPartDelta", "delta": _Delta("## hi\n\nsome **text**\n")},
        )
        await pilot.pause(0.1)
        assert scroll.has_class("visible")
        assert app._md_stream is not None
        # The streamed text accumulates in the markdown widget's source.
        assert "some" in (widget.source or "")


@pytest.mark.asyncio
async def test_thinking_deltas_are_ignored():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        scroll = app.query_one("#stream-scroll", VerticalScroll)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "ThinkingPartDelta", "delta": _Delta("hmm\n")},
        )
        await pilot.pause(0.05)
        assert not scroll.has_class("visible")
        assert app._md_stream is None


@pytest.mark.asyncio
async def test_final_response_clears_stream_and_writes_log():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        scroll = app.query_one("#stream-scroll", VerticalScroll)
        log = app.query_one("#log", RichLog)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "TextPartDelta", "delta": _Delta("streaming...\n")},
        )
        await pilot.pause(0.1)
        assert scroll.has_class("visible")

        before = len(log.lines)
        app.handle_bus_message(
            AgentResponseMessage(content="**all done**", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert not scroll.has_class("visible")
        assert app._md_stream is None
        assert len(log.lines) > before
