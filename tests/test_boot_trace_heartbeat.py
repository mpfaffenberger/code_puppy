"""Boot-trace liveness heartbeat: the Heartbeat class, recorder wiring, report tolerance.

Class tests inject a tiny interval and wait on Events, never on wall-clock sleeps.
The recorder reads ``CODE_PUPPY_BOOT_TRACE`` once at import, so traced runs go
through a child process via ``_run_py``.
"""

import itertools
import json
import re
import threading

import pytest

import code_puppy._boot_trace_heartbeat as hb_mod
from code_puppy._boot_trace_heartbeat import Heartbeat
from tests.boot_trace_support import TIMEOUT, _run_py
from tests.test_boot_trace_report_input import (
    numbered,
    record,
    run_report,
    span_pair,
    tagged,
    write_lines,
)

TINY = 0.01


@pytest.fixture
def threads(monkeypatch):
    """Capture every thread the Heartbeat starts so tests can join them."""
    started = []

    class Recording(threading.Thread):
        def start(self):
            started.append(self)
            super().start()

    monkeypatch.setattr(hb_mod.threading, "Thread", Recording)
    return started


def _join_all(threads):
    for thread in threads:
        thread.join(TIMEOUT)
        assert not thread.is_alive()


def _ticking_clock(monkeypatch, step):
    """Make ``time.monotonic`` advance by ``step`` per call (``0`` freezes it)."""
    counter = itertools.count()
    monkeypatch.setattr(hb_mod.time, "monotonic", lambda: next(counter) * step)


def test_idle_heartbeat_ticks_on_a_named_daemon_thread(threads):
    ticked = threading.Event()
    hb = Heartbeat(ticked.set, interval_s=TINY)

    hb.start()
    try:
        assert ticked.wait(TIMEOUT)
    finally:
        hb.stop()

    (thread,) = threads
    assert (thread.name, thread.daemon) == ("boot-trace-heartbeat", True)
    _join_all(threads)


class _CountingStop(threading.Event):
    """Stop event that reports once the loop has woken ``wakes`` times."""

    def __init__(self, wakes):
        super().__init__()
        self.remaining = wakes
        self.done = threading.Event()

    def wait(self, timeout=None):
        if self.remaining == 0:
            self.done.set()
            return True
        self.remaining -= 1
        return False


def test_continuous_activity_suppresses_ticks(monkeypatch, threads):
    _ticking_clock(monkeypatch, 0)  # every wake sees activity "just now"
    ticks = []
    hb = Heartbeat(lambda: ticks.append(1), interval_s=1.0)
    hb._stop = _CountingStop(wakes=5)

    hb.start()
    assert hb._stop.done.wait(TIMEOUT)
    _join_all(threads)

    assert ticks == []


def test_silent_gap_ticks_once_per_wake(monkeypatch, threads):
    _ticking_clock(monkeypatch, 10.0)  # every wake sees a long silence
    ticks = []
    hb = Heartbeat(lambda: ticks.append(1), interval_s=1.0, max_s=1e9)
    hb._stop = _CountingStop(wakes=4)

    hb.start()
    assert hb._stop.done.wait(TIMEOUT)
    _join_all(threads)

    assert ticks == [1, 1, 1, 1]


def test_max_s_ends_the_loop_without_a_tick(monkeypatch, threads):
    _ticking_clock(monkeypatch, 10.0)
    ticks = []
    hb = Heartbeat(lambda: ticks.append(1), interval_s=TINY, max_s=5.0)

    hb.start()
    _join_all(threads)

    assert ticks == []


def test_tick_exceptions_are_swallowed_and_ticking_continues(threads):
    calls, second = [], threading.Event()

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        second.set()

    hb = Heartbeat(tick, interval_s=TINY)
    hb.start()
    try:
        assert second.wait(TIMEOUT)
    finally:
        hb.stop()
    _join_all(threads)


def test_stop_waits_for_an_inflight_tick_then_no_tick_runs(threads):
    in_tick, release = threading.Event(), threading.Event()
    calls = []

    def tick():
        in_tick.set()
        release.wait(TIMEOUT)
        calls.append(1)

    hb = Heartbeat(tick, interval_s=TINY)
    hb.start()
    assert in_tick.wait(TIMEOUT)
    threading.Timer(0.05, release.set).start()

    hb.stop()
    after_stop = list(calls)
    _join_all(threads)

    assert after_stop == [1]
    assert calls == [1]


