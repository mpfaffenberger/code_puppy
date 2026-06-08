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
