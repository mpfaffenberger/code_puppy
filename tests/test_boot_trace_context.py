"""Tests for boot-trace parenting, phase/attr validation and fail-open behaviour."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import code_puppy.boot_trace as bt
from tests.boot_trace_support import (
    TIMEOUT,
    FakeSink,
    _e,
    _shape,
    make_clock,
    traced_loader,
)


@pytest.fixture
def clock(monkeypatch):
    return make_clock(monkeypatch)


@pytest.fixture
def traced(clock):
    yield from traced_loader()


# --- parenting -----------------------------------------------------------------


def test_nested_spans_parent_to_enclosing_span_and_restore(traced):
    sink = traced()
    bt.begin_boot()
    with bt.span("t.outer") as outer:
        with bt.span("t.inner"):
            pass
        restored = bt.current_span() is outer
    assert (_shape(sink)[2:], restored) == (
        [
            _e(sink, 3, phase="t.outer", span="3", parent="1", kind="start", attrs={}),
            _e(sink, 4, phase="t.inner", span="4", parent="3", kind="start", attrs={}),
            _e(
                sink,
                5,
                phase="t.inner",
                span="4",
                parent="3",
                kind="end",
                attrs={},
                durMs=0.0,
            ),
            _e(
                sink,
                6,
                phase="t.outer",
                span="3",
                parent="1",
                kind="end",
                attrs={},
                durMs=0.0,
            ),
        ],
        True,
    )


def test_current_span_restored_after_exception(traced):
    sink = traced()
    bt.begin_boot()
    with bt.span("t.outer") as outer:
        with pytest.raises(ValueError):
            with bt.span("t.inner"):
                raise ValueError("inner failed")
        restored = bt.current_span() is outer
    inner_end = _shape(sink)[4]
    assert (restored, bt.current_span().id, inner_end["kind"], inner_end["attrs"]) == (
        True,
        None,
        "error",
        {"outcome": "error", "exceptionClass": "ValueError"},
    )


@pytest.mark.parametrize(
    ("explicit", "parent_in_event", "drops"),
    [
        pytest.param("f", "f", 0, id="single-digit"),
        pytest.param("0123456789abcdef", "0123456789abcdef", 0, id="sixteen-digits"),
        pytest.param("ABC", "1", 1, id="uppercase"),
        pytest.param("g", "1", 1, id="non-hex"),
        pytest.param("0" * 17, "1", 1, id="seventeen-digits"),
        pytest.param("", "1", 1, id="empty"),
        pytest.param(5, "1", 1, id="non-string"),
    ],
)
def test_explicit_parent_is_validated_then_falls_back_to_root(
    traced, explicit, parent_in_event, drops
):
    sink = traced()
    bt.begin_boot()
    with bt.span("t.work", parent=explicit):
        pass
    start = _shape(sink)[2]
    assert (start["parent"], sink.drops) == (parent_in_event, drops)


def test_marks_parent_to_current_span_or_root(traced):
    sink = traced()
    bt.begin_boot()
    bt.mark("t.loose", attrs={"count": 1})
    with bt.span("t.outer"):
        bt.mark("t.inside")
    assert _shape(sink)[2:] == [
        _e(
            sink,
            3,
            phase="t.loose",
            span="3",
            parent="1",
            kind="mark",
            attrs={"count": 1},
        ),
        _e(sink, 4, phase="t.outer", span="4", parent="1", kind="start", attrs={}),
        _e(sink, 5, phase="t.inside", span="5", parent="4", kind="mark", attrs={}),
        _e(
            sink,
            6,
            phase="t.outer",
            span="4",
            parent="1",
            kind="end",
            attrs={},
            durMs=0.0,
        ),
    ]


def test_plain_worker_does_not_inherit_span_but_explicit_parent_does(traced):
    sink = traced()
    bt.begin_boot()

    def work(parent):
        seen = bt.current_span().id
        with bt.span("t.worker", parent=parent):
            pass
        return seen

    with bt.span("t.outer") as outer:
        with ThreadPoolExecutor(max_workers=1) as pool:
            plain = pool.submit(work, None).result(timeout=TIMEOUT)
            explicit = pool.submit(work, outer.id).result(timeout=TIMEOUT)
    workers = [
        e for e in _shape(sink) if e["phase"] == "t.worker" and e["kind"] == "start"
    ]
    assert (plain, explicit, [w["parent"] for w in workers]) == (None, None, ["1", "3"])


def test_concurrent_threads_with_captured_parent_pair_up(traced):
    sink = traced()
    bt.begin_boot()
    workers = 8
    barrier = threading.Barrier(workers, timeout=TIMEOUT)

    def open_span(parent_id):
        barrier.wait()
        with bt.span("t.conc", parent=parent_id) as span:
            span.update(count=2)

    with bt.span("t.outer") as outer:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(open_span, outer.id) for _ in range(workers)]
            for future in futures:
                future.result(timeout=TIMEOUT)
    events = _shape(sink)
    starts = [e for e in events if e["phase"] == "t.conc" and e["kind"] == "start"]
    ends = [e for e in events if e["phase"] == "t.conc" and e["kind"] == "end"]
    expected_ids = sorted((format(i, "x"), "3") for i in range(4, 4 + workers))
    assert (
        sorted((e["span"], e["parent"]) for e in starts),
        sorted((e["span"], e["parent"]) for e in ends),
        sorted(e["attrs"]["count"] for e in ends),
    ) == (expected_ids, expected_ids, [2] * workers)


# --- phases and attributes -----------------------------------------------------

VALID_PHASES = ["boot", "a.b", "a_b.c2", "x", "a" * 64]
INVALID_PHASES = ["", "Boot", "1a", "a..b", "a.", ".a", "a" * 65, "a-b", None, 5]


@pytest.mark.parametrize("phase", VALID_PHASES)
def test_valid_phase_emits_start_and_end(traced, phase):
    sink = traced()
    with bt.span(phase):
        pass
    assert _shape(sink) == [
        _e(sink, 1, phase=phase, span="1", kind="start", attrs={}),
        _e(sink, 2, phase=phase, span="1", kind="end", attrs={}, durMs=0.0),
    ]


@pytest.mark.parametrize("phase", INVALID_PHASES)
def test_invalid_phase_is_noop_and_counted(traced, phase):
    sink = traced()
    span = bt.span(phase)
    with span:
        pass
    bt.mark(phase)
    assert (span is bt.current_span(), span.id, _shape(sink), sink.drops) == (
        True,
        None,
        [],
        2,
    )


VALID_ATTRS = [
    pytest.param(("tier", "installed"), id="tier-installed"),
    pytest.param(("tier", "project"), id="tier-project"),
    pytest.param(("count", 0), id="count-zero"),
    pytest.param(("count", 2**53 - 1), id="count-max"),
    pytest.param(("cached", False), id="cached"),
    pytest.param(("network_attempted", True), id="network"),
    pytest.param(("outcome", "control_exit"), id="outcome"),
    pytest.param(("exceptionClass", "x" * 64), id="exception-class-max"),
    pytest.param(("plugin", "ollama"), id="plugin-official"),
    pytest.param(("plugin", "h:" + "a" * 16), id="plugin-hashed"),
]

INVALID_ATTRS = [
    pytest.param(("tier", "nope"), id="tier"),
    pytest.param(("count", True), id="count-bool"),
    pytest.param(("count", 1.0), id="count-float"),
    pytest.param(("count", -1), id="count-negative"),
    pytest.param(("count", 2**53), id="count-too-large"),
    pytest.param(("cached", "yes"), id="cached-str"),
    pytest.param(("network_attempted", 1), id="network-int"),
    pytest.param(("outcome", "boom"), id="outcome"),
    pytest.param(("exceptionClass", "a.b"), id="exception-dotted"),
    pytest.param(("exceptionClass", "x" * 65), id="exception-too-long"),
    pytest.param(("plugin", "myprivate"), id="plugin-unregistered"),
    pytest.param(("plugin", "/abs/path"), id="plugin-path"),
    pytest.param(("plugin", "h:ABCDEF0123456789"), id="plugin-uppercase-hash"),
]


@pytest.mark.parametrize("pair", VALID_ATTRS)
def test_known_attr_with_valid_value_is_kept(traced, pair):
    sink = traced()
    with bt.span("t.attr", attrs={pair[0]: pair[1]}):
        pass
    assert _shape(sink)[0]["attrs"] == {pair[0]: pair[1]} and sink.drops == 0


@pytest.mark.parametrize("pair", INVALID_ATTRS)
def test_known_attr_with_invalid_value_is_dropped_and_counted(traced, pair):
    sink = traced()
    with bt.span("t.attr", attrs={pair[0]: pair[1]}):
        pass
    assert (_shape(sink)[0]["attrs"], sink.drops) == ({}, 1)


@pytest.mark.parametrize(
    ("attrs", "drops"),
    [
        pytest.param("nope", 1, id="string"),
        pytest.param(["plugin"], 1, id="list"),
        pytest.param(None, 0, id="none"),
    ],
)
def test_non_dict_attrs_are_rejected_or_ignored(traced, attrs, drops):
    sink = traced()
    with bt.span("t.attr", attrs=attrs):
        pass
    assert (_shape(sink)[0]["attrs"], sink.drops) == ({}, drops)


def test_unknown_attr_keys_are_silently_dropped(traced):
    sink = traced()
    with bt.span("t.attr", attrs={"bogus": 1, "tier": "builtin"}):
        pass
    assert (_shape(sink)[0]["attrs"], sink.drops) == ({"tier": "builtin"}, 0)


def test_recorder_fails_open_when_sink_raises(traced):
    class RaisingSink(FakeSink):
        def offer(self, event):
            raise RuntimeError("sink is broken")

    traced(sink_cls=RaisingSink)
    ran = []
    bt.begin_boot()
    with bt.span("t.work"):
        ran.append(True)
    with pytest.raises(ValueError):
        with bt.span("t.work"):
            raise ValueError("body error")
    bt.mark("t.m")
    bt.end_boot()
    assert ran == [True]
