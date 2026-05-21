"""Tests for the session-channel feature of frontend_emitter.

Covers:
  * ``code_puppy.plugins.frontend_emitter.session_context.current_emitter_session_id`` ContextVar isolation
  * ``emit_event(session_id=...)`` explicit-kwarg precedence
  * ``emit_event`` ContextVar fallback
  * ``emit_event(session_id=None)`` opt-out of ContextVar fallback
  * ``subscribe(session_id=...)`` per-session routing filter
  * Wildcard subscriber still sees session-tagged events
  * Multi-session isolation under concurrent asyncio Tasks
  * Backward compatibility of the legacy 2-arg ``emit_event`` call shape
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from code_puppy.plugins.frontend_emitter.session_context import current_emitter_session_id
from code_puppy.plugins.frontend_emitter.emitter import (
    _recent_events,
    _subscriber_records,
    emit_event,
    get_subscriber_count,
    subscribe,
    unsubscribe,
)

# ─── helpers ─────────────────────────────────────────────────────────────


def _reset_emitter_state() -> None:
    """Wipe in-process subscriber and recent-event state between tests."""
    _subscriber_records.clear()
    _recent_events.clear()


def _drain(q: "asyncio.Queue[Dict[str, Any]]") -> List[Dict[str, Any]]:
    """Drain everything currently in ``q`` without awaiting."""
    out: List[Dict[str, Any]] = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.fixture(autouse=True)
def _emitter_enabled_and_reset():
    """Ensure the emitter is enabled and state is clean for each test."""
    _reset_emitter_state()
    with patch(
        "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_enabled",
        return_value=True,
    ), patch(
        "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_max_recent_events",
        return_value=1000,
    ), patch(
        "code_puppy.plugins.frontend_emitter.emitter.get_frontend_emitter_queue_size",
        return_value=1000,
    ):
        yield
    _reset_emitter_state()


# ─── ContextVar primitive ────────────────────────────────────────────────


class TestContextVar:
    def test_default_is_none(self):
        # Fresh ContextVar in a fresh asyncio Context defaults to None.
        ctx = __import__("contextvars").copy_context()

        def _read() -> Any:
            return current_emitter_session_id.get()

        assert ctx.run(_read) is None

    @pytest.mark.asyncio
    async def test_set_and_reset_roundtrip(self):
        assert current_emitter_session_id.get() is None
        token = current_emitter_session_id.set("sid-1")
        try:
            assert current_emitter_session_id.get() == "sid-1"
        finally:
            current_emitter_session_id.reset(token)
        assert current_emitter_session_id.get() is None

    @pytest.mark.asyncio
    async def test_isolation_across_concurrent_tasks(self):
        """Each asyncio Task gets its own ContextVar snapshot."""

        async def worker(sid: str) -> str:
            token = current_emitter_session_id.set(sid)
            try:
                # Yield to the loop so other workers run in between -- if
                # the ContextVar leaks across tasks, this is where it'd show.
                await asyncio.sleep(0.01)
                seen = current_emitter_session_id.get()
                # Yield again post-read for good measure.
                await asyncio.sleep(0.01)
                assert seen == sid, f"leak: expected {sid}, got {seen}"
                return seen
            finally:
                current_emitter_session_id.reset(token)

        results = await asyncio.gather(*[worker(f"sid-{i}") for i in range(10)])
        assert results == [f"sid-{i}" for i in range(10)]
        # Outer context unchanged.
        assert current_emitter_session_id.get() is None

    @pytest.mark.asyncio
    async def test_reset_runs_even_on_exception(self):
        async def boom() -> None:
            token = current_emitter_session_id.set("doomed")
            try:
                raise RuntimeError("kaboom")
            finally:
                current_emitter_session_id.reset(token)

        with pytest.raises(RuntimeError):
            await boom()
        assert current_emitter_session_id.get() is None


# ─── emit_event session_id precedence ────────────────────────────────────


class TestEmitEventSessionId:
    @pytest.mark.asyncio
    async def test_explicit_kwarg_wins_over_contextvar(self):
        q = subscribe()
        token = current_emitter_session_id.set("ctx-sid")
        try:
            emit_event("explicit-kwarg", {}, session_id="explicit-sid")
        finally:
            current_emitter_session_id.reset(token)
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["session_id"] == "explicit-sid"
        unsubscribe(q)

    @pytest.mark.asyncio
    async def test_contextvar_used_when_kwarg_unset(self):
        q = subscribe()
        token = current_emitter_session_id.set("ctx-sid")
        try:
            emit_event("ctx-fallback", {})
        finally:
            current_emitter_session_id.reset(token)
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["session_id"] == "ctx-sid"
        unsubscribe(q)

    @pytest.mark.asyncio
    async def test_explicit_none_opts_out_of_contextvar_fallback(self):
        """Passing session_id=None explicitly disables the ContextVar fallback."""
        q = subscribe()
        token = current_emitter_session_id.set("ctx-sid")
        try:
            emit_event("opt-out", {}, session_id=None)
        finally:
            current_emitter_session_id.reset(token)
        events = _drain(q)
        assert len(events) == 1
        assert events[0]["session_id"] is None
        unsubscribe(q)

    @pytest.mark.asyncio
    async def test_no_kwarg_no_contextvar_means_none(self):
        q = subscribe()
        emit_event("neither", {})  # no kwarg, no ContextVar set
        events = _drain(q)
        assert events[0]["session_id"] is None
        unsubscribe(q)


# ─── subscribe filter behaviour ──────────────────────────────────────────


class TestSubscribeFilter:
    @pytest.mark.asyncio
    async def test_session_subscriber_receives_only_matching(self):
        q_alice = subscribe(session_id="alice")
        emit_event("e1", {}, session_id="alice")
        emit_event("e2", {}, session_id="bob")
        emit_event("e3", {}, session_id="alice")
        emit_event("e4", {})  # session_id=None
        events = _drain(q_alice)
        assert [e["type"] for e in events] == ["e1", "e3"]
        assert all(e["session_id"] == "alice" for e in events)
        unsubscribe(q_alice)

    @pytest.mark.asyncio
    async def test_wildcard_subscriber_receives_everything(self):
        q_all = subscribe()
        emit_event("e1", {}, session_id="alice")
        emit_event("e2", {}, session_id="bob")
        emit_event("e3", {})  # session_id=None
        events = _drain(q_all)
        assert [e["type"] for e in events] == ["e1", "e2", "e3"]
        assert [e["session_id"] for e in events] == ["alice", "bob", None]
        unsubscribe(q_all)

    @pytest.mark.asyncio
    async def test_session_subscriber_does_not_receive_untagged(self):
        """An untagged event (session_id=None) must NOT leak to a session subscriber."""
        q_alice = subscribe(session_id="alice")
        emit_event("untagged", {})  # session_id will resolve to None
        assert q_alice.empty()
        unsubscribe(q_alice)

    @pytest.mark.asyncio
    async def test_multiple_session_subscribers_for_same_sid(self):
        """Two independent subscribers for the same session_id both receive."""
        q1 = subscribe(session_id="shared")
        q2 = subscribe(session_id="shared")
        emit_event("shared-evt", {}, session_id="shared")
        assert _drain(q1)[0]["type"] == "shared-evt"
        assert _drain(q2)[0]["type"] == "shared-evt"
        unsubscribe(q1)
        unsubscribe(q2)


# ─── multi-session isolation (the integration acceptance test) ───────────


class TestMultiSessionIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_sessions_do_not_cross_leak(self):
        """Many concurrent agent-style runs, each in its own ContextVar
        scope, must NEVER deliver events to another session's subscriber."""

        n_sessions = 8
        events_per_session = 25
        subscribers = {
            sid: subscribe(session_id=sid)
            for sid in (f"sess-{i}" for i in range(n_sessions))
        }
        q_wild = subscribe()  # observer

        async def run_session(sid: str) -> None:
            token = current_emitter_session_id.set(sid)
            try:
                for i in range(events_per_session):
                    # Interleave to maximise scheduler context-switches.
                    await asyncio.sleep(0)
                    emit_event(f"evt-{i}", {"who": sid, "i": i})
            finally:
                current_emitter_session_id.reset(token)

        await asyncio.gather(*[run_session(sid) for sid in subscribers])

        # 1. Each session subscriber received exactly its own events.
        for sid, q in subscribers.items():
            events = _drain(q)
            assert len(events) == events_per_session, (
                f"session {sid} got {len(events)} events, "
                f"expected {events_per_session}"
            )
            assert all(e["session_id"] == sid for e in events), (
                f"CROSS-SESSION LEAK detected for {sid}: "
                f"{[e['session_id'] for e in events if e['session_id'] != sid]}"
            )
            assert all(e["data"]["who"] == sid for e in events)

        # 2. Wildcard subscriber saw every event from every session.
        wild_events = _drain(q_wild)
        assert len(wild_events) == n_sessions * events_per_session
        sid_counts = {sid: 0 for sid in subscribers}
        for e in wild_events:
            sid_counts[e["session_id"]] += 1
        assert all(c == events_per_session for c in sid_counts.values())

        for q in subscribers.values():
            unsubscribe(q)
        unsubscribe(q_wild)

    @pytest.mark.asyncio
    async def test_event_count_matches_after_unsubscribe(self):
        """unsubscribe() actually stops delivery to that queue."""
        q = subscribe(session_id="A")
        emit_event("e1", {}, session_id="A")
        assert q.qsize() == 1
        unsubscribe(q)
        emit_event("e2", {}, session_id="A")
        # q is unsubscribed -- size must NOT increase.
        assert q.qsize() == 1


# ─── backward compatibility ──────────────────────────────────────────────


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_legacy_two_arg_emit_event_still_works(self):
        q = subscribe()  # legacy bare subscribe
        emit_event("legacy.type", {"foo": "bar"})  # legacy 2-arg emit
        events = _drain(q)
        assert len(events) == 1
        e = events[0]
        assert e["type"] == "legacy.type"
        assert e["data"] == {"foo": "bar"}
        assert "id" in e
        assert "timestamp" in e
        assert e["session_id"] is None
        unsubscribe(q)

    @pytest.mark.asyncio
    async def test_get_subscriber_count_tracks_session_subscribers(self):
        assert get_subscriber_count() == 0
        q1 = subscribe()
        q2 = subscribe(session_id="x")
        q3 = subscribe(session_id="y")
        assert get_subscriber_count() == 3
        unsubscribe(q2)
        assert get_subscriber_count() == 2
        unsubscribe(q1)
        unsubscribe(q3)
        assert get_subscriber_count() == 0
