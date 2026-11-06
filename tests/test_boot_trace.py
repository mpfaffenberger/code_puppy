"""Tests for the boot-trace recorder: disabled mode, root span, span semantics, units."""

import json
import textwrap
import threading
import time

import pytest

import code_puppy.boot_trace as bt
from tests.boot_trace_support import (
    IDLE_HEARTBEAT_INTERVAL_S,
    TIMEOUT,
    _e,
    _run_py,
    _shape,
    make_clock,
    traced_loader,
)


def _live_heartbeat_threads() -> list:
    return [t for t in threading.enumerate() if t.name == "boot-trace-heartbeat"]


@pytest.fixture
def clock(monkeypatch):
    return make_clock(monkeypatch)


@pytest.fixture
def traced(clock):
    yield from traced_loader()


# --- disabled mode -------------------------------------------------------------

DISABLED_VALUES = [
    None,
    "",
    "0",
    "off",
    "stdout",
    "1",
    "true",
    "Off",
    " stderr",
    "~/x",
    "trace.jsonl",
]


@pytest.mark.parametrize("value", DISABLED_VALUES)
def test_disabled_mode_is_a_shared_noop(traced, value):
    assert traced(value) is None
    assert bt.enabled() is False
    noop = bt.span("a.b")
    with noop as entered:
        inside = (entered is noop, bt.current_span() is noop)
    with pytest.raises(ValueError):
        with bt.span("a.b"):
            raise ValueError("propagates")
    observed = (
        bt.span("c.d", attrs={"tier": "builtin"}) is noop is bt.current_span(),
        noop.id,
        (
            noop.update(count=1),
            noop.set_unit(1, 2),
            noop.skip("cached"),
            noop.error("Foo"),
        ),
        inside,
        bt.plugin_attrs("installed", "ollama"),
        bt.register_plugin_names(("new_name",)),
        (bt.begin_boot(), bt.mark("a.b"), bt.end_boot()),
    )
    assert observed == (
        True,
        None,
        (None, None, None, None),
        (True, True),
        {},
        None,
        (None, None, None),
    )


IMPORT_CHILD = textwrap.dedent(
    """
    import json, sys
    import code_puppy
    before = set(sys.modules)
    import code_puppy.boot_trace
    print(json.dumps(sorted(set(sys.modules) - before)))
    """
)


@pytest.mark.parametrize("value", [None, "0", "off", "relative/x.jsonl", "~x"])
def test_disabled_import_loads_only_the_module(tmp_path, value):
    result = _run_py(IMPORT_CHILD, value, tmp_path)
    assert (result.returncode, json.loads(result.stdout)) == (
        0,
        ["code_puppy.boot_trace"],
    )


def test_variable_is_consumed_so_children_do_not_inherit_it(tmp_path):
    probe = "import os, code_puppy.boot_trace as bt; print(bt.enabled(), os.environ.get('CODE_PUPPY_BOOT_TRACE'))"
    result = _run_py(probe, str(tmp_path / "t.jsonl"), tmp_path)

    assert (result.returncode, result.stdout.strip()) == (0, "True None")


def test_stderr_target_also_loads_the_sink(tmp_path):
    result = _run_py(IMPORT_CHILD, "stderr", tmp_path)
    delta = set(json.loads(result.stdout))
    assert (
        result.returncode,
        {"code_puppy.boot_trace", "code_puppy._boot_trace_sink"} <= delta,
    ) == (0, True)


SILENT_CHILD = textwrap.dedent(
    """
    from code_puppy import boot_trace as bt
    bt.begin_boot()
    with bt.span("a.b") as s:
        s.update(count=1)
    bt.end_boot()
    """
)


def test_unset_env_is_silent_and_writes_nothing(tmp_path):
    result = _run_py(SILENT_CHILD, None, tmp_path)
    assert (
        result.returncode,
        result.stdout,
        result.stderr,
        list((tmp_path / "cwd").iterdir()),
    ) == (0, "", "", [])


# --- root span -----------------------------------------------------------------


def test_reloading_the_recorder_leaves_no_heartbeat_thread_or_beat_behind(traced):
    """Every traced test reloads the module; the old heartbeat must not survive it."""
    traced()
    bt.begin_boot()
    first = bt._rec.heartbeat
    # Pinned by the fixture so a slow runner cannot inject a beat into the
    # exact-event assertions throughout these suites.
    pinned = bt._HEARTBEAT_INTERVAL_S

    sink = traced()  # as if a second traced test ran in the same session
    bt.begin_boot()

    deadline = time.monotonic() + TIMEOUT
    while len(_live_heartbeat_threads()) > 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert (pinned, len(_live_heartbeat_threads()), first is bt._rec.heartbeat) == (
        IDLE_HEARTBEAT_INTERVAL_S,
        1,
        False,
    )
    assert [e["phase"] for e in sink.events] == ["boot", "py.main_reached"]


