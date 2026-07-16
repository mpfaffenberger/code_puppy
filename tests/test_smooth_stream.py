"""Tests for the smooth-stream renderers (thinking + termflow typewriter)."""

import asyncio
import io

import pytest
from rich.console import Console

from code_puppy.agents.smooth_stream import (
    SmoothTermflowWriter,
    ThinkingStreamSmoother,
    _split_by_visible,
    make_smooth_termflow_writer,
    make_thinking_smoother,
)


def _plain_console() -> tuple[Console, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=200, no_color=True)
    return console, buf


@pytest.mark.asyncio
async def test_buffered_content_preserved_and_ordered():
    """Bursty feeds should reassemble into identical, in-order output."""
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=0.02)
    sm.start()
    for chunk in ["Hello, ", "this ", "is ", "smooth ", "thinking!"]:
        sm.feed(chunk)
    await sm.close()
    assert buf.getvalue() == "Hello, this is smooth thinking!"


@pytest.mark.asyncio
async def test_emits_in_multiple_smooth_chunks():
    """A single large feed should be drained over multiple console writes."""
    console, _ = _plain_console()
    writes: list[str] = []
    console.print = lambda s, end="": writes.append(str(s))  # type: ignore[assignment]
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=0.05)
    sm.start()
    sm.feed("x" * 200)
    await sm.close()
    # Should be split into several ticks, not dumped in one go.
    assert len(writes) > 3


@pytest.mark.asyncio
async def test_markup_characters_not_interpreted():
    """Markup-looking thinking text must render verbatim, never swallowed."""
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=0.02)
    text = "danger [bold]not markup[/bold] and [red]stuff[/red] done"
    sm.start()
    sm.feed(text)
    await sm.close()
    assert buf.getvalue() == text


@pytest.mark.asyncio
async def test_close_is_safe_without_feed():
    """Closing with nothing buffered shouldn't hang or raise."""
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002)
    sm.start()
    await sm.close()
    assert buf.getvalue() == ""


@pytest.mark.asyncio
async def test_abort_discards_buffer_and_stops_typing():
    """abort() must stop output immediately and drop the backlog."""
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.005, catch_up_seconds=1.0)
    sm.start()
    sm.feed("x" * 10_000)
    await asyncio.sleep(0.02)  # let a few ticks emit
    sm.abort()
    emitted = buf.getvalue()
    await asyncio.sleep(0.05)  # nothing more may print afterwards
    assert buf.getvalue() == emitted
    assert len(emitted) < 10_000


@pytest.mark.asyncio
async def test_cancellation_discards_instead_of_dumping():
    """Cancelling the drain task must NOT flush the backlog to the terminal."""
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.005, catch_up_seconds=1.0)
    sm.start()
    sm.feed("y" * 10_000)
    await asyncio.sleep(0.02)
    sm._task.cancel()
    await asyncio.sleep(0.02)
    assert len(buf.getvalue()) < 10_000


@pytest.mark.asyncio
async def test_pause_suspends_typing_until_resume():
    """Content fed DURING a pause must stay silent until resume."""
    from code_puppy.messaging.pause_controller import (
        get_pause_controller,
        reset_pause_controller,
    )

    reset_pause_controller()
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=0.02)
    sm.start()
    try:
        get_pause_controller().pause()
        sm.feed("quiet please")
        await asyncio.sleep(0.05)
        assert buf.getvalue() == ""
        get_pause_controller().resume()
        await sm.close()
        assert buf.getvalue() == "quiet please"
    finally:
        reset_pause_controller()


@pytest.mark.asyncio
async def test_pause_transition_flushes_tail_atomically():
    """Buffered content from BEFORE the pause flushes in one go at pause time.

    The tail must land before the steering prompt renders, and the buffer
    must be empty so close() can't stall the agent pipeline.
    """
    from code_puppy.messaging.pause_controller import (
        get_pause_controller,
        reset_pause_controller,
    )

    reset_pause_controller()
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=5.0)
    sm.start()
    try:
        sm.feed("tail content " * 50)  # would take ~5s at the steady rate
        await asyncio.sleep(0.01)
        get_pause_controller().pause()
        await asyncio.sleep(0.05)  # a few ticks: transition flush fires
        assert buf.getvalue().endswith("tail content ")
        assert sm._pending == ""
    finally:
        get_pause_controller().resume()
        await sm.close()
        reset_pause_controller()


