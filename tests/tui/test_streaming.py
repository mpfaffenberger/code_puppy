"""Phase 2 polish: live token streaming preview."""

import pytest
from textual.widgets import RichLog

from code_puppy.messaging import AgentResponseMessage
from code_puppy.tui.app import build_app


class _Delta:
    def __init__(self, text):
        self.content_delta = text


@pytest.mark.asyncio
async def test_text_deltas_populate_stream_preview():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        stream = app.query_one("#stream", RichLog)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "TextPartDelta", "delta": _Delta("line one\nline two\n")},
        )
        await pilot.pause(0.05)
        assert stream.has_class("visible")
        assert len(stream.lines) >= 2


@pytest.mark.asyncio
async def test_thinking_deltas_are_ignored():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        stream = app.query_one("#stream", RichLog)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "ThinkingPartDelta", "delta": _Delta("hmm\n")},
        )
        await pilot.pause(0.05)
        assert not stream.has_class("visible")


@pytest.mark.asyncio
async def test_final_response_clears_stream_and_writes_log():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        stream = app.query_one("#stream", RichLog)
        log = app.query_one("#log", RichLog)
        app._on_stream_event(
            "part_delta",
            {"delta_type": "TextPartDelta", "delta": _Delta("streaming...\n")},
        )
        await pilot.pause(0.05)
        assert stream.has_class("visible")

        before = len(log.lines)
        app.handle_bus_message(
            AgentResponseMessage(content="**all done**", is_markdown=True)
        )
        await pilot.pause(0.05)
        assert not stream.has_class("visible")
        assert len(log.lines) > before
