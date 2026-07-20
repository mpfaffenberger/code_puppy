"""Firehose performance benchmarks for the TUI render pipeline.

Phase 5 perf pass: before optimizing blind, MEASURE. These are not strict
pass/fail unit tests -- they hammer the two hot paths and report timings so
we can decide whether coalescing / scrollback-capping is actually needed.

Run with output visible:
    .venv/bin/python -m pytest tests/tui/test_perf_firehose.py -o addopts="" -s -q

Tune the load with env vars (defaults stay CI-friendly):
    CP_PERF_BUS_N      number of firehose bus messages   (default 500)
    CP_PERF_DELTA_N    number of streamed token deltas   (default 2000)

The assertions are deliberately loose (generous wall-clock ceilings) so a
slow CI box doesn't flake; the real signal is the printed report.
"""

import os
import time

import pytest
from textual.containers import VerticalScroll

from code_puppy.messaging import MessageLevel, TextMessage
from code_puppy.tui.app import build_app


def _bus_n() -> int:
    return int(os.environ.get("CP_PERF_BUS_N", "500"))


def _delta_n() -> int:
    return int(os.environ.get("CP_PERF_DELTA_N", "2000"))


def _widget_count(app) -> int:
    return len(app.query_one("#log", VerticalScroll).children)


class _Delta:
    def __init__(self, text):
        self.content_delta = text


def _idle(app) -> bool:
    """True when the render queue AND both batch buffers are fully drained."""
    return app._render_q.empty() and not app._pending and not app._pending_deltas


async def _drain(pilot, app, *, timeout=30.0):
    """Pump the event loop until everything is mounted (or we give up)."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        await pilot.pause(0.02)
        if _idle(app):
            # One more pause so the final batch finishes mounting.
            await pilot.pause(0.06)
            if _idle(app):
                return True
    return False


@pytest.mark.asyncio
async def test_firehose_bus_output():
    """Simulate a wall of tool/shell output: N TextMessages through the bus.

    Reports total drain time, per-message cost, and how many widgets the
    VerticalScroll ends up holding (the DOM-bloat signal).
    """
    n = _bus_n()
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        start_widgets = _widget_count(app)

        t0 = time.perf_counter()
        for i in range(n):
            app.enqueue_render(
                (
                    "bus",
                    TextMessage(
                        level=MessageLevel.INFO,
                        text=f"line {i:05d}: the quick brown fox jumps over the lazy dog",
                    ),
                )
            )
        enqueue_s = time.perf_counter() - t0

        drained = await _drain(pilot, app, timeout=max(60.0, n * 0.05))
        total_s = time.perf_counter() - t0

        added = _widget_count(app) - start_widgets
        per_msg_ms = (total_s / n) * 1000

        print(
            f"\n[firehose-bus] n={n} drained={drained} "
            f"enqueue={enqueue_s * 1000:.1f}ms total={total_s * 1000:.1f}ms "
            f"per_msg={per_msg_ms:.3f}ms widgets_added={added}"
        )

        assert drained, f"render queue did not drain within timeout (n={n})"
        # Coalescing: a firehose of plain-text messages collapses into a small
        # number of mounted widgets instead of one-per-message. This guards the
        # win -- if someone reverts batching, widgets_added jumps back to n.
        assert added < n, f"expected coalesced widgets, got {added} for n={n}"
        # Loose ceiling: ~10ms/msg would be miserable; flag if we blow past it.
        assert per_msg_ms < 10.0, f"per-message render too slow: {per_msg_ms:.3f}ms"


@pytest.mark.asyncio
async def test_firehose_token_stream():
    """Simulate fast token streaming: N small text deltas into MarkdownStream.

    MarkdownStream batches writes internally, so this should stay cheap even
    at high N. Reports total time and per-delta cost.
    """
    n = _delta_n()
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()

        t0 = time.perf_counter()
        for i in range(n):
            app._on_stream_event(
                "part_delta",
                {
                    "index": 0,
                    "delta_type": "TextPartDelta",
                    "delta": _Delta("tok " if i % 12 else "tok\n"),
                },
            )
        enqueue_s = time.perf_counter() - t0

        drained = await _drain(pilot, app, timeout=max(60.0, n * 0.05))
        total_s = time.perf_counter() - t0
        per_delta_ms = (total_s / n) * 1000

        # One markdown widget should hold the whole streamed response.
        from textual.widgets import Markdown

        mds = list(app.query_one("#log", VerticalScroll).query(Markdown))

        print(
            f"\n[firehose-stream] n={n} drained={drained} "
            f"enqueue={enqueue_s * 1000:.1f}ms total={total_s * 1000:.1f}ms "
            f"per_delta={per_delta_ms:.3f}ms md_widgets={len(mds)}"
        )

        assert drained, f"render queue did not drain within timeout (n={n})"
        assert app._streamed_this_turn is True
        # The whole stream collapses into a single Markdown widget (no DOM
        # bloat) -- this is the key win of streaming vs. per-line mounting.
        assert len(mds) == 1
        assert per_delta_ms < 5.0, f"per-delta stream too slow: {per_delta_ms:.3f}ms"
