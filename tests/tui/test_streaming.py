"""Live response streaming renders inline -- and stays below tool output.

The in-progress response is a ``Markdown`` widget streamed in place at the
bottom of ``#log`` (nice, formatted, continuous). Its banner is an *anchor*:
while the response streams, any tool output (bus/legacy) mounts ABOVE that
anchor, so the response stays pinned to the bottom and tool output always
lands above it -- deterministic ordering, no cross-channel race, no preview.

Thinking (ThinkingPart) stream into a dim ``Static.thinking-content`` widget
and appear BEFORE the response text, matching interactive-mode order.
"""

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from code_puppy.messaging import AgentResponseMessage, MessageLevel, TextMessage
from code_puppy.tui.app import build_app


class _Delta:
    def __init__(self, text):
        self.content_delta = text


class _Part:
    def __init__(self, content):
        self.content = content


def _feed_start(app, content, index=0, part_type="TextPart"):
    app._on_stream_event(
        "part_start",
        {"index": index, "part_type": part_type, "part": _Part(content)},
    )


def _feed_thinking_start(app, content="", index=0):
    app._on_stream_event(
        "part_start",
        {"index": index, "part_type": "ThinkingPart", "part": _Part(content)},
    )


def _feed_thinking_delta(app, text, index=0):
    app._on_stream_event(
        "part_delta",
        {"index": index, "delta_type": "ThinkingPartDelta", "delta": _Delta(text)},
    )


def _feed_thinking_end(app, index=0):
    app._on_stream_event("part_end", {"index": index})


def _markdown_children(app):
    return list(app.query_one("#log", VerticalScroll).query(Markdown))


def _thinking_content_widgets(app):
    """All Static.thinking-content widgets in the log."""
    return list(app.query_one("#log", VerticalScroll).query("Static.thinking-content"))


def _feed(app, text, delta_type="TextPartDelta", index=None):
    data = {"delta_type": delta_type, "delta": _Delta(text)}
    if index is not None:
        data["index"] = index
    app._on_stream_event("part_delta", data)


def _banner_count(app):
    return app.log_text().count("AGENT RESPONSE")


def _pos(children, marker):
    return next(
        i
        for i, c in enumerate(children)
        if marker in str(getattr(c, "_cp_renderable", ""))
    )


@pytest.mark.asyncio
async def test_text_deltas_stream_inline_markdown():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed(app, "Rust")
        await pilot.pause(0.05)
        _feed(app, "'s a language with **grammars**\n")
        await pilot.pause(0.1)
        mds = _markdown_children(app)
        assert len(mds) == 1
        assert app._streamed_this_turn is True
        assert (mds[0].source or "").startswith("Rust")
        assert _banner_count(app) == 1


@pytest.mark.asyncio
async def test_thinking_suppressed_when_toggle_on(monkeypatch):
    """ThinkingPart events produce no widget when suppress_thinking is True.

    The gate uses a dynamic import inside _on_stream_event so we patch at
    the source module (code_puppy.config), not at the tui module.
    """
    import code_puppy.config as cfg

    monkeypatch.setattr(cfg, "get_suppress_thinking_messages", lambda: True)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "hmm", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.1)
        assert _thinking_content_widgets(app) == []
        assert app._streamed_this_turn is False


@pytest.mark.asyncio
async def test_tool_output_mounts_above_streaming_response():
    """Tool output that arrives while the response streams lands ABOVE it."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Response starts streaming...
        _feed(app, "the answer\n")
        await pilot.pause(0.1)
        # ...then a tool output bus message arrives during streaming.
        app.enqueue_render(
            ("bus", TextMessage(level=MessageLevel.INFO, text="TOOL-OUTPUT-MARKER"))
        )
        await pilot.pause(0.15)

        children = list(app.query_one("#log", VerticalScroll).children)
        mds = _markdown_children(app)
        assert len(mds) == 1
        tool_pos = _pos(children, "TOOL-OUTPUT-MARKER")
        banner_pos = _pos(children, "AGENT RESPONSE")
        md_pos = children.index(mds[0])
        # tool output above the response block (banner + markdown).
        assert tool_pos < banner_pos < md_pos


@pytest.mark.asyncio
async def test_final_response_finalizes_without_duplicating():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed(app, "streaming...\n")
        await pilot.pause(0.1)
        assert len(_markdown_children(app)) == 1

        # Completion finalizes the streamed widget -- no second one mounted.
        app.handle_bus_message(
            AgentResponseMessage(content="streaming...", is_markdown=True)
        )
        await pilot.pause(0.1)
        assert app._md_stream is None
        assert app._response_anchor is None
        assert len(_markdown_children(app)) == 1
        assert _banner_count(app) == 1


@pytest.mark.asyncio
async def test_part_start_initial_content_is_not_dropped():
    """A TextPart's opening text (carried in part_start, not a delta) is kept.

    Regression: the response was truncated at the very start because the
    opening characters arrive in PartStartEvent.part.content, which the TUI
    used to ignore (it only handled part_delta).
    """
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_start(app, "List files ", index=0)  # opening text in part_start
        _feed(app, "deep-dive time!", index=0)  # remainder via deltas
        await pilot.pause(0.1)
        app._finalize_stream()
        await pilot.pause(0.1)
        mds = _markdown_children(app)
        assert len(mds) == 1
        assert (mds[0].source or "") == "List files deep-dive time!"


@pytest.mark.asyncio
async def test_part_start_without_content_is_ignored():
    """A part_start with empty content must not start a stream on its own."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_start(app, "", index=0)
        await pilot.pause(0.05)
        assert app._streamed_this_turn is False
        assert _markdown_children(app) == []


