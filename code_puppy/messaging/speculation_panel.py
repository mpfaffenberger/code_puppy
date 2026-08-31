"""Append-only speculation record for CodeMode (pydantic-ai-harness#699), via termflow.

The previous implementation drove a Rich ``Live`` region: the whole frame was
repainted on every stream delta, which flickered on busy streams and fought
the terminal's scroll state at reveal time. This version follows termflow's
streaming philosophy instead and never repaints anything:

* each code line prints exactly once, when the statement containing it
  closes (termflow's Pygments pipeline supplies the colors);
* launches, settles, hits, misses, evictions, and the eager prefix commit
  append chronologically beneath the code as their events arrive, so the
  scrollback itself is the record -- no separate "reveal" frame exists;
* the session totals line prints when the cycle finalizes.

One panel instance lives per streaming console (module singleton, matching
``event_stream_handler``'s console handling). A cycle spans one ``run_code``
part: it opens on the first `SpeculativeCodeUpdateEvent`, prints its remaining
code when the part ends, absorbs the outcome events the capability flushes
after execution, and finalizes when the next part starts or the stream ends.

Rendering is fail-open like every other observation surface: an exception
here must never break the run.
"""

from __future__ import annotations

import ast
import logging
from typing import Any, Dict, Optional

from rich.console import Console
from rich.text import Text
from termflow.syntax import Highlighter

from pydantic_ai_harness.code_mode import (
    EagerPrefixCommittedEvent,
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
    SpeculativeCodeUpdateEvent,
)

logger = logging.getLogger(__name__)

_GUTTER = "  {lineno:>3} │ "


def _closed_boundary_line(code: str, closed_statements: int) -> int:
    """Last line (1-based) covered by the first `closed_statements` statements.

    Mirrors the harness's scanner: the largest parsable prefix of the
    streaming snippet defines the closed region. Returns 0 when nothing has
    closed yet.
    """
    if closed_statements <= 0:
        return 0
    lines = code.split("\n")
    for end in range(len(lines), 0, -1):
        try:
            body = ast.parse("\n".join(lines[:end])).body
        except SyntaxError:
            continue
        if not body:
            return 0
        node = body[min(closed_statements, len(body)) - 1]
        return node.end_lineno or 0
    return 0


def _args_preview(arguments: Dict[str, Any], limit: int = 40) -> str:
    """First keyword argument as a short human cue, elided past `limit`."""
    for key, value in arguments.items():
        text = f"{key}={value!r}"
        return text if len(text) <= limit else text[: limit - 1] + "…"
    return ""


