"""Per-agent-run + conversation-wide timing stats (TTFT + generation speed).

Driven by lifecycle callbacks so timing measurement is fully decoupled from
the spinner / event-stream renderer:

* ``agent_run_start`` -- fires BEFORE pydantic-ai opens its HTTP/SSE socket,
  giving us a true T0 for time-to-first-token. (Measuring inside the stream
  handler underestimated TTFT because the request was already in flight by
  the time the handler started iterating events.)
* ``stream_event`` -- fires for every part-start / part-delta event. The
  first text/thinking event marks T1 (first-token time); subsequent events
  accumulate output-token counts AND inter-event elapsed time for the
  generation-speed average. Gen-speed is measured purely between stream
  events -- gaps larger than ``_MAX_INTER_EVENT_GAP_SECONDS`` (tool
  execution, the next model call's request latency) are treated as stalls
  and excluded, so TG reflects actual decode speed rather than wall-clock
  time across the whole agent run.
* ``agent_run_end`` -- folds the just-finished cycle into conversation-wide
  aggregates so the auto-save line shows up-to-date averages.

Sub-agent runs are intentionally ignored -- they'd otherwise clobber the main
session's stats with parallel/nested timing data.

The cumulative averages surface on the auto-save line at the end of each
turn (see ``config._maybe_autosave_session``). The spinner itself doesn't
render any of this data live -- the per-cycle values flicker too aggressively
to be readable mid-stream.
"""

from __future__ import annotations

import math
import time
from threading import Lock
from typing import Any, Optional, Tuple

from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPartDelta,
)

from code_puppy.tools.subagent_context import is_subagent


