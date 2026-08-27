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

from rich.console import Console, ConsoleOptions, RenderResult
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from pydantic_ai_harness.code_mode import (
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

    def clock_ms(self) -> float:
        if self.elapsed_ms is not None:
            return self.elapsed_ms
        return (time.monotonic() - self.started) * 1000.0


class SpeculationPanel:
    """Renders one speculative `run_code` lifecycle as a live terminal region."""

    def __init__(self) -> None:
        self._live: Optional[Live] = None
        self._console: Optional[Console] = None
        self._code: str = ""
        self._closed_line: int = 0
        self._launches: Dict[str, _Launch] = {}
        self._misses: List[str] = []
        self._phase: str = "idle"  # idle | streaming | executing

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

        Stops the live region so the message bus can render tool output
        without interleaving; the annotated panel prints at `finalize` once
        the outcome events have arrived.
        """
        if self._phase == "streaming":
            self._phase = "executing"
            live, self._live = self._live, None
            if live is not None:
                live.stop()

    def finalize(self) -> None:
        """Close the cycle: stop the live region, print the permanent record."""
        try:
            if self._phase == "idle":
                return
            live, console = self._live, self._console
            self._live = None
            if live is not None:
                live.stop()
            if console is not None and self._code:
                console.print(self._render_panel(final=True))
            self._reset()
        except Exception:  # pragma: no cover
            logger.exception("speculation panel failed to finalize")

    # -- event handlers -------------------------------------------------

    def _on_update(self, event: SpeculativeCodeUpdateEvent, console: Console) -> None:
        if self._phase == "idle":
            self._phase = "streaming"
            self._console = console
        self._code = event.code
        self._closed_line = _closed_boundary_line(event.code, event.closed_statements)
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

    def _ensure_live(self, console: Console) -> None:
        if self._live is not None:
            return
        self._live = Live(
            self,
            console=console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.start()

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.refresh()

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield self._render_panel(final=False)

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
                return Text(f"hit {ms:3.0f}ms ", style="bold green")
            if launch.state == "wasted":
                return Text("wasted   ", style="grey50")
        return Text(" " * (_GUTTER_WIDTH - 1))

    def _render_panel(self, *, final: bool) -> Panel:
        body = Text()
        highlighted = Syntax("", "python", theme="ansi_dark").highlight(self._code)
        highlighted.rstrip()
        code_lines = highlighted.split("\n")
        raw_lines = self._code.rstrip("\n").split("\n")
        for i, raw in enumerate(raw_lines):
            lineno = i + 1
            body.append_text(self._gutter_for_line(lineno))
            closed = lineno <= self._closed_line or final or self._phase == "executing"
            if closed and i < len(code_lines):
                body.append_text(code_lines[i])
            else:
                body.append(raw, style="grey50")
            body.append("\n")
        body.append_text(self._footer())
        title = "run_code" if final else "run_code (streaming)"
        return Panel(body, title=title, title_align="left", border_style="grey50")

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
            if hits:
                hidden = sum(c.elapsed_ms or 0.0 for c in hits)
                parts.append(f"hits {len(hits)} ({hidden:.0f}ms hidden)")
            if self._misses:
                parts.append(f"misses {len(self._misses)}")
            if wasted:
                parts.append(f"wasted {wasted}")
            if not parts and self._phase == "executing":
                parts.append("executing...")
        return Text("  " + " - ".join(parts) if parts else "", style="dim")

    def _reset(self) -> None:
        self._console = None
        self._code = ""
        self._closed_line = 0
        self._launches = {}
        self._misses = []
        self._phase = "idle"


_panel: Optional[SpeculationPanel] = None


def get_speculation_panel() -> SpeculationPanel:
    """The process-wide panel shared by every event stream invocation.

    Module singleton because outcome events can arrive in a later handler
    invocation than the streaming cycle that opened the panel.
    """
    global _panel
    if _panel is None:
        _panel = SpeculationPanel()
    return _panel