def test_stop_is_idempotent_and_safe_before_start():
    hb = Heartbeat(lambda: None, interval_s=TINY)

    hb.stop()
    hb.stop()
    hb.note_activity()


def test_thread_start_failure_is_fail_open(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(hb_mod.threading, "Thread", refuse)
    ticks = []
    hb = Heartbeat(lambda: ticks.append(1), interval_s=TINY)

    hb.start()
    hb.stop()

    assert ticks == []


# --- recorder integration (child process) ---------------------------------

ENABLED_PROBE = """
import threading
import code_puppy.boot_trace as bt

bt._HEARTBEAT_INTERVAL_S = 0.02
bt.begin_boot()
enough = threading.Event()
real_mark, beats = bt._rec.mark, []


def counting(phase, parent, attrs):
    real_mark(phase, parent, attrs)
    if phase == "boot.heartbeat":
        beats.append(1)
        if len(beats) >= 3:
            enough.set()


bt._rec.mark = counting
assert enough.wait(120), "no heartbeat during the idle gap"
bt.end_boot()
"""

DISABLED_PROBE = """
import sys
import threading
import code_puppy.boot_trace as bt

bt.begin_boot()
bt.end_boot()
print(
    "code_puppy._boot_trace_heartbeat" in sys.modules,
    bt.enabled(),
    [t.name for t in threading.enumerate()],
)
"""


@pytest.fixture(scope="module")
def traced_events(tmp_path_factory):
    base = tmp_path_factory.mktemp("heartbeat")
    trace = base / "trace.jsonl"
    result = _run_py(ENABLED_PROBE, str(trace), base)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    return result, trace, events


def test_recorder_emits_heartbeat_marks_under_the_root_before_it_ends(traced_events):
    result, _, events = traced_events

    root_start, reached = events[0], events[1]
    root_end = events[-1]
    beats = [e for e in events if e["phase"] == "boot.heartbeat"]

    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert (root_start["phase"], root_start["kind"]) == ("boot", "start")
    assert (reached["phase"], reached["kind"]) == ("py.main_reached", "mark")
    assert (root_end["phase"], root_end["kind"]) == ("boot", "end")
    assert len(beats) >= 3
    assert {e["kind"] for e in beats} == {"mark"}
    assert {e["parent"] for e in beats} == {root_start["span"]}
    assert all(e["attrs"] == {} for e in beats)
    openers = [e["span"] for e in events if e["kind"] in ("start", "mark")]
    assert len(set(openers)) == len(openers)
    assert all(e["seq"] < root_end["seq"] for e in beats)
    assert result.stdout == ""


def test_report_ignores_heartbeat_marks_from_a_real_trace(traced_events, capsys):
    _, trace, _ = traced_events

    code, out, err = run_report(capsys, trace)

    assert code == 0, err
    assert "boot (session lifetime, not boot-ready)" in out
    assert "boot.heartbeat" not in out


def test_disabled_mode_never_imports_the_heartbeat_or_starts_a_thread(tmp_path):
    result = _run_py(DISABLED_PROBE, None, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False ['MainThread']"


def test_report_rankings_and_status_are_unchanged_by_heartbeats(tmp_path, capsys):
    def trace(heartbeats):
        records = [record("start", "boot", "1")]
        records += span_pair("cli.slow", 9.0, "2", parent="1")
        records += heartbeats
        records += span_pair("cli.fast", 1.0, "3", parent="1")
        records.append(record("end", "boot", "1", dur=20.0))
        return numbered(records)

    beats = [
        record("mark", "boot.heartbeat", format(n, "x"), parent="1")
        for n in range(10, 14)
    ]
    plain = write_lines(tmp_path, [tagged(r) for r in trace([])], "plain.txt")
    beating = write_lines(tmp_path, [tagged(r) for r in trace(beats)], "beating.txt")

    plain_code, plain_out, _ = run_report(capsys, plain)
    beat_code, beat_out, _ = run_report(capsys, beating)

    assert plain_code == beat_code == 0
    # The raw ``events:`` count legitimately includes the marks; nothing else may differ.
    assert re.sub(r"events: \d+", "events: N", beat_out) == re.sub(
        r"events: \d+", "events: N", plain_out
    )