class SpeculationPanel:
    """Streams one speculative `run_code` lifecycle as append-only lines."""

    def __init__(self) -> None:
        self._highlighter = Highlighter()
        self._console: Optional[Console] = None
        self._phase: str = "idle"  # idle | streaming | executing
        self._code: str = ""
        self._closed_count: int = -1
        self._printed_lines: int = 0
        self._launch_labels: Dict[str, str] = {}
        # Per-cycle outcome counters, folded into the session totals at finalize.
        self._hits = 0
        self._hidden_ms = 0.0
        self._misses = 0
        self._wasted = 0
        self._eager_hidden_ms = 0.0
        # Session-cumulative record, across every cycle this process rendered.
        self._session_hits = 0
        self._session_hidden_ms = 0.0
        self._session_misses = 0
        self._session_wasted = 0
        self._session_eager_hidden_ms = 0.0

    # -- event intake ---------------------------------------------------

    def handle_event(self, event: Any, console: Console) -> bool:
        """Consume a speculation event; returns True when the event was ours."""
        try:
            if isinstance(event, SpeculativeCodeUpdateEvent):
                self._on_update(event, console)
            elif isinstance(event, SpeculativeCallLaunchedEvent):
                self._on_launched(event, console)
            elif isinstance(event, SpeculativeCallSettledEvent):
                self._on_settled(event, console)
            elif isinstance(event, SpeculativeCallClaimedEvent):
                self._on_claimed(event, console)
            elif isinstance(event, SpeculativeCallMissedEvent):
                self._on_missed(event, console)
            elif isinstance(event, SpeculativeCallEvictedEvent):
                self._on_evicted(event, console)
            elif isinstance(event, EagerPrefixCommittedEvent):
                self._on_eager(event, console)
            else:
                return False
            return True
        except Exception:  # pragma: no cover - rendering must not break runs
            logger.exception(
                "speculation panel failed handling %r", type(event).__name__
            )
            return True

    @property
    def active(self) -> bool:
        """True while a speculation cycle owns the output."""
        return self._phase != "idle"

    def on_part_end(self) -> None:
        """The `run_code` args finished streaming; the snippet now executes.

        Every line is printable now, so the remaining tail (the statements the
        line-conservative scanner held back) prints here, before execution's
        outcome lines start arriving.
        """
        if self._phase != "streaming":
            return
        self._phase = "executing"
        console = self._console
        if console is None:  # pragma: no cover - streaming always sets it
            return
        self._print_code_through(console, len(self._code.split("\n")))
        console.print(Text("  executing...", style="dim"))

    def on_stream_end(self) -> None:
        """One event stream ended; keep an executing cycle alive for its outcomes.

        The claim/miss/eviction events flush in a later handler invocation than
        the one that streamed the snippet, so an `executing` cycle must survive
        the gap; it finalizes when the next part starts. A cycle still
        `streaming` here was cut mid-part: finalize it so nothing dangles.
        """
        if self._phase == "streaming":
            self.finalize()

    def finalize(self) -> None:
        """Close the cycle: fold counters into the session totals and print them."""
        try:
            if self._phase == "idle":
                return
            self._session_hits += self._hits
            self._session_hidden_ms += self._hidden_ms
            self._session_misses += self._misses
            self._session_wasted += self._wasted
            self._session_eager_hidden_ms += self._eager_hidden_ms
            if self._console is not None:
                self._console.print(self._session_line())
            self._reset()
        except Exception:  # pragma: no cover
            logger.exception("speculation panel failed to finalize")

    # -- event handlers -------------------------------------------------

    def _on_update(self, event: SpeculativeCodeUpdateEvent, console: Console) -> None:
        """Print any newly closed lines; already-printed lines are never touched."""
        if self._phase == "idle":
            self._phase = "streaming"
            self._console = console
            console.print(Text("─ run_code (speculating) ─", style="dim"))
        self._code = event.code
        if event.closed_statements == self._closed_count:
            return
        self._closed_count = event.closed_statements
        boundary = _closed_boundary_line(event.code, event.closed_statements)
        self._print_code_through(console, boundary)

    def _on_launched(self, event: SpeculativeCallLaunchedEvent, console: Console) -> None:
        label = event.wrapped_tool_name
        self._launch_labels[event.launch_id] = label
        preview = _args_preview(event.arguments)
        where = (
            "prefetched at execution"
            if event.phase == "execution"
            else f"launched at line {event.line_start}"
        )
        console.print(Text(f"  >> {label}({preview}) {where}", style="yellow"))

    def _on_settled(self, event: SpeculativeCallSettledEvent, console: Console) -> None:
        label = self._launch_labels.get(event.launch_id, "call")
        verb = "ready" if event.outcome == "ready" else "failed"
        console.print(
            Text(f"  .. {label} {verb} after {event.elapsed_ms:.0f}ms", style="dim")
        )

    def _on_claimed(self, event: SpeculativeCallClaimedEvent, console: Console) -> None:
        self._hits += 1
        self._hidden_ms += event.elapsed_ms
        detail = f"{event.elapsed_ms:.0f}ms hidden"
        if event.ready_at_claim is False:
            detail += ", claimed mid-flight"
        console.print(
            Text(f"  == hit {event.wrapped_tool_name} ({detail})", style="green")
        )

    def _on_missed(self, event: SpeculativeCallMissedEvent, console: Console) -> None:
        self._misses += 1
        console.print(
            Text(
                f"  -- miss {event.wrapped_tool_name} (ran cold, no matching launch)",
                style="yellow",
            )
        )

    def _on_evicted(self, event: SpeculativeCallEvictedEvent, console: Console) -> None:
        self._wasted += 1
        console.print(
            Text(
                f"  xx wasted {event.wrapped_tool_name} ({event.state})",
                style="dim",
            )
        )

    def _on_eager(self, event: EagerPrefixCommittedEvent, console: Console) -> None:
        hidden_s = max(0.0, event.executed_ms - event.waited_ms) / 1000.0
        self._eager_hidden_ms += max(0.0, event.executed_ms - event.waited_ms)
        console.print(
            Text(
                f"  eager ran {event.statements} stmts during generation "
                f"({hidden_s:.1f}s hidden)",
                style="cyan",
            )
        )

    # -- rendering ------------------------------------------------------

    def _print_code_through(self, console: Console, boundary: int) -> None:
        """Print code lines `(self._printed_lines, boundary]`, exactly once each.

        The whole current prefix is re-highlighted so multi-line constructs
        keep their lexer context, but only the new lines are written.
        """
        if boundary <= self._printed_lines:
            return
        lines = self._code.split("\n")
        boundary = min(boundary, len(lines))
        highlighted = self._highlighter.highlight_lines(lines, "python")
        for index in range(self._printed_lines, boundary):
            # The gutter is a styled span, not the Text's base style: a base
            # style would combine with (and dim) the code's own colors.
            line = Text()
            line.append(_GUTTER.format(lineno=index + 1), style="dim")
            line.append_text(Text.from_ansi(highlighted[index]))
            console.print(line)
        self._printed_lines = boundary

    def _session_line(self) -> Text:
        return Text(
            f"  speculation this session: hits {self._session_hits} "
            f"({self._session_hidden_ms / 1000.0:.1f}s hidden) - "
            f"misses {self._session_misses} - wasted {self._session_wasted} - "
            f"eager {self._session_eager_hidden_ms / 1000.0:.1f}s hidden",
            style="dim",
        )

    def _reset(self) -> None:
        self._console = None
        self._phase = "idle"
        self._code = ""
        self._closed_count = -1
        self._printed_lines = 0
        self._launch_labels = {}
        self._hits = 0
        self._hidden_ms = 0.0
        self._misses = 0
        self._wasted = 0
        self._eager_hidden_ms = 0.0


_panel: Optional[SpeculationPanel] = None


def get_speculation_panel() -> SpeculationPanel:
    """Module singleton, one per process like the streaming console itself."""
    global _panel
    if _panel is None:
        _panel = SpeculationPanel()
    return _panel
