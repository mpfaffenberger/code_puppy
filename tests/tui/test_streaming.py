"""Live response streaming renders inline in the unified scrollback.

The in-progress response is a ``Markdown`` widget mounted as a child of the
``#log`` scroll container and streamed in place (Textual ``MarkdownStream``),
so it reads as one continuous flow with the rest of the conversation. There is
no separate streaming region; on completion the widget simply stays as history.
"""

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from code_puppy.messaging import AgentResponseMessage
from code_puppy.tui.app import build_app


class _Delta:
    def __init__(self, text):
        self.content_delta = text


def _markdown_children(app):
    return list(app.query_one("#log", VerticalScroll).query(Markdown))


@pytest.mark.asyncio
async def test_text_deltas_stream_formatted_markdown_inline():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._on_stream_event(
            "part_delta",
            {
                "delta_type": "TextPartDelta",
                "delta": _Delta("## hi\n\nsome **text**\n"),
            },
        )
        await pilot.pause(0.1)
        # A markdown widget is mounted inline in the scrollback and accumulates.
        mds = _markdown_children(app)
        assert len(mds) == 1
        assert app._streamed_this_turn is True
        assert app._md_stream is not None
        assert "some" in (mds[0].source or "")


@pytest.mark.asyncio
async def test_thinking_deltas_are_ignored():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._on_stream_event(
            "part_delta",
            {"delta_type": "ThinkingPartDelta", "delta": _Delta("hmm\n")},
        )
        await pilot.pause(0.05)
        assert _markdown_children(app) == []
        assert app._md_stream is None


@pytest.mark.asyncio
async def test_final_response_finalizes_stream_without_duplicating():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._on_stream_event(
            "part_delta",
            {"delta_type": "TextPartDelta", "delta": _Delta("streaming...\n")},
        )
        await pilot.pause(0.1)
        assert len(_markdown_children(app)) == 1

        # The streamed response is already shown; completion just finalizes it
        # (no second markdown widget mounted).
        app.handle_bus_message(
            AgentResponseMessage(content="streaming...", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert app._md_stream is None
        assert len(_markdown_children(app)) == 1


@pytest.mark.asyncio
async def test_non_streamed_response_is_mounted():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # No stream deltas this turn -> the final response must be mounted.
        app.handle_bus_message(
            AgentResponseMessage(content="**all done**", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert len(_markdown_children(app)) == 1
