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
from unittest.mock import patch


from code_puppy_core_plugins.herdr.reporter import (
    AWAITING,
    BLOCKED,
    IDLE,
    THINKING,
    WORKING,
    HerdrReporter,
)


class FakeClient:
    """Records report calls instead of touching a socket."""

    def __init__(self, active: bool = True) -> None:
        self.active = active
        self.states: list[tuple[str, str | None]] = []
        self.activity: list[tuple[str, str | None, bool]] = []
        self.sessions: list[tuple[str, str]] = []
        self.metadata: list[dict] = []
        self.closed = False

    def report_state(
        self, state, agent_session_id=None, *, message=None, critical=True
    ):
        self.states.append((state, agent_session_id))
        self.activity.append((state, message, critical))

    def report_session(self, agent_session_id, session_path=None):
        self.sessions.append((agent_session_id, session_path))

    def report_metadata(self, tokens):
        self.metadata.append(tokens)

    def release_and_close(self, timeout_s=1.0):
        self.closed = True

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


def test_reporter_reports_durable_session_once_on_prompt():
    """Session comes from the durable ref (name, path), not the run group_id."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    ref = ("auto_session_x", "/tmp/autosaves/auto_session_x.pkl")
    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_session_ref",
        return_value=ref,
    ):
        r.on_user_prompt("group-uuid-ignored")
        r.on_user_prompt("another-group-uuid")  # unchanged ref -> no re-report
    assert fake.sessions == [ref]
    # State reports carry the durable session NAME, never a group_id.
    r.on_run_start("group-uuid-ignored")
    assert all(sid in (None, "auto_session_x") for _, sid in fake.states)


def test_reporter_reports_session_again_when_ref_changes():
    """A new session (e.g. after /clear or resume) refreshes on the next prompt."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    ref1 = ("auto_session_a", "/tmp/a.pkl")
    ref2 = ("auto_session_b", "/tmp/b.pkl")
    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_session_ref",
        side_effect=[ref1, ref2],
    ):
        r.on_user_prompt()
        r.on_user_prompt()
    assert fake.sessions == [ref1, ref2]


def test_reporter_ignores_per_run_group_id_for_session():
    """Passing a group_id to run_start must not produce a session report."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_session_ref",
        return_value=None,
    ):
        r.on_run_start("group-uuid")
        r.on_run_end("group-uuid")
    assert fake.sessions == []


def test_reporter_session_resolved_outside_lock():
    fake = FakeClient()
    r = HerdrReporter(fake)
    observed = {}

    def _probe():
        observed["locked"] = r._lock.locked()
        return ("n", "/p")

    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_session_ref",
        side_effect=_probe,
    ):
        r.on_user_prompt()
    assert observed["locked"] is False


def test_reporter_shutdown_releases_without_intermediate_idle():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # working reported
    fake.states.clear()
    r.on_shutdown()
    assert fake.closed is True
    # No intermediate idle report on shutdown -- release only.
    assert fake.states == []


# --- Phase 3: pane metadata at interactive turn end ------------------------


def test_reporter_emits_metadata_at_turn_end():
    """A completed interactive turn refreshes pane metadata (decorative)."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    payload = {"model": "claude", "context": "42%", "tokens": "48k/200k"}
    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_tokens_payload",
        return_value=payload,
    ):
        r.on_run_start()
        r.on_turn_end()
    assert fake.metadata == [payload]


def test_reporter_skips_metadata_when_payload_unavailable():
    """No usage -> no metadata report (pane keeps last good values / TTL)."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_tokens_payload",
        return_value=None,
    ):
        r.on_run_start()
        r.on_turn_end()
    assert fake.metadata == []


def test_reporter_metadata_computed_outside_lock():
    """Token payload resolution must never happen under the reporter lock."""
    fake = FakeClient()
    r = HerdrReporter(fake)
    observed = {}

    def _probe():
        observed["locked"] = r._lock.locked()
        return {"context": "1%", "tokens": "1k/200k"}

    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.current_tokens_payload",
        side_effect=_probe,
    ):
        r.on_turn_end()
    assert observed["locked"] is False


# --- Phase 4: decorative activity messages ---------------------------------


def _activity(fake: FakeClient) -> list[tuple[str, str | None, bool]]:
    return fake.activity


def test_outer_run_start_carries_thinking_message_critically():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    assert _activity(fake) == [(WORKING, THINKING, True)]


def test_tool_start_is_decorative_running_message_same_state():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # (WORKING, thinking, critical)
    r.on_tool_start("read_file")
    # Same WORKING state, new activity -> decorative (critical=False).
    assert _activity(fake)[-1] == (WORKING, "running read file", False)
    # State never mutated by the tool callback.
    assert _states(fake) == [WORKING, WORKING]


def test_tool_complete_reverts_to_thinking_decoratively():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_tool_start("read_file")
    r.on_tool_complete()
    assert _activity(fake)[-1] == (WORKING, THINKING, False)
    assert all(s == WORKING for s in _states(fake))


def test_activity_dedupes_on_state_and_message():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_tool_start("read_file")
    r.on_tool_start("read_file")  # identical (state, message) -> no re-send
    running = [a for a in _activity(fake) if a[1] == "running read file"]
    assert len(running) == 1


def test_tool_callbacks_never_change_state():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_tool_start("a_tool")
    r.on_tool_complete()
    r.on_tool_start("b_tool")
    r.on_run_end()
    # State is a pure function of run depth here: working ... then idle once.
    assert _states(fake)[0] == WORKING
    assert _states(fake)[-1] == IDLE
    assert _states(fake).count(IDLE) == 1


def test_blocked_message_is_awaiting_input():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_awaiting_user_input(True)
    assert _activity(fake)[-1] == (BLOCKED, AWAITING, True)
    r.on_awaiting_user_input(False)
    # Back to working -> activity restored to thinking, critical edge.
    assert _activity(fake)[-1] == (WORKING, THINKING, True)


def test_notify_false_menu_leaks_no_message():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()
    r.on_tool_start("read_file")
    r.on_awaiting_user_input(True, notify=False)
    r.on_awaiting_user_input(False, notify=False)
    # No BLOCKED / awaiting message ever surfaced.
    assert BLOCKED not in _states(fake)
    assert AWAITING not in [m for _, m, _ in _activity(fake)]


def test_subagent_start_keeps_activity_no_duplicate_thinking():
    fake = FakeClient()
    r = HerdrReporter(fake)
    r.on_run_start()  # outer -> thinking
    r.on_tool_start("read_file")  # running read file
    r.on_run_start()  # nested subagent run: must NOT reset to thinking
    # No new report for the nested start (state + message both unchanged).
    assert _activity(fake)[-1] == (WORKING, "running read file", False)


def test_tool_start_resolves_message_outside_lock():
    fake = FakeClient()
    r = HerdrReporter(fake)
    observed = {}

    def _probe(name):
        observed["locked"] = r._lock.locked()
        return f"running {name}"

    with patch(
        "code_puppy_core_plugins.herdr.reporter.sources.activity_message",
        side_effect=_probe,
    ):
        r.on_run_start()
        r.on_tool_start("read_file")
    assert observed["locked"] is False


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
