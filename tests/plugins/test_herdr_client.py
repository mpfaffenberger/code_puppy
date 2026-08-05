"""Tests for the herdr socket transport (``HerdrClient``).

Split out from ``test_herdr_plugin.py`` (which keeps the reporter state
machine + core wiring) so each file stays well under the 600-line cap.

Covers env-gated activation, a real ``AF_UNIX`` round-trip, the Windows
named-pipe transport (activation without ``AF_UNIX`` plus a real pipe
round-trip against a ctypes pipe server), seq monotonicity,
retry-until-acked delivery, and the protocol-16 additions:
coalescing critical/decorative lanes, wire-order seq assignment, pane
metadata, and bounded idempotent release.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time

import pytest

import code_puppy.plugins.herdr.client as cl
from code_puppy.plugins.herdr.client import AGENT, SOURCE, HerdrClient


# --- client activation guard ----------------------------------------------


def test_client_inactive_without_env(monkeypatch):
    for var in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_PANE_ID"):
        monkeypatch.delenv(var, raising=False)
    client = HerdrClient()
    assert client.active is False
    client.report_state("working")  # inert, never raises


def test_client_inactive_when_env_incomplete(monkeypatch):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.delenv("HERDR_SOCKET_PATH", raising=False)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    assert HerdrClient().active is False


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_client_sends_report_over_socket(monkeypatch):
    tmpdir = tempfile.mkdtemp()
    sock_path = os.path.join(tmpdir, "herdr.sock")

    received: list[bytes] = []
    ready = threading.Event()

    def serve():
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        ready.set()
        conn, _ = server.accept()
        with conn:
            data = conn.recv(65536)
            received.append(data)
            conn.sendall(b'{"result":{"type":"ok"}}\n')  # ack so send completes
        server.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    ready.wait(timeout=2)

    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", sock_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")

    client = HerdrClient()
    assert client.active is True
    client.report_state("working", agent_session_id="sess-42")

    t.join(timeout=3)
    assert received, "herdr listener never received a report"

    line = received[0].decode("utf-8").strip().splitlines()[0]
    envelope = json.loads(line)
    assert envelope["method"] == "pane.report_agent"
    params = envelope["params"]
    assert params["pane_id"] == "w1:p1"
    assert params["source"] == SOURCE
    assert params["agent"] == AGENT
    assert params["state"] == "working"
    assert params["agent_session_id"] == "sess-42"
    assert isinstance(params["seq"], int)


# --- Windows named-pipe transport -----------------------------------------

_IS_WINDOWS = os.name == "nt"


@pytest.mark.skipif(not _IS_WINDOWS, reason="named-pipe transport is windows-only")
def test_client_active_on_windows_without_af_unix(monkeypatch):
    """Windows has no ``socket.AF_UNIX``; the pipe transport must still arm."""
    assert not hasattr(socket, "AF_UNIX")  # the premise of the whole feature
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", r"C:\nonexistent\herdr.sock")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    client = HerdrClient()
    assert client.active is True
    client.close()


def _serve_one_pipe_request(pipe_name: str, received: list, ready: threading.Event):
    """Minimal one-shot named-pipe server (what herdr's Windows build does)."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.CreateNamedPipeW.restype = wintypes.HANDLE
    PIPE_ACCESS_DUPLEX = 0x3
    handle = k32.CreateNamedPipeW(
        pipe_name, PIPE_ACCESS_DUPLEX, 0, 1, 65536, 65536, 0, None
    )
    assert handle not in (0, wintypes.HANDLE(-1).value), "CreateNamedPipeW failed"
    ready.set()
    k32.ConnectNamedPipe(wintypes.HANDLE(handle), None)
    buf = ctypes.create_string_buffer(65536)
    n = wintypes.DWORD()
    k32.ReadFile(wintypes.HANDLE(handle), buf, 65536, ctypes.byref(n), None)
    received.append(buf.raw[: n.value])
    reply = b'{"result":{"type":"ok"}}\n'
    k32.WriteFile(wintypes.HANDLE(handle), reply, len(reply), ctypes.byref(n), None)
    k32.FlushFileBuffers(wintypes.HANDLE(handle))
    k32.DisconnectNamedPipe(wintypes.HANDLE(handle))
    k32.CloseHandle(wintypes.HANDLE(handle))


@pytest.mark.skipif(not _IS_WINDOWS, reason="named-pipe transport is windows-only")
def test_client_sends_report_over_named_pipe(monkeypatch):
    """Full round-trip over the ``\\\\.\\pipe\\<HERDR_SOCKET_PATH>`` mapping."""
    sock_path = os.path.join(tempfile.mkdtemp(), "herdr.sock")
    pipe_name = "\\\\.\\pipe\\" + sock_path

    received: list[bytes] = []
    ready = threading.Event()
    t = threading.Thread(
        target=_serve_one_pipe_request, args=(pipe_name, received, ready), daemon=True
    )
    t.start()
    assert ready.wait(timeout=2)

    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", sock_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")

    client = HerdrClient()
    assert client.active is True
    client.report_state("working", agent_session_id="sess-42")

    t.join(timeout=3)
    assert received, "pipe server never received a report"

    envelope = json.loads(received[0].decode("utf-8").strip().splitlines()[0])
    assert envelope["method"] == "pane.report_agent"
    params = envelope["params"]
    assert params["pane_id"] == "w1:p1"
    assert params["source"] == SOURCE
    assert params["agent"] == AGENT
    assert params["state"] == "working"
    assert params["agent_session_id"] == "sess-42"