@pytest.mark.asyncio
async def test_close_does_not_stall_while_paused():
    """Regression: close() during a pause must NOT wait for resume.

    The old behavior held the model's HTTP stream open for the whole pause
    (handler blocked in close() inside ``node.stream``), getting connections
    killed upstream → RemoteProtocolError on the post-steer model call.
    """
    from code_puppy.messaging.pause_controller import (
        get_pause_controller,
        reset_pause_controller,
    )

    reset_pause_controller()
    console, buf = _plain_console()
    sm = ThinkingStreamSmoother(console, tick_interval=0.002, catch_up_seconds=5.0)
    sm.start()
    try:
        sm.feed("x" * 5000)
        await asyncio.sleep(0.01)
        get_pause_controller().pause()
        # NO resume — close() must still finish fast (transition flush
        # empties the buffer; closed + empty exits the drain loop).
        await asyncio.wait_for(sm.close(), timeout=1.0)
        assert "x" * 100 in buf.getvalue()
    finally:
        reset_pause_controller()


def test_make_thinking_smoother_respects_disabled(monkeypatch):
    """make_thinking_smoother returns None when smoothing is toggled off."""
    monkeypatch.setattr("code_puppy.config.get_smooth_thinking_stream", lambda: False)
    console, _ = _plain_console()
    assert make_thinking_smoother(console) is None


def test_make_thinking_smoother_enabled_by_default(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_smooth_thinking_stream", lambda: True)
    console, _ = _plain_console()
    assert isinstance(make_thinking_smoother(console), ThinkingStreamSmoother)


# ── SmoothTermflowWriter ────────────────────────────────────────────────

ESC = "\x1b"
BOLD = f"{ESC}[1m"
RESET = f"{ESC}[0m"


def test_split_by_visible_keeps_ansi_atomic():
    """ANSI sequences must never be split and trailing codes attach greedily."""
    s = f"{BOLD}Hi{RESET}there"
    # Ask for 2 visible chars -> should emit BOLD + 'Hi' + RESET (greedy tail).
    emit, rest, consumed = _split_by_visible(s, 2)
    assert consumed == 2
    assert emit == f"{BOLD}Hi{RESET}"
    assert rest == "there"


@pytest.mark.asyncio
async def test_termflow_writer_preserves_bytes_exactly():
    """Everything written must come out the other side byte-identical."""
    buf = io.StringIO()
    w = SmoothTermflowWriter(buf, tick_interval=0.002, catch_up_seconds=0.02)
    w.start()
    payload = f"{BOLD}Hello{RESET}\nsecond line with {ESC}[31mcolor{RESET}!"
    # Write in lumpy pieces like termflow would.
    w.write(payload[:10])
    w.write(payload[10:25])
    await asyncio.sleep(0.01)
    w.write(payload[25:])
    await w.close()
    assert buf.getvalue() == payload


@pytest.mark.asyncio
async def test_termflow_writer_types_in_multiple_writes():
    """A big write should reach the target in several smaller flushes."""
    target_writes: list[str] = []

    class _Spy:
        def write(self, s):
            target_writes.append(s)
            return len(s)

        def flush(self):
            pass

    w = SmoothTermflowWriter(_Spy(), tick_interval=0.002, catch_up_seconds=0.05)
    w.start()
    w.write("x" * 200)
    await w.close()
    assert len(target_writes) > 3
    assert "".join(target_writes) == "x" * 200


def test_make_smooth_termflow_writer_respects_disabled(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_smooth_response_stream", lambda: False)
    assert make_smooth_termflow_writer(io.StringIO()) is None


def test_make_smooth_termflow_writer_enabled_by_default(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_smooth_response_stream", lambda: True)
    assert isinstance(make_smooth_termflow_writer(io.StringIO()), SmoothTermflowWriter)
