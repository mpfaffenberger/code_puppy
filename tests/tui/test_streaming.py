"""Live response streaming renders inline in the unified scrollback.

The in-progress response is a ``Markdown`` widget mounted as a child of the
``#log`` scroll container and streamed in place (Textual ``MarkdownStream``),
so it reads as one continuous flow with the rest of the conversation. A queue +
async consumer feeds it: the widget is mounted (awaited) before the first
append, so the first delta is never lost.
"""

import asyncio

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


def _start_stream(app):
    """Start a per-turn stream consumer the way _run_agent_turn does."""
    app._streamed_this_turn = False
    app._stream_queue = asyncio.Queue()
    app.run_worker(app._consume_stream(app._stream_queue), group="stream")


def _feed(app, text, delta_type="TextPartDelta"):
    app._on_stream_event(
        "part_delta", {"delta_type": delta_type, "delta": _Delta(text)}
    )


@pytest.mark.asyncio
async def test_text_deltas_stream_formatted_markdown_inline():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _start_stream(app)
        await pilot.pause()
        # Feed the first chunk + more; the first chunk must survive the mount.
        _feed(app, "Rust")
        await pilot.pause(0.05)
        _feed(app, "'s a language with **grammars**\n")
        await pilot.pause(0.1)
        mds = _markdown_children(app)
        assert len(mds) == 1
        assert app._streamed_this_turn is True
        assert (mds[0].source or "").startswith("Rust")


@pytest.mark.asyncio
async def test_thinking_deltas_are_ignored():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _start_stream(app)
        await pilot.pause()
        _feed(app, "hmm\n", delta_type="ThinkingPartDelta")
        await pilot.pause(0.05)
        assert _markdown_children(app) == []
        assert app._streamed_this_turn is False


@pytest.mark.asyncio
async def test_final_response_finalizes_stream_without_duplicating():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _start_stream(app)
        await pilot.pause()
        _feed(app, "streaming...\n")
        await pilot.pause(0.1)
        assert len(_markdown_children(app)) == 1

        # Completion finalizes the existing widget -- no second one mounted.
        app.handle_bus_message(
            AgentResponseMessage(content="streaming...", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert app._stream_queue is None
        assert app._md_stream is None
        assert len(_markdown_children(app)) == 1


@pytest.mark.asyncio
async def test_non_streamed_response_is_mounted():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _start_stream(app)
        await pilot.pause()
        # No stream deltas this turn -> the final response must be mounted.
        app.handle_bus_message(
            AgentResponseMessage(content="**all done**", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert len(_markdown_children(app)) == 1
        assert app._stream_queue is None
