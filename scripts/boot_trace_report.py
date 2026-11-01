#!/usr/bin/env python3
"""Ranked report for Code Puppy boot-trace output (schema v1).

Accepts JSONL trace files or stderr captures with tagged trace lines, pairs
span starts with their terminals per boot, and prints the slowest phases and
plugin imports. Standalone and stdlib-only: it never imports code_puppy and
never echoes input lines or exception text.

Depends on: boot_trace.py :: _Recorder.emit()  (event shape; keep in sync)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import IO, Any, Iterator

SCHEMA_VERSION = 1
TAG = b"CODE_PUPPY_BOOT_TRACE "
MAX_LINE_BYTES = 2048
MAX_SAFE_INT = 2**53 - 1
MAX_SHOWN_ID = 32
DEFAULT_TOP = 20
PLUGIN_PHASE = "plugin.import"
DROP_PHASE = "boot.dropped"
LIFETIME_PHASES = frozenset({"boot", "cli.handle_args"})
LIFETIME_LABEL = "(session lifetime, not boot-ready)"
KINDS = frozenset({"start", "end", "error", "skip", "mark"})
TERMINAL_KINDS = frozenset({"end", "error", "skip"})
TIERS = frozenset({"installed", "builtin", "user", "project"})
OUTCOMES = frozenset(
    {
        "ok",
        "error",
        "timeout",
        "tls",
        "dns",
        "other",
        "remote",
        "fallback",
        "unavailable",
        "control_exit",
    }
)
PHASE_RE = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*")
SPAN_RE = re.compile(r"[0-9a-f]{1,16}")
BOOT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
PLUGIN_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}|h:[0-9a-f]{16}")
UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]")
PHASE_ROW = "  {dur:>11}  {status:<26}  {label}"
PLUGIN_ROW = "  {tier:<9}  {identity:<20}  {dur:>11}  {status}"
ATTRIBUTION_NOTES = (
    "shared or nested imports are charged to the first importer",
    "import wrappers include ownership finalization and cleanup",
    "already-imported modules are warm",
    "queue and writer startup add diagnostic overhead",
    "pre-Python, interpreter, and package-init time is invisible",
    "no phase totals or percentages; do not add nested durations",
    "ACP session duration is not startup duration",
    "durations do not show CPU vs disk, antivirus, or network time",
)

_BAD = "bad"
_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Event:
    boot_id: str
    seq: int
    phase: str
    span: str
    parent: str | None
    kind: str
    dur_ms: float | None
    tier: str | None
    plugin: str | None
    outcome: str | None
    dropped: int | None


@dataclass(frozen=True)
class Pair:
    start: Event
    end: Event


@dataclass
class _Ingest:
    events: dict[str, list[Event]]
    issues: Counter
    stray: int = 0
    tagged_seen: bool = False


@dataclass(frozen=True)
class _Summary:
    boot_id: str
    event_count: int
    pairs: list[Pair]
    skipped: int
    issues: Counter


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def _in_safe_range(value: Any) -> bool:
    return _is_finite_number(value) and 0 <= value <= MAX_SAFE_INT


def _matches(value: Any, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _valid_phase(value: Any) -> bool:
    return _matches(value, PHASE_RE) and len(value) <= 64


def _enum_or_none(value: Any, allowed: frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _reject_constant(token: str) -> None:
    raise ValueError("non-finite number")


def _to_event(obj: Any) -> Event | str:
    """Return a validated Event, ``_UNKNOWN`` for other schema versions, or ``_BAD``."""
    if not isinstance(obj, dict) or not _is_int(obj.get("v")):
        return _BAD
    if obj["v"] != SCHEMA_VERSION:
        return _UNKNOWN
    kind = obj.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return _BAD
    boot_id, seq = obj.get("bootId"), obj.get("seq")
    phase, span, attrs = obj.get("phase"), obj.get("span"), obj.get("attrs")
    if not (
        _matches(boot_id, BOOT_ID_RE)
        and _is_int(seq)
        and 1 <= seq <= MAX_SAFE_INT
        and _valid_phase(phase)
        and _matches(span, SPAN_RE)
        and ("parent" not in obj or _matches(obj["parent"], SPAN_RE))
        and isinstance(attrs, dict)
        and _is_finite_number(obj.get("tMonoMs"))
        and _is_finite_number(obj.get("tWallMs"))
    ):
        return _BAD
    dur_ms = obj.get("durMs")
    if kind in TERMINAL_KINDS and not _in_safe_range(dur_ms):
        return _BAD
    is_drop = phase == DROP_PHASE
    dropped = obj.get("dropped")
    if (is_drop or "dropped" in obj) and not (
        is_drop and kind == "mark" and _is_int(dropped) and _in_safe_range(dropped)
    ):
        return _BAD
    plugin = attrs.get("plugin")
    return Event(
        boot_id=boot_id,
        seq=seq,
        phase=phase,
        span=span,
        parent=obj.get("parent"),
        kind=kind,
        dur_ms=float(dur_ms) if kind in TERMINAL_KINDS else None,
        tier=_enum_or_none(attrs.get("tier"), TIERS),
        plugin=plugin if _matches(plugin, PLUGIN_RE) else None,
        outcome=_enum_or_none(attrs.get("outcome"), OUTCOMES),
        dropped=dropped if is_drop else None,
    )


def _parse_line(body: bytes) -> Event | str:
    try:
        text = body.rstrip(b"\r\n").decode("utf-8")
        obj = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return _BAD
    return _to_event(obj)


def _iter_lines(stream: IO[bytes]) -> Iterator[tuple[bytes, bool]]:
    """Yield ``(line, oversized)``; oversized lines are drained, never buffered."""
    read_size = MAX_LINE_BYTES + 1
    while True:
        line = stream.readline(read_size)
        if not line:
            return
        if len(line) <= MAX_LINE_BYTES:
            yield line, False
            continue
        yield line, True
        while not line.endswith(b"\n"):
            line = stream.readline(read_size)
            if not line:
                return


def _ingest_line(state: _Ingest, line: bytes, oversized: bool) -> None:
    tagged = line.startswith(TAG)
    state.tagged_seen = state.tagged_seen or tagged
    body = line[len(TAG) :] if tagged else line
    if not tagged and not body.lstrip().startswith(b"{"):
        state.stray += 1  # ordinary stderr noise unless the input is untagged JSONL
        return
    result = _BAD if oversized else _parse_line(body)
    if isinstance(result, Event):
        state.events.setdefault(result.boot_id, []).append(result)
    elif result == _UNKNOWN:
        state.issues["unknown_version"] += 1
    else:
        state.issues["malformed"] += 1


def _ingest(stream: IO[bytes]) -> _Ingest:
    state = _Ingest(events={}, issues=Counter())
    for line, oversized in _iter_lines(stream):
        _ingest_line(state, line, oversized)
    if not state.tagged_seen:
        state.issues["malformed"] += state.stray
    return state


def _dedupe_seq(events: list[Event], issues: Counter) -> list[Event]:
    by_seq: dict[int, Event] = {}
    for event in sorted(events, key=lambda e: e.seq):
        if event.seq in by_seq:
            issues["inconsistent"] += 1
        else:
            by_seq[event.seq] = event
    return list(by_seq.values())


def _pair_spans(events: list[Event], issues: Counter) -> tuple[list[Pair], int]:
    """Match terminals to starts by span; return complete pairs and skip count."""
    unique = _dedupe_seq(events, issues)
    if unique:
        issues["seq_gaps"] = unique[-1].seq - len(unique)
    issues["drop_marks"] = sum(1 for e in unique if e.phase == DROP_PHASE)
    open_starts: dict[str, Event] = {}
    used_spans: set[str] = set()
    pairs: list[Pair] = []
    skipped = 0
    for event in unique:
        if event.kind in ("start", "mark"):
            if event.span in used_spans:
                issues["inconsistent"] += 1
                continue
            used_spans.add(event.span)
            if event.kind == "start":
                open_starts[event.span] = event
            continue
        start = open_starts.get(event.span)
        if start is None or (start.phase, start.parent) != (event.phase, event.parent):
            issues["inconsistent"] += 1
            continue
        del open_starts[event.span]
        if event.kind == "skip":
            skipped += 1
        else:
            pairs.append(Pair(start, event))
    issues["unmatched_starts"] = len(open_starts)
    return pairs, skipped


def _summarize(boot_id: str, state: _Ingest) -> _Summary:
    events = state.events[boot_id]
    issues = Counter(state.issues)
    pairs, skipped = _pair_spans(events, issues)
    issues["dropped_events"] = max(
        (e.dropped for e in events if e.dropped is not None), default=0
    )
    return _Summary(boot_id, len(events), pairs, skipped, issues)


def _status(pair: Pair) -> str:
    base = "ok" if pair.end.kind == "end" else "error"
    return f"{base} outcome={pair.end.outcome}" if pair.end.outcome else base


def _ranked(pairs: list[Pair], top: int) -> list[Pair]:
    return sorted(pairs, key=lambda p: (-(p.end.dur_ms or 0.0), p.start.seq))[:top]


def _phase_row(pair: Pair) -> str:
    label = pair.start.phase
    if label in LIFETIME_PHASES:
        label = f"{label} {LIFETIME_LABEL}"
    return PHASE_ROW.format(
        dur=f"{pair.end.dur_ms:.3f}", status=_status(pair), label=label
    )


def _plugin_row(pair: Pair) -> str:
    return PLUGIN_ROW.format(
        tier=pair.end.tier or "?",
        identity=pair.end.plugin or "invalid",
        dur=f"{pair.end.dur_ms:.3f}",
        status=_status(pair),
    )


def _render(summary: _Summary, top: int) -> list[str]:
    issues = summary.issues
    complete = not any(issues.values())
    phases = [p for p in summary.pairs if p.start.phase != PLUGIN_PHASE]
    plugins = [p for p in summary.pairs if p.start.phase == PLUGIN_PHASE]
    lines = [
        "Boot trace report (schema v1)",
        f"boot id: {summary.boot_id}",
        f"events: {summary.event_count}  skipped spans (not ranked): {summary.skipped}",
        f"status: {'complete' if complete else 'INCOMPLETE'}",
        "",
        f"Phases (top {top}, excludes {PLUGIN_PHASE})",
        PHASE_ROW.format(dur="DURATION_MS", status="STATUS", label="PHASE"),
    ]
    lines += [_phase_row(p) for p in _ranked(phases, top)] or ["  (none)"]
    lines += [
        "",
        f"Plugins ({PLUGIN_PHASE}, top {top})",
        PLUGIN_ROW.format(
            tier="TIER", identity="IDENTITY", dur="DURATION_MS", status="STATUS"
        ),
    ]
    lines += [_plugin_row(p) for p in _ranked(plugins, top)] or ["  (none)"]
    if not complete:
        counts = " ".join(
            f"{name}={value}" for name, value in sorted(issues.items()) if value
        )
        lines += ["", f"INCOMPLETE: {counts}"]
    lines += ["", "Attribution caveats:"]
    lines += [f"  - {note}" for note in ATTRIBUTION_NOTES]
    return lines


def _shown_id(boot_id: str) -> str:
    return UNSAFE_ID_CHARS.sub("", boot_id)[:MAX_SHOWN_ID]


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ranked report for Code Puppy boot-trace output (schema v1)."
    )
    parser.add_argument("input", help="trace file, or '-' to read stdin")
    parser.add_argument(
        "--boot-id", help="boot to report when the input holds several boots"
    )
    parser.add_argument(
        "--top",
        type=_positive_int,
        default=DEFAULT_TOP,
        help=f"rows per section (default {DEFAULT_TOP})",
    )
    return parser.parse_args(argv)


def _read_input(source: str) -> _Ingest:
    if source == "-":
        return _ingest(sys.stdin.buffer)
    with open(source, "rb") as handle:
        return _ingest(handle)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        state = _read_input(args.input)
    except OSError:
        return _fail("cannot read input")
    if not state.events:
        return _fail("no usable v1 boot trace events")
    boot_ids = sorted(state.events)
    boot_id = args.boot_id
    if boot_id is None:
        if len(boot_ids) > 1:
            candidates = ", ".join(_shown_id(b) for b in boot_ids)
            return _fail(f"several boot ids; pass --boot-id (found: {candidates})")
        boot_id = boot_ids[0]
    if boot_id not in state.events:
        return _fail("boot id not found in input")
    summary = _summarize(boot_id, state)
    print("\n".join(_render(summary, args.top)))
    return 0 if not any(summary.issues.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
