"""Live CLI panel for speculative CodeMode (pydantic-ai-harness#699).

While the model streams a speculative ``run_code`` snippet, this panel owns
the terminal region the plain ``Calling run_code... N token(s)`` progress line
would have used, and renders the speculation lifecycle from the run's typed
``code_mode.*`` capability events:

* the decoded snippet appears as it streams -- closed statements are syntax
  highlighted, the still-open tail stays dim grey;
* every speculative launch gets a gutter clock next to its statement's lines,
  ticking while the call runs ahead of the model's own writing;
* when the launch settles the clock freezes (ready or failed, with latency);
* when the snippet finally executes, gutter markers become outcomes (``hit``
  for adopted launches, ``x`` for wasted ones) and the footer totals the
  hidden latency.

One panel instance lives per streaming console (module singleton, matching
``event_stream_handler``'s console handling). A cycle spans one ``run_code``
part: it opens on the first `SpeculativeCodeUpdateEvent`, freezes when the
part ends, absorbs the outcome events the capability flushes after execution,
and prints a permanent record into the scrollback when the next part starts
or the stream ends. Outcome events with no live cycle (e.g. flushed after a
retry) degrade to one-line prints.

Rendering is fail-open like every other observation surface: an exception
here must never break the run.
"""

from __future__ import annotations

import ast
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.box import Box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

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

_SPINNER_FRAMES = "|/-\\"
_GUTTER_WIDTH = 10

# ROUNDED with the left edge blanked: streamed output in Code Puppy flows
# flush-left, and a full box reads as a wall between the code and the page.
_NO_LEFT_BOX = Box(" ─┬╮\n  ││\n ─┼┤\n  ││\n ─┼┤\n ─┼┤\n  ││\n ─┴╯\n")


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


@dataclass
class _Launch:
    line_start: int
    line_end: int
    label: str
    state: str = "running"  # running | ready | failed | hit | wasted
    started: float = field(default_factory=time.monotonic)
    elapsed_ms: Optional[float] = None
    ready_at_claim: Optional[bool] = None
    """For hits: True when the result was already waiting at claim time (the
    full call latency was hidden); False when the snippet had to wait for the
    tail of the call (partial overlap)."""

    def clock_ms(self) -> float:
        if self.elapsed_ms is not None:
            return self.elapsed_ms
        return (time.monotonic() - self.started) * 1000.0


