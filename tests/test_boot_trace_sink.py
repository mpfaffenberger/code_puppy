"""Tests for the boot-trace writer sink (``code_puppy/_boot_trace_sink.py``)."""

import io
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from collections import namedtuple
from pathlib import Path

import pytest

from code_puppy import _boot_trace_sink as sink_mod
from code_puppy._boot_trace_sink import (
    MAX_LINE,
    MAX_QUEUE,
    STDERR_PREFIX,
    Sink,
    _open,
    _write_all,
)
from tests.boot_trace_support import SUBPROCESS_TIMEOUT_S

BOOT_ID = "ab" * 16
T0_NS = 123_456
WRITER = "boot-trace-writer"
TIMEOUT = 10.0
REPO_ROOT = Path(__file__).resolve().parents[1]
Started = namedtuple("Started", "sink writer")


def _ev(idx: int) -> dict:
    return {"phase": "t.ev", "kind": "mark", "span": "x", "idx": idx, "attrs": {}}


def _rec(seq: int, event: dict) -> dict:
    return {"v": 1, "bootId": BOOT_ID, "seq": seq, **event}


def _line(seq: int, event: dict, prefix: bytes = b"") -> bytes:
    body = json.dumps(
        _rec(seq, event),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    return prefix + body.encode("ascii") + b"\n"


def _mark(seq: int, dropped: int, span: str = "1") -> dict:
    return {
        "v": 1,
        "bootId": BOOT_ID,
        "seq": seq,
        "phase": "boot.dropped",
        "span": span,
        "kind": "mark",
        "attrs": {},
        "dropped": dropped,
    }


def _circular() -> dict:
    loop: dict = {}
    loop["self"] = loop
    return loop


def _without_clock(record: dict) -> dict:
    """Only the drop mark carries clocks here; they are asserted by type, not value."""
    if "tMonoMs" not in record:
        return record
    assert isinstance(record["tMonoMs"], float)
    assert isinstance(record["tWallMs"], int)
    return {k: v for k, v in record.items() if k not in ("tMonoMs", "tWallMs")}


def _records(data: bytes, prefix: bytes = b"") -> list[dict]:
    lines = data.splitlines()
    assert all(line.startswith(prefix) for line in lines)
    return [_without_clock(json.loads(line[len(prefix) :])) for line in lines]


def _wait_until(predicate, timeout: float = TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    pause = threading.Event()
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        pause.wait(0.005)


class _FakeStderr:
    def __init__(self, fd):
        self._fd = fd

    def fileno(self):
        return self._fd


class _Pipe:
    """Read end drained by a thread so a writer never blocks on a full pipe."""

    def __init__(self):
        self.read_fd, self.write_fd = os.pipe()
        self._write_open = True
        self._data = bytearray()
        self._lock = threading.Lock()
        self._eof = threading.Event()
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        try:
            while chunk := os.read(self.read_fd, 65536):
                with self._lock:
                    self._data += chunk
        except OSError:
            pass
        finally:
            self._eof.set()

    @property
    def data(self) -> bytes:
        with self._lock:
            return bytes(self._data)

    def wait_for_lines(self, count: int) -> bytes:
        _wait_until(lambda: self.data.count(b"\n") >= count)
        return self.data

    def finish(self) -> bytes:
        """Close our write end; callers must have joined the writer first."""
        if self._write_open:
            os.close(self.write_fd)
            self._write_open = False
        assert self._eof.wait(TIMEOUT), "pipe never reached EOF"
        return self.data

    def close(self):
        """Teardown path: never asserts, so a failing test cannot hang here."""
        if self._write_open:
            os.close(self.write_fd)
            self._write_open = False
        self._eof.wait(TIMEOUT)
        os.close(self.read_fd)


class _WriteGate:
    """Holds or shortens writes issued by the writer thread; others are real."""

    def __init__(self):
        self._real_write = os.write
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.armed = False
        self.max_bytes = None
        self.zero_bytes = False

    def arm(self):
        self.blocked.clear()
        self.release.clear()
        self.armed = True

    def __call__(self, fd, data):
        if threading.current_thread().name != WRITER:
            return self._real_write(fd, data)
        if self.zero_bytes:
            return 0
        if self.armed:
            self.armed = False
            self.blocked.set()
            if not self.release.wait(TIMEOUT):
                raise OSError("gate was never released")
        if self.max_bytes is not None:
            data = data[: self.max_bytes]
        return self._real_write(fd, data)


@pytest.fixture
def pipe():
    p = _Pipe()
    yield p
    p.close()


@pytest.fixture
def gate(monkeypatch):
    g = _WriteGate()
    monkeypatch.setattr(sink_mod.os, "write", g)
    return g


@pytest.fixture
def start():
    """Build sinks; teardown stops every writer and joins it."""
    started = []

    def _start(target: str) -> Started:
        # A disabled sink's writer can exit before it could be enumerated, so
        # capture the thread object at construction instead.
        threads: list[threading.Thread] = []
        real_thread = threading.Thread

        class RecordingThread(real_thread):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                threads.append(self)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sink_mod.threading, "Thread", RecordingThread)
            sink = Sink(target, boot_id=BOOT_ID, t0_ns=T0_NS)
        (writer,) = threads
        started.append(Started(sink, writer))
        return started[-1]

    yield _start
    for item in started:
        item.sink.request_stop()
    for item in started:
        item.writer.join(TIMEOUT)


def _use_stderr(monkeypatch, fd: int) -> None:
    monkeypatch.setattr(sys, "stderr", _FakeStderr(fd))


def _finish(item: Started, pipe: _Pipe | None = None) -> bytes:
    item.sink.request_stop()
    item.writer.join(TIMEOUT)
    assert not item.writer.is_alive(), "writer did not exit after request_stop"
    return pipe.finish() if pipe is not None else b""


def _hold_first_event(gate: _WriteGate, item: Started) -> None:
    """Park the writer inside its first write so later offers queue deterministically."""
    gate.arm()
    item.sink.offer(_ev(0))
    assert gate.blocked.wait(TIMEOUT)


def _assert_disabled(item: Started) -> None:
    item.writer.join(TIMEOUT)
    assert not item.writer.is_alive(), "disabled sink must let its writer exit"
    item.sink.offer(_ev(0))
    item.sink.record_drop()
    item.sink.request_stop()


# --- stderr target: framing, partial writes, failure ---------------------------


def test_stderr_target_writes_prefixed_compact_ascii_lines(monkeypatch, start, pipe):
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    item.sink.offer(_ev(0))
    item.sink.offer(dict(_ev(1), attrs={"label": "naïve "}))
    data = _finish(item, pipe)
    assert data == (
        _line(1, _ev(0), STDERR_PREFIX)
        + _line(2, dict(_ev(1), attrs={"label": "naïve "}), STDERR_PREFIX)
    )
    assert data.isascii()


def test_partial_writes_reassemble_exactly(monkeypatch, gate, start, pipe):
    gate.max_bytes = 2
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    for idx in range(3):
        item.sink.offer(_ev(idx))
    data = _finish(item, pipe)
    assert data == b"".join(_line(i + 1, _ev(i), STDERR_PREFIX) for i in range(3))


def test_zero_byte_write_disables_sink(monkeypatch, gate, start, pipe):
    gate.zero_bytes = True
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    item.sink.offer(_ev(0))
    _assert_disabled(item)
    assert pipe.finish() == b""


# --- queue overflow and drop-mark coalescing -----------------------------------


def test_blocked_writer_overflow_coalesces_drop_marks(monkeypatch, gate, start, pipe):
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    sink = item.sink
    _hold_first_event(gate, item)

    # Round one: seq 1 in flight, seqs 2..513 queued, K offers dropped.
    rejected = 5
    for idx in range(1, MAX_QUEUE + rejected + 1):
        sink.offer(_ev(idx))
    gate.release.set()

    # Dropped seqs are 514..513+K; the mark takes the next seq after them.
    round_one_mark = MAX_QUEUE + 2 + rejected
    expected = [_rec(i + 1, _ev(i)) for i in range(MAX_QUEUE + 1)]
    expected.append(_mark(round_one_mark, dropped=rejected))
    data = pipe.wait_for_lines(len(expected))
    assert _records(data, STDERR_PREFIX) == expected

    # Round two: the second mark carries the cumulative count, not the delta.
    second_overflow = 3
    gate.arm()
    sink.offer(_ev(1000))
    assert gate.blocked.wait(TIMEOUT)
    for idx in range(1001, 1001 + MAX_QUEUE + second_overflow):
        sink.offer(_ev(idx))
    gate.release.set()

    head = round_one_mark + 1
    expected_round_two = [_rec(head, _ev(1000))]
    expected_round_two += [_rec(head + 1 + j, _ev(1001 + j)) for j in range(MAX_QUEUE)]
    last_seq = head + MAX_QUEUE + second_overflow + 1
    expected_round_two.append(_mark(last_seq, rejected + second_overflow, "2"))
    data = pipe.wait_for_lines(len(expected) + MAX_QUEUE + 2)
    assert _records(data, STDERR_PREFIX)[len(expected) :] == expected_round_two
    _finish(item, pipe)


@pytest.mark.parametrize(
    "bad_event",
    [
        pytest.param(None, id="non-dict-none"),
        pytest.param("not-a-dict", id="non-dict-str"),
        pytest.param({"blob": "x" * MAX_LINE}, id="oversize-line"),
        pytest.param({"x": float("nan")}, id="nan-not-json"),
        pytest.param({"x": {1, 2}}, id="set-not-json"),
        pytest.param(_circular(), id="circular-not-json"),
    ],
)
def test_rejected_event_leaves_seq_gap_and_counts(
    monkeypatch, gate, start, pipe, bad_event
):
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    _hold_first_event(gate, item)
    item.sink.offer(bad_event)
    item.sink.offer(_ev(7))
    gate.release.set()
    data = pipe.wait_for_lines(3)
    # seq 2 is the gap; the mark is allocated after the delivered seq 3.
    assert _records(data, STDERR_PREFIX) == [
        _rec(1, _ev(0)),
        _rec(3, _ev(7)),
        _mark(4, dropped=1),
    ]
    _finish(item, pipe)


def test_producer_rejection_wakes_idle_writer_to_emit_drop_mark(
    monkeypatch, start, pipe
):
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    item.sink.record_drop()
    data = pipe.wait_for_lines(1)
    # seq 1 was consumed by the rejected attempt; the mark takes seq 2.
    assert _records(data, STDERR_PREFIX) == [_mark(2, dropped=1)]
    _finish(item, pipe)


def test_drain_then_exit_ignores_offers_after_stop(monkeypatch, start, pipe):
    _use_stderr(monkeypatch, pipe.write_fd)
    item = start("stderr")
    for idx in range(3):
        item.sink.offer(_ev(idx))
    item.sink.request_stop()
    item.sink.offer(_ev(99))
    item.sink.record_drop()
    data = _finish(item, pipe)
    assert data == b"".join(_line(i + 1, _ev(i), STDERR_PREFIX) for i in range(3))


def test_next_span_id_is_hex_counter_from_one(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    sink = Sink("relative.jsonl", boot_id=BOOT_ID, t0_ns=T0_NS)
    ids = [sink.next_span_id() for _ in range(17)]
    assert ids == [format(n, "x") for n in range(1, 18)]
    sink.request_stop()


# --- low-level helpers ---------------------------------------------------------


def test_write_all_retries_blocking_io(monkeypatch, pipe):
    real_write = os.write
    calls = []

    def flaky(fd, data):
        calls.append(fd)
        if len(calls) == 1:
            raise BlockingIOError(11, "busy")
        return real_write(fd, data)

    monkeypatch.setattr(sink_mod.os, "write", flaky)
    _write_all(pipe.write_fd, b"hello\n")
    assert pipe.finish() == b"hello\n"
    assert len(calls) == 2


def test_write_all_zero_bytes_raises(monkeypatch, pipe):
    monkeypatch.setattr(sink_mod.os, "write", lambda fd, data: 0)
    with pytest.raises(OSError):
        _write_all(pipe.write_fd, b"x\n")


# --- file target ---------------------------------------------------------------


@pytest.mark.parametrize("dir_name", ["trace", "tr ace ünï"])
def test_file_target_writes_untagged_lines(tmp_path, start, dir_name):
    folder = tmp_path / dir_name
    folder.mkdir()
    path = folder / "boot.jsonl"
    item = start(str(path))
    item.sink.offer(_ev(0))
    item.sink.offer(_ev(1))
    _finish(item)
    assert path.read_bytes() == _line(1, _ev(0)) + _line(2, _ev(1))


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_file_target_is_created_mode_0600(tmp_path, start):
    path = tmp_path / "boot.jsonl"
    item = start(str(path))
    _finish(item)
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_existing_file_is_never_overwritten(tmp_path, start):
    path = tmp_path / "boot.jsonl"
    path.write_bytes(b"keep\n")
    item = start(str(path))
    item.sink.offer(_ev(0))
    _finish(item)
    assert path.read_bytes() == b"keep\n"


def _stderr_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stderr", None)
    return "stderr"


def _stderr_fileno_raises(monkeypatch, tmp_path):
    class Broken:
        def fileno(self):
            raise io.UnsupportedOperation("no fileno")

    monkeypatch.setattr(sys, "stderr", Broken())
    return "stderr"


def _stderr_fileno_reserved(fd):
    def setup(monkeypatch, tmp_path):
        _use_stderr(monkeypatch, fd)
        return "stderr"

    return setup


def _relative_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return "relative.jsonl"


def _missing_parent(monkeypatch, tmp_path):
    return str(tmp_path / "missing" / "boot.jsonl")


@pytest.mark.parametrize(
    "make_target",
    [
        pytest.param(_stderr_none, id="stderr-none"),
        pytest.param(_stderr_fileno_raises, id="stderr-fileno-raises"),
        pytest.param(_stderr_fileno_reserved(0), id="stderr-fileno-0"),
        pytest.param(_stderr_fileno_reserved(1), id="stderr-fileno-1"),
        pytest.param(_relative_path, id="relative-path"),
        pytest.param(_missing_parent, id="missing-parent"),
    ],
)
def test_invalid_targets_self_disable(monkeypatch, tmp_path, start, make_target):
    target = make_target(monkeypatch, tmp_path)
    item = start(target)
    _assert_disabled(item)
    assert list(tmp_path.iterdir()) == []


WINDOWS_STYLE_PATHS = [r"C:\x\t.jsonl", r"\\server\share\x"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX path rules")
@pytest.mark.parametrize("path", WINDOWS_STYLE_PATHS)
def test_windows_style_paths_are_rejected_on_posix(path):
    with pytest.raises(ValueError):
        _open(path)


@pytest.mark.skipif(os.name != "nt", reason="Windows path rules")
@pytest.mark.parametrize("path", WINDOWS_STYLE_PATHS)
def test_windows_style_paths_pass_isabs_on_windows(path):
    assert os.path.isabs(path)
    with pytest.raises(OSError):
        _open(path)


# --- subprocess behaviour ------------------------------------------------------

CHILD_FLOOD = textwrap.dedent(
    """
    from code_puppy._boot_trace_sink import MAX_QUEUE, Sink

    sink = Sink("stderr", boot_id="ab" * 16, t0_ns=0)
    for idx in range(4 * MAX_QUEUE):
        sink.offer({"phase": "t.ev", "kind": "mark", "span": "x", "idx": idx,
                    "tMonoMs": 0.0, "tWallMs": 0, "attrs": {"pad": "y" * 100}})
    """
)

CHILD_STDERR = textwrap.dedent(
    """
    from code_puppy._boot_trace_sink import Sink

    sink = Sink("stderr", boot_id="ab" * 16, t0_ns=0)
    for idx in range(3):
        sink.offer({"phase": "t.ev", "kind": "mark", "span": "x", "idx": idx,
                    "tMonoMs": 0.0, "tWallMs": 0, "attrs": {}})
    sink.request_stop()
    """
)


def _run_child(code: str, cwd: Path, **popen_kwargs) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.Popen(
        [sys.executable, "-c", code], env=env, cwd=cwd, **popen_kwargs
    )


def test_exit_is_not_blocked_by_unread_stderr_pipe(tmp_path):
    proc = _run_child(
        CHILD_FLOOD,
        tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.wait(timeout=30) == 0
    finally:
        proc.kill()
        proc.stderr.close()


def test_stderr_target_never_writes_stdout(tmp_path):
    proc = _run_child(
        CHILD_STDERR, tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, _ = proc.communicate(timeout=SUBPROCESS_TIMEOUT_S)
    assert (proc.returncode, out) == (0, b"")