def test_root_span_lifecycle_emits_once(traced):
    sink = traced()
    assert bt.enabled() is True
    bt.begin_boot()
    bt.begin_boot()
    bt.end_boot()
    bt.end_boot()
    bt.begin_boot()
    assert _shape(sink) == [
        _e(sink, 1, phase="boot", span="1", kind="start", attrs={}),
        _e(
            sink,
            2,
            phase="py.main_reached",
            span="2",
            parent="1",
            kind="mark",
            attrs={},
        ),
        _e(sink, 3, phase="boot", span="1", kind="end", attrs={}, durMs=0.0),
    ]
    assert sink.stops >= 1


ROOT_END_CASES = [
    pytest.param({}, "end", {}, id="no-args"),
    pytest.param({"exit_code": 0}, "end", {}, id="exit-0"),
    pytest.param({"exit_code": None}, "end", {}, id="exit-none"),
    pytest.param({"exit_code": 3}, "error", {"outcome": "control_exit"}, id="exit-3"),
    pytest.param(
        {"exc": ValueError("x")},
        "error",
        {"outcome": "error", "exceptionClass": "ValueError"},
        id="value-error",
    ),
    pytest.param(
        {"exc": KeyboardInterrupt(), "exit_code": 0},
        "error",
        {"outcome": "error", "exceptionClass": "KeyboardInterrupt"},
        id="interrupt-beats-exit-0",
    ),
    pytest.param(
        {"exc": SystemExit(0)},
        "end",
        {"outcome": "control_exit"},
        id="systemexit-0",
    ),
    pytest.param(
        {"exc": SystemExit("boom")},
        "error",
        {"outcome": "control_exit", "exceptionClass": "SystemExit"},
        id="systemexit-str",
    ),
]


@pytest.mark.parametrize(("kwargs", "kind", "attrs"), ROOT_END_CASES)
def test_root_terminal_classification(traced, kwargs, kind, attrs):
    sink = traced()
    bt.begin_boot()
    bt.end_boot(**kwargs)
    assert _shape(sink)[2:] == [
        _e(sink, 3, phase="boot", span="1", kind=kind, attrs=attrs, durMs=0.0)
    ]


def test_end_boot_without_begin_emits_nothing_but_stops(traced):
    sink = traced()
    bt.end_boot()
    assert (sink.events, sink.stops >= 1) == ([], True)


# --- span semantics ------------------------------------------------------------


def _raise_value_error(span):
    raise ValueError("message is never recorded")


def _skip_then_raise(span):
    span.skip("env")
    raise ValueError("hidden")


def _error_then_raise(span):
    span.error("Foo")
    raise KeyError("hidden")


SPAN_CASES = [
    pytest.param(lambda s: None, "end", {}, None, id="plain"),
    pytest.param(
        lambda s: s.error("Foo"),
        "error",
        {"outcome": "error", "exceptionClass": "Foo"},
        None,
        id="error-cls",
    ),
    pytest.param(
        lambda s: (s.error("Foo"), s.update(outcome="timeout")),
        "error",
        {"outcome": "timeout", "exceptionClass": "Foo"},
        None,
        id="error-outcome-override",
    ),
    pytest.param(lambda s: s.skip("cached"), "skip", {}, "cached", id="skip"),
    pytest.param(
        lambda s: (s.skip("cached"), s.error("Foo")),
        "error",
        {"outcome": "error", "exceptionClass": "Foo"},
        None,
        id="error-beats-skip",
    ),
    pytest.param(
        _skip_then_raise,
        "error",
        {"outcome": "error", "exceptionClass": "ValueError"},
        None,
        id="exception-beats-skip",
    ),
    pytest.param(
        _error_then_raise,
        "error",
        {"outcome": "error", "exceptionClass": "KeyError"},
        None,
        id="exception-beats-error",
    ),
]


@pytest.mark.parametrize(("body", "kind", "extra", "reason"), SPAN_CASES)
def test_span_terminal_precedence(traced, body, kind, extra, reason):
    sink = traced()
    bt.begin_boot()
    try:
        with bt.span("t.work", attrs={"tier": "builtin"}) as span:
            body(span)
    except (ValueError, KeyError):
        pass
    terminal = _e(
        sink,
        4,
        phase="t.work",
        span="3",
        parent="1",
        kind=kind,
        attrs={"tier": "builtin", **extra},
        durMs=0.0,
    )
    if reason is not None:
        terminal["reason"] = reason
    start = _e(
        sink,
        3,
        phase="t.work",
        span="3",
        parent="1",
        kind="start",
        attrs={"tier": "builtin"},
    )
    assert _shape(sink)[2:] == [start, terminal]


EXC_CASES = [
    pytest.param(
        ValueError("hidden"),
        "error",
        {"outcome": "error", "exceptionClass": "ValueError"},
        id="value-error",
    ),
    pytest.param(SystemExit(0), "end", {"outcome": "control_exit"}, id="exit-0"),
    pytest.param(SystemExit(None), "end", {"outcome": "control_exit"}, id="exit-none"),
    pytest.param(
        SystemExit(3),
        "error",
        {"outcome": "control_exit", "exceptionClass": "SystemExit"},
        id="exit-3",
    ),
    pytest.param(
        SystemExit("boom"),
        "error",
        {"outcome": "control_exit", "exceptionClass": "SystemExit"},
        id="exit-str",
    ),
    pytest.param(
        KeyboardInterrupt(),
        "error",
        {"outcome": "error", "exceptionClass": "KeyboardInterrupt"},
        id="interrupt",
    ),
]