def test_client_seq_strictly_increases(monkeypatch):
    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", "/nonexistent/herdr.sock")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    client = HerdrClient()
    seqs = [client._next_seq() for _ in range(100)]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    client.close()
    time.sleep(0.05)


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_client_retries_until_herdr_acks(monkeypatch):
    """A dropped report (no ack) is retried, then delivered exactly once.

    With code-puppy authoritative AND herdr no longer screen-scraping, a lost
    edge has no safety net, so delivery must be reliable. Re-sending the same
    envelope is safe because herdr dedupes on ``seq``.
    """
    monkeypatch.setattr(cl, "_SEND_BACKOFF_S", 0.02)
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "herdr.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(8)

    received: list[str] = []
    conn_count = {"n": 0}

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            conn_count["n"] += 1
            if conn_count["n"] == 1:
                conn.close()  # drop first connection without acking
                continue
            received.append(conn.recv(65536).decode())
            conn.sendall(b'{"result":{"type":"ok"}}\n')
            conn.close()

    threading.Thread(target=serve, daemon=True).start()

    client = HerdrClient(socket_path=sock_path, pane_id="w1:p1")
    client._active = True
    if client._worker is None:
        client._start_worker()
    try:
        client.report_state("working", "sess-1")
        time.sleep(0.4)
    finally:
        server.close()

    assert conn_count["n"] >= 2, "first drop should trigger a retry"
    assert len(received) == 1, "report must be delivered exactly once"
    assert json.loads(received[0])["params"]["state"] == "working"


# --- Phase 2: coalescing lanes, wire-order seq, bounded release -------------


def _inert_client(monkeypatch):
    """An inactive client whose worker never starts, for slot-logic unit tests."""
    for var in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_PANE_ID"):
        monkeypatch.delenv(var, raising=False)
    c = HerdrClient()
    assert c.active is False
    assert c._worker is None
    return c


def test_take_next_prioritizes_critical_over_decorative(monkeypatch):
    """Drain order: state -> session -> message -> metadata -> release."""
    c = _inert_client(monkeypatch)
    c._state = {"state": "working"}
    c._session = {"agent_session_id": "s1"}
    c._message = {"state": "working", "message": "running foo"}
    c._metadata = {"tokens": {"model": "m"}}
    with c._cond:
        order = []
        job = c._take_next_locked()
        while job is not None:
            order.append(job)
            job = c._take_next_locked()
    methods = [m for m, _ in order]
    assert methods == [
        cl._M_STATE,  # critical state
        cl._M_SESSION,  # critical session
        cl._M_STATE,  # decorative message (still report_agent)
        cl._M_METADATA,  # decorative metadata
    ]


def test_decorative_saturation_cannot_displace_critical(monkeypatch):
    """A hammered decorative lane never pushes a critical state edge back."""
    c = _inert_client(monkeypatch)
    c._state = {"state": "blocked"}
    for i in range(1000):  # saturate decorative -- latest-wins, so it coalesces
        c._metadata = {"tokens": {"n": str(i)}}
    with c._cond:
        method, params = c._take_next_locked()
    assert method == cl._M_STATE
    assert params["state"] == "blocked"


def test_closing_discards_decorative_but_keeps_release(monkeypatch):
    """Once closing, decorative work is dropped and release becomes terminal."""
    c = _inert_client(monkeypatch)
    c._message = {"state": "idle", "message": "thinking"}
    c._metadata = {"tokens": {"model": "m"}}
    c._closing = True
    c._release = {}
    with c._cond:
        first = c._take_next_locked()
        second = c._take_next_locked()
    assert first[0] == cl._M_RELEASE
    assert second is None  # decorative work was skipped entirely


def test_closing_flushes_pending_critical_before_release(monkeypatch):
    """A pending critical edge still flushes ahead of the release."""
    c = _inert_client(monkeypatch)
    c._state = {"state": "idle"}
    c._closing = True
    c._release = {}
    with c._cond:
        first = c._take_next_locked()
        second = c._take_next_locked()
    assert first[0] == cl._M_STATE
    assert second[0] == cl._M_RELEASE