class SpeculationPanel:
    """Renders one speculative `run_code` lifecycle as a live terminal region."""

    def __init__(self, *, max_code_lines: int = 10) -> None:
        if max_code_lines < 1:
            raise ValueError("max_code_lines must be at least 1")
        self._max_code_lines = max_code_lines
        self._live: Optional[Live] = None
        self._console: Optional[Console] = None
        self._code: str = ""
        self._closed_line: int = 0
        self._closed_count: int = -1
        self._highlight_cache: Optional[tuple[str, List[Text]]] = None
        self._launches: Dict[str, _Launch] = {}
        self._misses: List[str] = []
        self._eager_commit: Optional[EagerPrefixCommittedEvent] = None
        self._phase: str = "idle"  # idle | streaming | executing
        # Session-cumulative speculation record, across every cycle this
        # process has rendered; shown in each final reveal's footer.
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
                self._on_launched(event)
            elif isinstance(event, SpeculativeCallSettledEvent):
                self._on_settled(event)
            elif isinstance(event, SpeculativeCallClaimedEvent):
                self._on_claimed(event, console)
            elif isinstance(event, SpeculativeCallMissedEvent):
                self._on_missed(event, console)
            elif isinstance(event, SpeculativeCallEvictedEvent):
                self._on_evicted(event, console)
            elif isinstance(event, EagerPrefixCommittedEvent):
                # Arrives with the outcome flush after the snippet ran; the
                # reveal's footer reports it, so storing is enough here.
                self._eager_commit = event
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
        """True while a speculation cycle owns the terminal region."""
        return self._phase != "idle"

    def on_part_end(self) -> None:
        """The `run_code` args finished streaming; the snippet now executes.

        The live region stays up through execution (tool output is bus-quiet
        during speculative runs), so one Live spans the whole cycle: its final
        frame becomes the permanent reveal at `finalize`, with no clear-and-
        reprint boundary to fight the terminal's scroll state.
        """
        if self._phase == "streaming":
            self._phase = "executing"

    def on_stream_end(self) -> None:
        """One event stream ended; keep an executing cycle alive for its outcomes.

        The claim/miss/eviction events flush in a later handler invocation than
        the one that streamed the snippet (tool execution runs between them), so
        an `executing` cycle must survive the gap; its reveal prints when the
        next part starts. A cycle still `streaming` here was cut mid-part:
        finalize it so the live region never outlives its stream.
        """
        if self._phase == "streaming":
            self.finalize()

    def finalize(self) -> None:
        """Close the cycle: stop the live region, print the permanent record."""
        try:
            if self._phase == "idle":
                return
            self._session_hits += sum(
                1 for c in self._launches.values() if c.state == "hit"
            )
            self._session_hidden_ms += sum(
                c.elapsed_ms or 0.0 for c in self._launches.values() if c.state == "hit"
            )
            self._session_misses += len(self._misses)
            self._session_wasted += sum(
                1 for c in self._launches.values() if c.state == "wasted"
            )
            if self._eager_commit is not None:
                self._session_eager_hidden_ms += max(
                    0.0, self._eager_commit.executed_ms - self._eager_commit.waited_ms
                )
            live, console = self._live, self._console
            self._live = None
            if live is not None:
                # The final frame is the permanent record: update in place and
                # stop non-transiently, so nothing is cleared or reprinted.
                live.update(self._render_panel(final=True), refresh=True)
                live.stop()
                if console is not None:
                    console.print(self._session_line())
            elif console is not None and self._code:
                console.print(
                    self._render_panel(final=True, max_code_lines=self._max_code_lines)
                )
                console.print(self._session_line())
            self._reset()
        except Exception:  # pragma: no cover
            logger.exception("speculation panel failed to finalize")

    # -- event handlers -------------------------------------------------

    def _on_update(self, event: SpeculativeCodeUpdateEvent, console: Console) -> None:
        """Per-delta path: repaint every event so the tail grows smoothly.

        The boundary search only reruns when a statement actually closed and
        the highlight is cached per code revision, so the per-event repaint
        stays cheap.
        """
        if self._phase == "idle":
            self._phase = "streaming"
            self._console = console
        self._code = event.code
        if event.closed_statements != self._closed_count:
            self._closed_count = event.closed_statements
            self._closed_line = _closed_boundary_line(
                event.code, event.closed_statements
            )
        self._ensure_live(console)
        self._refresh()

    def _on_launched(self, event: SpeculativeCallLaunchedEvent) -> None:
        self._launches[event.launch_id] = _Launch(
            line_start=event.line_start,
            line_end=event.line_end,
            label=event.wrapped_tool_name,
        )
        self._refresh()

    def _on_settled(self, event: SpeculativeCallSettledEvent) -> None:
        launch = self._launches.get(event.launch_id)
        if launch is not None:
            launch.state = event.outcome
            launch.elapsed_ms = event.elapsed_ms
            self._refresh()

    def _on_claimed(self, event: SpeculativeCallClaimedEvent, console: Console) -> None:
        launch = self._launches.get(event.launch_id)
        if launch is None:
            console.print(
                Text(
                    f"  speculation hit: {event.wrapped_tool_name} "
                    f"ran {event.elapsed_ms:.0f}ms during generation",
                    style="green",
                )
            )
            return
        launch.state = "hit"
        launch.elapsed_ms = event.elapsed_ms
        launch.ready_at_claim = event.ready_at_claim
        self._refresh()

    def _on_missed(self, event: SpeculativeCallMissedEvent, console: Console) -> None:
        if self._phase == "idle":
            console.print(
                Text(
                    f"  speculation miss: {event.wrapped_tool_name} ran cold",
                    style="cyan",
                )
            )
            return
        self._misses.append(event.wrapped_tool_name)
        self._refresh()

    def _on_evicted(self, event: SpeculativeCallEvictedEvent, console: Console) -> None:
        launch = self._launches.get(event.launch_id)
        if launch is None:
            console.print(
                Text(
                    f"  speculation wasted: {event.wrapped_tool_name} was never claimed",
                    style="grey50",
                )
            )
            return
        launch.state = "wasted"
        self._refresh()

    # -- rendering ------------------------------------------------------

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.refresh()

    def _ensure_live(self, console: Console) -> None:
        if self._live is not None:
            return
        # One Live per cycle, kept until finalize. `transient=False` means the
        # last frame persists in the scrollback instead of being cleared and
        # reprinted -- the clear/reprint boundary is what scrambled scrolling.
        # `crop` keeps an over-tall frame from scrolling the screen on every
        # refresh; the streaming renderer also tail-clips the code to fit.
        self._live = Live(
            self,
            console=console,
            refresh_per_second=10,
            transient=False,
            vertical_overflow="crop",
        )
        self._live.start()

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        # Tail-clip live frames to the terminal: a frame taller than the screen
        # makes Live scroll the whole window on every refresh. The newest lines
        # are the interesting ones while code streams in.
        max_code_lines = min(self._max_code_lines, max(console.size.height - 8, 4))
        yield self._render_panel(final=False, max_code_lines=max_code_lines)

    def _gutter_for_line(self, lineno: int) -> Text:
        for launch in self._launches.values():
            if launch.line_start != lineno:
                continue
            ms = launch.clock_ms()
            if launch.state == "running":
                frame = _SPINNER_FRAMES[
                    int(time.monotonic() * 8) % len(_SPINNER_FRAMES)
                ]
                return Text(f"{frame} {ms:5.0f}ms ", style="yellow")
            if launch.state == "ready":
                return Text(f"+ {ms:5.0f}ms ", style="green")
            if launch.state == "failed":
                return Text(f"! {ms:5.0f}ms ", style="red")
            if launch.state == "hit":
                # `hit` fully overlapped generation; `hit~` means the snippet
                # still waited for the tail of the call at claim time.
                if launch.ready_at_claim is False:
                    return Text(f"hit~{ms:3.0f}ms ", style="yellow")
                return Text(f"hit {ms:3.0f}ms ", style="bold green")
            if launch.state == "wasted":
                return Text("wasted   ", style="grey50")
        return Text(" " * (_GUTTER_WIDTH - 1))

    def _highlighted_lines(self) -> List[Text]:
        """Pygments over the whole snippet, cached per code revision.

        Rendering happens on the auto-refresh thread at 10fps; between deltas
        the code is unchanged and the highlight must not be recomputed.
        """
        cache = self._highlight_cache
        if cache is not None and cache[0] == self._code:
            return cache[1]
        highlighted = Syntax("", "python", theme="ansi_dark").highlight(self._code)
        highlighted.rstrip()
        lines = highlighted.split("\n")
        self._highlight_cache = (self._code, lines)
        return lines

    def _render_panel(self, *, final: bool, max_code_lines: int | None = None) -> Panel:
        body = Text()
        code_lines = self._highlighted_lines()
        raw_lines = self._code.rstrip("\n").split("\n")
        first = 0
        if max_code_lines is not None and len(raw_lines) > max_code_lines:
            first = len(raw_lines) - max_code_lines
            body.append(f"(+{first} earlier lines)\n", style="dim")
        for i, raw in enumerate(raw_lines[first:], start=first):
            lineno = i + 1
            body.append_text(self._gutter_for_line(lineno))
            closed = lineno <= self._closed_line or final or self._phase == "executing"
            if closed and i < len(code_lines):
                body.append_text(code_lines[i])
            else:
                body.append(raw, style="grey50")
            body.append("\n")
        body.append_text(self._footer())
        # Same 2.5 chars/token heuristic as the plain tool progress line.
        tokens = max(1, int(len(self._code) / 2.5)) if self._code else 0
        title = (
            f"run_code (~{tokens} tokens)"
            if final
            else f"run_code (streaming, ~{tokens} tokens)"
        )
        return Panel(
            body,
            title=title,
            title_align="left",
            border_style="grey50",
            box=_NO_LEFT_BOX,
        )

    def _footer(self) -> Text:
        running = sum(1 for c in self._launches.values() if c.state == "running")
        ready = sum(1 for c in self._launches.values() if c.state == "ready")
        failed = sum(1 for c in self._launches.values() if c.state == "failed")
        hits = [c for c in self._launches.values() if c.state == "hit"]
        wasted = sum(1 for c in self._launches.values() if c.state == "wasted")
        parts: List[str] = []
        if self._phase == "streaming":
            parts.append("speculating while the model writes")
            if running:
                parts.append(f"{running} in flight")
            if ready:
                parts.append(f"{ready} ready")
            if failed:
                parts.append(f"{failed} failed")
        else:
            if self._eager_commit is not None:
                commit = self._eager_commit
                hidden_s = max(0.0, commit.executed_ms - commit.waited_ms) / 1000.0
                parts.append(
                    f"eager ran {commit.statements} stmts during generation "
                    f"({hidden_s:.1f}s hidden)"
                )
            if hits:
                hidden = sum(c.elapsed_ms or 0.0 for c in hits)
                partial = sum(1 for c in hits if c.ready_at_claim is False)
                detail = f"{hidden:.0f}ms hidden"
                if partial:
                    detail += f", {partial} partial"
                parts.append(f"hits {len(hits)} ({detail})")
            if self._misses:
                parts.append(f"misses {len(self._misses)} ({', '.join(self._misses)})")
            if wasted:
                parts.append(f"wasted {wasted}")
            if not parts and self._phase == "executing":
                parts.append("executing...")
        return Text("  " + " - ".join(parts) if parts else "", style="dim")

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
        self._code = ""
        self._closed_line = 0
        self._closed_count = -1
        self._highlight_cache = None
        self._launches = {}
        self._misses = []
        self._eager_commit = None
        self._phase = "idle"


_panel: Optional[SpeculationPanel] = None


def get_speculation_panel(*, max_code_lines: int = 10) -> SpeculationPanel:
    """The process-wide panel shared by every event stream invocation.

    Module singleton because outcome events can arrive in a later handler
    invocation than the streaming cycle that opened the panel.
    """
    global _panel
    if _panel is None:
        _panel = SpeculationPanel(max_code_lines=max_code_lines)
    return _panel