@pytest.mark.parametrize(("exc", "kind", "extra"), EXC_CASES)
def test_body_exception_is_classified_and_propagated_unchanged(
    traced, exc, kind, extra
):
    sink = traced()
    bt.begin_boot()
    with pytest.raises(BaseException) as raised:
        with bt.span("t.work"):
            raise exc
    assert raised.value is exc
    assert _shape(sink)[-1] == _e(
        sink, 4, phase="t.work", span="3", parent="1", kind=kind, attrs=extra, durMs=0.0
    )


@pytest.mark.parametrize(
    ("reason", "terminal", "drops"),
    [
        pytest.param("acp", {"kind": "skip", "reason": "acp"}, 0, id="acp"),
        pytest.param(
            "disabled", {"kind": "skip", "reason": "disabled"}, 0, id="disabled"
        ),
        pytest.param(
            "not_installed",
            {"kind": "skip", "reason": "not_installed"},
            0,
            id="not_installed",
        ),
        pytest.param("cached", {"kind": "skip", "reason": "cached"}, 0, id="cached"),
        pytest.param("non_tty", {"kind": "skip", "reason": "non_tty"}, 0, id="non_tty"),
        pytest.param("env", {"kind": "skip", "reason": "env"}, 0, id="env"),
        pytest.param(
            "shadowed", {"kind": "skip", "reason": "shadowed"}, 0, id="shadowed"
        ),
        pytest.param("refused", {"kind": "skip", "reason": "refused"}, 0, id="refused"),
        pytest.param("retired", {"kind": "skip", "reason": "retired"}, 0, id="retired"),
        pytest.param("bogus", {"kind": "end"}, 1, id="invalid-reason"),
    ],
)
def test_skip_reason_is_validated(traced, reason, terminal, drops):
    sink = traced()
    with bt.span("t.work") as span:
        span.skip(reason)
    expected_end = _e(
        sink, 2, phase="t.work", span="1", attrs={}, durMs=0.0, **terminal
    )
    start = _e(sink, 1, phase="t.work", span="1", kind="start", attrs={})
    assert (_shape(sink), sink.drops) == ([start, expected_end], drops)


def test_span_mutators_are_ignored_after_exit(traced):
    sink = traced()
    with bt.span("t.work", attrs={"tier": "builtin"}) as span:
        pass
    before = _shape(sink)
    span.update(count=9)
    span.set_unit(1, 2)
    span.skip("cached")
    span.error("Foo")
    assert (_shape(sink), sink.drops) == (before, 0)


# --- units ---------------------------------------------------------------------

UNIT_CASES = [
    pytest.param([(1, 3)], (1, 3), 0, id="accepted"),
    pytest.param([(2, 4)], (0, 3), 1, id="wrong-total"),
    pytest.param([(4, 3)], (0, 3), 1, id="n-above-total"),
    pytest.param([(True, 3)], (0, 3), 1, id="bool"),
    pytest.param([(1.0, 3)], (0, 3), 1, id="float"),
    pytest.param([(-1, 3)], (0, 3), 1, id="negative"),
    pytest.param([(1, 3), (3, 3)], (3, 3), 0, id="last-accepted-wins"),
]


@pytest.mark.parametrize(("calls", "unit", "drops"), UNIT_CASES)
def test_set_unit_accepts_only_fixed_total(traced, calls, unit, drops):
    sink = traced()
    with bt.span("t.loop", unit=(0, 3)) as span:
        for n, of in calls:
            span.set_unit(n, of)
    start = _e(
        sink,
        1,
        phase="t.loop",
        span="1",
        kind="start",
        attrs={},
        unit={"n": 0, "of": 3},
    )
    end = _e(
        sink,
        2,
        phase="t.loop",
        span="1",
        kind="end",
        attrs={},
        durMs=0.0,
        unit={"n": unit[0], "of": unit[1]},
    )
    assert (_shape(sink), sink.drops) == ([start, end], drops)


@pytest.mark.parametrize(
    "unit",
    [(True, 3), (1.0, 3), (-1, 3), (4, 3), (0, 2**53)],
    ids=["bool", "float", "negative", "n-above-total", "total-too-large"],
)
def test_invalid_span_unit_is_dropped_and_counted(traced, unit):
    sink = traced()
    with bt.span("t.loop", unit=unit):
        pass
    start = _e(sink, 1, phase="t.loop", span="1", kind="start", attrs={})
    end = _e(sink, 2, phase="t.loop", span="1", kind="end", attrs={}, durMs=0.0)
    assert (_shape(sink), sink.drops) == ([start, end], 1)


def test_set_unit_without_start_unit_is_rejected(traced):
    sink = traced()
    with bt.span("t.loop") as span:
        span.set_unit(1, 3)
    assert (
        [e for e in _shape(sink) if e["kind"] == "end"][0].get("unit"),
        sink.drops,
    ) == (None, 1)
