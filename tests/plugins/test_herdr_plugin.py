"""Tests for the built-in herdr integration plugin.

code-puppy reports working/blocked/idle *authoritatively* -- state is a pure
function of run-depth (working) and the ``awaiting_user_input`` signal
(blocked), with no heartbeat and nothing for herdr to infer from the screen.

Covers:

* ``HerdrReporter`` -- the event -> state machine (dedup, refcount,
  blocked/idle arbitration), driven through a fake client.
* the core wiring -- ``command_runner.set_awaiting_user_input`` firing the
  ``awaiting_user_input`` callback that feeds the reporter.
* ``HerdrClient`` -- the socket transport (env-gated activation, a real
  ``AF_UNIX`` round-trip, seq monotonicity, and retry-until-acked delivery).
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
from code_puppy.plugins.herdr.reporter import BLOCKED, IDLE, WORKING, HerdrReporter


class FakeClient:
    """Records report calls instead of touching a socket."""

    def __init__(self, active: bool = True) -> None:
        self.active = active
        self.states: list[tuple[str, str | None]] = []
        self.sessions: list[str] = []
        self.closed = False

    def report_state(self, state, agent_session_id=None):
        self.states.append((state, agent_session_id))

    def report_session(self, agent_session_id):
        self.sessions.append(agent_session_id)

    def close(self):
        self.closed = True


def _states(fake: FakeClient) -> list[str]:
    return [s for s, _ in fake.states]


# --- reporter state machine ------------------------------------------------


def test_reporter_working_from_run_depth():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_run_end()
    assert _states(fake) == [WORKING, IDLE]


def test_reporter_full_turn_cycle():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_startup()  # idle
    r.on_user_prompt()  # (session capture only)
    r.on_run_start()  # working
    r.on_run_end()  # depth 0 -> idle
    assert _states(fake) == [IDLE, WORKING, IDLE]


def test_reporter_subagent_refcount_stays_working():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # root: depth 1, working
    r.on_run_start()  # subagent: depth 2
    r.on_run_end()  # subagent done: depth 1 -> NOT idle yet
    assert _states(fake) == [WORKING]
    r.on_run_end()  # root done: depth 0 -> idle
    assert _states(fake) == [WORKING, IDLE]


def test_reporter_blocked_from_awaiting_then_recovers():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # working
    r.on_awaiting_user_input(True)  # blocked (shell approval / ask / menu)
    r.on_awaiting_user_input(False)  # run still in flight -> working
    assert _states(fake) == [WORKING, BLOCKED, WORKING]


def test_reporter_awaiting_takes_priority_over_working():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True)
    r.on_run_start()  # nested run while blocked must stay blocked
    assert _states(fake)[-1] == BLOCKED


def test_reporter_awaiting_at_idle_shows_blocked():
    # A menu/picker opened at the prompt (no run in flight) is still blocked.
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_awaiting_user_input(True)
    r.on_awaiting_user_input(False)
    assert _states(fake) == [BLOCKED, IDLE]


def test_reporter_dedupes_repeated_state():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(False)  # already working -> no new report
    assert _states(fake) == [WORKING]


def test_reporter_turn_end_resets_depth():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_run_start()
    r.on_turn_end()  # turn boundary forces idle regardless of depth
    assert _states(fake)[-1] == IDLE


def test_reporter_cancel_clears_awaiting():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True)
    r.on_run_cancel()  # -> idle, awaiting cleared
    assert _states(fake)[-1] == IDLE
    r.on_awaiting_user_input(False)  # stale clear must not resurrect working
    assert _states(fake)[-1] == IDLE


def test_reporter_no_heartbeat_no_background_chatter():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    settled = len(fake.states)
    time.sleep(0.2)
    assert len(fake.states) == settled  # no heartbeat -> no re-asserts
    assert not hasattr(r, "_heartbeat")


def test_reporter_reports_session_once():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start("sess-1")
    r.on_run_start("sess-1")  # same id, no re-report
    assert fake.sessions == ["sess-1"]
    assert all(sid == "sess-1" for _, sid in fake.states)


def test_reporter_shutdown_closes_client():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_shutdown()
    assert fake.closed is True


# --- core wiring: set_awaiting_user_input fires the callback ----------------


def test_set_awaiting_user_input_fires_callback():
    from code_puppy import callbacks
    from code_puppy.tools.command_runner import set_awaiting_user_input

    seen: list[bool] = []
    callbacks.register_callback(
        "awaiting_user_input", lambda awaiting: seen.append(awaiting)
    )
    try:
        set_awaiting_user_input(True)
        set_awaiting_user_input(False)
    finally:
        callbacks._callbacks["awaiting_user_input"].clear()
    assert seen == [True, False]


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
