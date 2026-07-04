"""Tests for the built-in herdr integration plugin.

Covers the two units that carry the logic:

* ``HerdrReporter`` -- the event -> state machine (dedup, refcount,
  blocked/idle arbitration), driven through a fake client.
* ``HerdrClient`` -- the socket transport, verified end-to-end against a
  real ``AF_UNIX`` listener, plus the env-gated activation guard.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time

import pytest

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


# --- reporter state machine ------------------------------------------------


def test_reporter_dedupes_repeated_state():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start()
    r.on_tool_call("read_file")  # still working -> no new report
    r.on_tool_done()  # still working -> no new report

    assert [s for s, _ in fake.states] == [WORKING]


def test_reporter_full_turn_cycle():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_startup()  # idle
    r.on_user_prompt()  # working
    r.on_run_start()  # working (deduped)
    r.on_tool_call("grep")  # working (deduped)
    r.on_tool_done()
    r.on_run_end()  # depth 0 -> idle

    assert [s for s, _ in fake.states] == [IDLE, WORKING, IDLE]


def test_reporter_subagent_refcount_stays_working():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start()  # root: depth 1, working
    r.on_run_start()  # subagent: depth 2
    r.on_run_end()  # subagent done: depth 1 -> NOT idle yet
    assert [s for s, _ in fake.states] == [WORKING]

    r.on_run_end()  # root done: depth 0 -> idle
    assert [s for s, _ in fake.states] == [WORKING, IDLE]


def test_reporter_ask_user_question_blocks_then_recovers():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start()  # working
    r.on_tool_call("ask_user_question")  # blocked
    r.on_tool_done()  # working again

    assert [s for s, _ in fake.states] == [WORKING, BLOCKED, WORKING]


def test_reporter_permission_prompt_blocks():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start()  # working
    r.on_permission_prompt()  # blocked

    assert fake.states[-1][0] == BLOCKED


def test_reporter_turn_end_resets_depth():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start()
    r.on_run_start()
    r.on_turn_end()  # turn boundary forces idle regardless of depth

    assert fake.states[-1][0] == IDLE


def test_reporter_reports_session_once():
    fake = FakeClient()
    r = HerdrReporter(fake)

    r.on_run_start("sess-1")
    r.on_tool_call("read_file")
    r.on_run_start("sess-1")  # same id, no re-report

    assert fake.sessions == ["sess-1"]
    # every state report carries the remembered session id
    assert all(sid == "sess-1" for _, sid in fake.states)


def test_reporter_shutdown_closes_client():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_shutdown()
    assert fake.closed is True


# --- client activation guard ----------------------------------------------


def test_client_inactive_without_env(monkeypatch):
    for var in ("HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_PANE_ID"):
        monkeypatch.delenv(var, raising=False)
    client = HerdrClient()
    assert client.active is False
    # inert: reporting is a no-op, never raises
    client.report_state("working")


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
    # drain (socket path is bogus; sends fail soft on the worker)
    client.close()
    time.sleep(0.05)
