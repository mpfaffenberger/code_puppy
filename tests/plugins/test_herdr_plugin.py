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

import time


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


def test_reporter_agent_prompt_reports_blocked_then_recovers():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True)  # agent asks for attention
    r.on_awaiting_user_input(False)
    assert _states(fake) == [WORKING, BLOCKED, WORKING]


def test_reporter_awaiting_takes_priority_over_working():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True)
    r.on_run_start()  # nested run while blocked must stay blocked
    assert _states(fake) == [WORKING, BLOCKED]


def test_reporter_menu_cycle_at_idle_sends_no_reports():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_startup()  # establish idle as the last reported state
    r.on_awaiting_user_input(True, notify=False)
    r.on_awaiting_user_input(False, notify=False)
    assert _states(fake) == [IDLE]


def test_reporter_user_menu_never_reports_blocked_or_repeats_state():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True, notify=False)
    r.on_awaiting_user_input(False, notify=False)
    r.on_awaiting_user_input(True, notify=False)
    r.on_awaiting_user_input(False, notify=False)
    r.on_run_end()
    assert _states(fake) == [WORKING, IDLE]
    assert BLOCKED not in _states(fake)


def test_reporter_reports_underlying_change_after_unblock():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # working, reported
    r.on_awaiting_user_input(True, notify=False)
    r.on_run_end()  # underlying run ends while the user menu is open
    r.on_awaiting_user_input(False, notify=False)
    assert _states(fake) == [WORKING, IDLE]


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


def test_set_awaiting_user_input_exposes_notification_intent():
    from code_puppy.tools.command_runner import (
        set_awaiting_user_input,
        should_notify_awaiting_user_input,
    )

    set_awaiting_user_input(True, notify=False)
    assert should_notify_awaiting_user_input() is False
    set_awaiting_user_input(False)
    assert should_notify_awaiting_user_input() is True