def test_put_refuses_new_work_after_release_scheduled(monkeypatch):
    """New reports after a scheduled release must not add wire events."""
    c = _inert_client(monkeypatch)
    c._active = True  # allow _put past its activation guard
    c._schedule_release()
    c.report_state("working")
    c.report_metadata({"model": "m"})
    assert c._state is None
    assert c._metadata is None
    assert c._release == {}


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_metadata_envelope_carries_agent_applies_to_and_ttl(monkeypatch):
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "herdr.sock")
    received: list[str] = []
    ready = threading.Event()

    def serve():
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        ready.set()
        conn, _ = server.accept()
        with conn:
            received.append(conn.recv(65536).decode())
            conn.sendall(b'{"result":{"type":"ok"}}\n')
        server.close()

    threading.Thread(target=serve, daemon=True).start()
    ready.wait(timeout=2)

    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", sock_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    client = HerdrClient()
    client.report_metadata({"model": "claude", "context": "42%", "tokens": "48k/200k"})
    time.sleep(0.4)

    assert received, "herdr listener never received metadata"
    env = json.loads(received[0].splitlines()[0])
    assert env["method"] == "pane.report_metadata"
    p = env["params"]
    assert p["agent"] == AGENT
    assert p["applies_to_source"] == SOURCE
    assert p["ttl_ms"] == cl._METADATA_TTL_MS
    assert p["tokens"]["model"] == "claude"


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_release_is_sent_and_precedes_worker_exit(monkeypatch):
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "herdr.sock")
    methods: list[str] = []
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(8)

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            data = conn.recv(65536).decode()
            if data.strip():
                methods.append(json.loads(data.splitlines()[0])["method"])
            conn.sendall(b'{"result":{"type":"ok"}}\n')
            conn.close()

    threading.Thread(target=serve, daemon=True).start()

    monkeypatch.setenv("HERDR_ENV", "1")
    monkeypatch.setenv("HERDR_SOCKET_PATH", sock_path)
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p1")
    client = HerdrClient()
    client.report_state("working")
    time.sleep(0.15)
    client.release_and_close(timeout_s=1.0)
    client._worker.join(timeout=1.0)
    server.close()

    assert client._worker is not None and not client._worker.is_alive()
    assert "pane.release_agent" in methods
    assert methods[-1] == "pane.release_agent"  # release is the final wire event


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_release_and_close_is_bounded_when_herdr_hangs(monkeypatch):
    """A herdr that accepts but never acks cannot exceed the caller timeout."""
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "herdr.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(8)
    held: list = []

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            held.append(conn)  # accept, read nothing, never ack -> recv times out

    threading.Thread(target=serve, daemon=True).start()

    client = HerdrClient(socket_path=sock_path, pane_id="w1:p1")
    client._active = True
    client._start_worker()
    client.report_state("working")

    start = time.monotonic()
    client.release_and_close(timeout_s=0.2)
    elapsed = time.monotonic() - start
    server.close()
    # Bounded by the caller timeout, not by the (slow, retrying) worker.
    assert elapsed < 0.6


def test_release_and_close_is_idempotent(monkeypatch):
    c = _inert_client(monkeypatch)
    c._active = True
    c._schedule_release()
    first_release = c._release
    c._schedule_release()  # second call must not re-arm
    assert c._release_scheduled is True
    assert c._release is first_release


@pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX transport is unix-only"
)
def test_send_retries_reuse_one_seq(monkeypatch):
    """One ``_send`` assigns exactly one seq, however many attempts it makes."""
    monkeypatch.setattr(cl, "_SEND_BACKOFF_S", 0.0)
    tmp = tempfile.mkdtemp()
    sock_path = os.path.join(tmp, "herdr.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(8)
    conn_count = {"n": 0}

    def serve():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            conn_count["n"] += 1
            if conn_count["n"] == 1:
                conn.close()  # drop first -> force a retry
                continue
            conn.recv(65536)
            conn.sendall(b'{"result":{"type":"ok"}}\n')
            conn.close()

    threading.Thread(target=serve, daemon=True).start()

    client = HerdrClient(socket_path=sock_path, pane_id="w1:p1")
    client._active = True

    seq_calls = {"n": 0}
    real_next_seq = client._next_seq

    def counting_next_seq():
        seq_calls["n"] += 1
        return real_next_seq()

    monkeypatch.setattr(client, "_next_seq", counting_next_seq)
    client._send(cl._M_STATE, {"state": "working"})
    server.close()

    assert conn_count["n"] >= 2, "first drop should have forced a retry"
    assert seq_calls["n"] == 1, "retries must reuse the same seq / envelope"