class AgentRunStats:
    """Singleton-style storage for per-cycle + conversation run stats.

    Class-level state with a lock keeps the API trivially callable from
    callback hooks (sync or async) without needing to thread an instance
    through the agent runtime.
    """

    _lock: Lock = Lock()

    # Inter-event gaps above this are stalls (tool runs, follow-up request
    # latency) and are excluded from generation-time accounting. Streaming
    # deltas arrive sub-second even on slow backends, so 2s is generous.
    _MAX_INTER_EVENT_GAP_SECONDS: float = 2.0

    # ----------------- per-cycle state -----------------
    # T0 set on agent_run_start; T1 set on first content stream_event;
    # output_tokens accumulates across all stream_events in the cycle.
    # gen_seconds accumulates only the gaps BETWEEN stream events, so tool
    # execution time between model calls never pollutes the TG denominator.
    _stream_start_time: float = 0.0
    _first_token_time: float = 0.0
    _last_token_time: float = 0.0
    _gen_seconds: float = 0.0
    _output_tokens: int = 0

    # Snapshot of the most-recently-finished cycle. Used as a fallback so
    # consumers (telemetry, future displays) have something stable to read
    # between cycles instead of seeing zeros.
    _last_ttft_seconds: float = 0.0
    _last_gen_tps: float = 0.0

    # --------------- conversation-wide aggregates ---------------
    # Summed across every model call in the session so we can report
    # weighted averages on auto-save / session shutdown.
    _total_ttft_seconds: float = 0.0
    _ttft_sample_count: int = 0
    _total_output_tokens: int = 0
    _total_gen_seconds: float = 0.0

    # ----------------- API -----------------
    @classmethod
    def mark_request_start(cls) -> None:
        """Mark T0 = true request-start (called by ``agent_run_start`` hook).

        Resets per-cycle counters but preserves conversation-wide aggregates
        and the most-recently-completed cycle's last-known values.
        """
        with cls._lock:
            cls._stream_start_time = time.monotonic()
            cls._first_token_time = 0.0
            cls._last_token_time = 0.0
            cls._gen_seconds = 0.0
            cls._output_tokens = 0

    @classmethod
    def record_output_tokens(cls, tokens: int) -> None:
        """Account for ``tokens`` more streamed output tokens.

        Marks the first-token timestamp on the initial call so TTFT can be
        computed when the cycle ends. Generation time accumulates only as
        gaps between consecutive stream events; gaps wider than
        ``_MAX_INTER_EVENT_GAP_SECONDS`` are stalls (tool execution,
        follow-up request latency) and re-anchor the burst instead.
        """
        if tokens <= 0:
            return
        now = time.monotonic()
        with cls._lock:
            if cls._stream_start_time == 0.0:
                # Defensive: if mark_request_start() wasn't called, anchor now.
                cls._stream_start_time = now
            if cls._first_token_time == 0.0:
                cls._first_token_time = now
            else:
                gap = now - cls._last_token_time
                if 0.0 < gap <= cls._MAX_INTER_EVENT_GAP_SECONDS:
                    cls._gen_seconds += gap
            cls._last_token_time = now
            cls._output_tokens += int(tokens)

    @classmethod
    def snapshot_cycle_into_aggregates(cls) -> None:
        """Fold the just-finished cycle into conversation-wide aggregates.

        Called by the ``agent_run_end`` hook so the auto-save line reflects
        the cycle that just completed. Also updates the ``_last_*`` snapshot
        fields. Per-cycle counters are zeroed so the next ``mark_request_start``
        starts cleanly.
        """
        with cls._lock:
            if cls._first_token_time > 0.0 and cls._stream_start_time > 0.0:
                ttft = cls._first_token_time - cls._stream_start_time
                if ttft > 0:
                    cls._last_ttft_seconds = ttft
                    cls._total_ttft_seconds += ttft
                    cls._ttft_sample_count += 1
                if cls._output_tokens > 0 and cls._gen_seconds > 0:
                    cls._last_gen_tps = cls._output_tokens / cls._gen_seconds
                    cls._total_output_tokens += cls._output_tokens
                    cls._total_gen_seconds += cls._gen_seconds
            # Zero per-cycle state so the next run starts cleanly.
            cls._stream_start_time = 0.0
            cls._first_token_time = 0.0
            cls._last_token_time = 0.0
            cls._gen_seconds = 0.0
            cls._output_tokens = 0

    @classmethod
    def reset_cycle_state(cls) -> None:
        """Wipe per-cycle state. Mostly useful for tests / fresh runs.

        Conversation-wide aggregates are preserved -- use
        :meth:`reset_conversation_stats` to wipe those too.
        """
        with cls._lock:
            cls._stream_start_time = 0.0
            cls._first_token_time = 0.0
            cls._last_token_time = 0.0
            cls._gen_seconds = 0.0
            cls._output_tokens = 0
            cls._last_ttft_seconds = 0.0
            cls._last_gen_tps = 0.0

    @classmethod
    def reset_conversation_stats(cls) -> None:
        """Wipe conversation-wide aggregate stats (e.g. on session start)."""
        with cls._lock:
            cls._total_ttft_seconds = 0.0
            cls._ttft_sample_count = 0
            cls._total_output_tokens = 0
            cls._total_gen_seconds = 0.0

    @classmethod
    def get_conversation_stats(
        cls,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Return ``(avg_ttft_seconds, avg_gen_tps)`` for the whole session.

        Folds in the currently-active cycle (if it has measurable values) so
        the auto-save line includes the request that just completed.
        Returns ``(None, None)`` if no data has been collected yet.
        """
        with cls._lock:
            total_ttft = cls._total_ttft_seconds
            ttft_count = cls._ttft_sample_count
            total_out = cls._total_output_tokens
            total_gen = cls._total_gen_seconds

            # Fold in the currently-active cycle so the just-finished
            # request is reflected before it gets snapshotted.
            if cls._first_token_time > 0.0 and cls._stream_start_time > 0.0:
                live_ttft = cls._first_token_time - cls._stream_start_time
                if live_ttft > 0:
                    total_ttft += live_ttft
                    ttft_count += 1
                if cls._output_tokens > 0 and cls._gen_seconds > 0:
                    total_out += cls._output_tokens
                    total_gen += cls._gen_seconds

            avg_ttft = (total_ttft / ttft_count) if ttft_count > 0 else None
            avg_gen = (total_out / total_gen) if total_gen > 0 else None
            return avg_ttft, avg_gen

    @staticmethod
    def format_conversation_stats(
        avg_ttft: Optional[float], avg_gen: Optional[float]
    ) -> str:
        """Format conversation-wide averages as a compact suffix string.

        Note: a space is intentionally inserted between the TTFT value and
        its ``s`` unit so Rich's ReprHighlighter can match the full decimal
        as a number. Without the space, ``1.53s`` gets clipped to ``1.``
        because ``s`` is a word character and breaks the regex word boundary.
        The gen-speed value already has a natural space before ``t/s``.
        """
        parts = []
        if avg_ttft is not None and avg_ttft > 0:
            parts.append(f"avg TTFT {avg_ttft:.2f} s")
        if avg_gen is not None and avg_gen > 0:
            parts.append(f"avg TG {avg_gen:,.1f} t/s")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Callback handlers
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Approx 2.5 chars/token, matching estimator used elsewhere in the codebase."""
    if not text:
        return 0
    return max(1, math.floor(len(text) / 2.5))


def _record_text_tokens(text: str) -> None:
    n = _estimate_tokens(text)
    if n > 0:
        AgentRunStats.record_output_tokens(n)


async def _on_agent_run_start(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
) -> None:
    """Mark T0 = true request-start, before any HTTP packets fly."""
    if is_subagent():
        return
    AgentRunStats.mark_request_start()


async def _on_stream_event(
    event_type: str,
    event_data: Any,
    agent_session_id: str | None = None,
) -> None:
    """Detect first-token + accumulate output tokens for gen-speed math."""
    if is_subagent():
        return
    if not isinstance(event_data, dict):
        return

    if event_type == "part_start":
        part = event_data.get("part")
        if isinstance(part, (TextPart, ThinkingPart)):
            content = getattr(part, "content", "") or ""
            if content:
                _record_text_tokens(content)
    elif event_type == "part_delta":
        delta = event_data.get("delta")
        if isinstance(delta, (TextPartDelta, ThinkingPartDelta)):
            content = getattr(delta, "content_delta", "") or ""
            if content:
                _record_text_tokens(content)
        elif isinstance(delta, ToolCallPartDelta):
            args = getattr(delta, "args_delta", "") or ""
            if args:
                _record_text_tokens(args)


async def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Fold the just-finished cycle into conversation-wide aggregates.

    Always fires regardless of success/failure so partial-but-real stats
    still count toward the running averages.
    """
    if is_subagent():
        return
    AgentRunStats.snapshot_cycle_into_aggregates()


# ---------------------------------------------------------------------------
# Hook registration (idempotent, auto-runs on import)
# ---------------------------------------------------------------------------
_HOOKS_REGISTERED = False


def register_hooks() -> None:
    """Idempotently register the three run-stats callback hooks."""
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return
    try:
        from code_puppy.callbacks import register_callback

        register_callback("agent_run_start", _on_agent_run_start)
        register_callback("stream_event", _on_stream_event)
        register_callback("agent_run_end", _on_agent_run_end)
        _HOOKS_REGISTERED = True
    except Exception:
        # Callback module unavailable (extremely unlikely); silently skip
        # so this module can still import in degraded environments.
        pass


# Auto-register on import so any code path that touches the agents package
# (CLI, tests, plugins) gets timing instrumentation for free.
register_hooks()


__all__ = [
    "AgentRunStats",
    "register_hooks",
    "_on_agent_run_start",
    "_on_stream_event",
    "_on_agent_run_end",
]