@pytest.mark.asyncio
async def test_multipart_stream_is_lossless_after_finalize():
    """Text parts split by tool calls keep every character (no dropped prefixes).

    Regression: the live incremental render dropped a variable-length prefix
    at each text-part boundary. The committed widget must be rebuilt from the
    lossless accumulation, separating parts with a blank line.
    """
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Part 0 (index 0), then a tool call, then part 1 (index 2).
        _feed(app, "Web serve ", index=0)
        _feed(app, "is the deferred item.", index=0)
        await pilot.pause(0.05)
        app.enqueue_render(("bus", TextMessage(level=MessageLevel.INFO, text="TOOL")))
        await pilot.pause(0.05)
        _feed(app, "No serve ", index=2)
        _feed(app, "impl exists yet.", index=2)
        await pilot.pause(0.1)
        # Finalize the turn (as the AgentResponseMessage would).
        app._finalize_stream()
        await pilot.pause(0.1)

        mds = _markdown_children(app)
        assert len(mds) == 1
        source = mds[0].source or ""
        assert source == "Web serve is the deferred item.\n\nNo serve impl exists yet."
        # No leftover stream state.
        assert app._md_stream is None
        assert app._stream_text == ""


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
        assert app._md_stream is None
        assert _banner_count(app) == 1


# ------------------------------------------------------------------ #
# Thinking stream tests
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_thinking_creates_static_widget():
    """A ThinkingPart start/delta/end cycle mounts a thinking-content Static."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "Let me reason...", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.15)
        widgets = _thinking_content_widgets(app)
        assert len(widgets) == 1
        assert app._streamed_this_turn is False  # thinking != text response


@pytest.mark.asyncio
async def test_thinking_text_accumulated_losslessly():
    """All thinking deltas are present in the final widget content."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "step one. ", index=0)
        _feed_thinking_delta(app, "step two. ", index=0)
        _feed_thinking_delta(app, "step three.", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.15)
        widgets = _thinking_content_widgets(app)
        assert len(widgets) == 1
        rendered = str(getattr(widgets[0], "_cp_renderable", ""))
        assert "step one" in rendered
        assert "step two" in rendered
        assert "step three" in rendered


@pytest.mark.asyncio
async def test_thinking_initial_content_not_dropped():
    """Text in ThinkingPart.content (part_start) is not silently dropped."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_thinking_start(app, content="opening thought", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.15)
        widgets = _thinking_content_widgets(app)
        assert len(widgets) == 1
        rendered = str(getattr(widgets[0], "_cp_renderable", ""))
        assert "opening thought" in rendered


@pytest.mark.asyncio
async def test_thinking_appears_before_response_in_log():
    """The THINKING block lands above the AGENT RESPONSE block in the scrollback."""

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Thinking part first (index 0)
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "I am thinking...", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.1)
        # Then the text response (index 1)
        _feed(app, "Here is my answer.", index=1)
        await pilot.pause(0.1)

        children = list(app.query_one("#log", VerticalScroll).children)
        mds = _markdown_children(app)
        thinking_widgets = _thinking_content_widgets(app)
        assert len(mds) == 1
        assert len(thinking_widgets) == 1

        thinking_pos = children.index(thinking_widgets[0])
        md_pos = children.index(mds[0])
        assert thinking_pos < md_pos, "Thinking must appear before response text"


@pytest.mark.asyncio
async def test_thinking_state_cleared_after_stop():
    """_thinking_widget is None after the part ends (widget stays in scrollback)."""
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "pondering...", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.15)
        assert app._thinking_widget is None
        assert app._thinking_text_acc == ""
        assert app._thinking_pending_deltas == []
        # But the widget is still in the DOM
        assert len(_thinking_content_widgets(app)) == 1


@pytest.mark.asyncio
async def test_second_thinking_block_appears_after_first_response():
    """Two think→respond cycles keep correct DOM order.

    Regression: without the stream-finalisation guard in _start_thinking_stream,
    the second THINKING banner mounted at the absolute bottom -- AFTER the
    already-streaming first response text -- because _md_stream was still open.

    Correct order:
        THINKING1 | response1_text | THINKING2 | response2_text
    """

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()

        # --- Cycle 1: think then respond ---
        _feed_thinking_start(app, index=0)
        _feed_thinking_delta(app, "first thought", index=0)
        _feed_thinking_end(app, index=0)
        await pilot.pause(0.1)

        _feed(app, "first response", index=1)
        await pilot.pause(0.1)

        # --- Cycle 2: think again then respond ---
        _feed_thinking_start(app, index=2)
        _feed_thinking_delta(app, "second thought", index=2)
        _feed_thinking_end(app, index=2)
        await pilot.pause(0.1)

        _feed(app, "second response", index=3)
        await pilot.pause(0.1)

        children = list(app.query_one("#log", VerticalScroll).children)
        mds = _markdown_children(app)
        thinking_widgets = _thinking_content_widgets(app)

        # Both thinking widgets and at least one Markdown widget present.
        assert len(thinking_widgets) == 2
        assert len(mds) >= 1

        t1_pos = children.index(thinking_widgets[0])
        t2_pos = children.index(thinking_widgets[1])

        # The first Markdown widget (response1) is between the two thinking
        # blocks -- not after both of them.
        md_pos = children.index(mds[0])
        assert t1_pos < md_pos < t2_pos, (
            f"Expected THINKING1({t1_pos}) < response({md_pos}) < THINKING2({t2_pos})"
        )
