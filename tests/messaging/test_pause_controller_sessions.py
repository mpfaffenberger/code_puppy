"""Per-session PauseController isolation keyed by the conversation root id."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

import pytest

from code_puppy.agents._run_signals import (
    drain_pause_state_on_cancel,
    reset_pause_state_at_run_start,
)
from code_puppy.messaging import (
    drop_session_pause_controller,
    get_pause_controller,
    get_session_pause_controller,
    reset_pause_controller,
)
from code_puppy.tools.subagent_context import (
    reset_conversation_root_id,
    set_conversation_root_id,
)


@pytest.fixture(autouse=True)
def _fresh_pause_state():
    reset_pause_controller()
    yield
    reset_pause_controller()


@contextmanager
def session_scope(root_id: str):
    token = set_conversation_root_id(root_id)
    try:
        yield
    finally:
        reset_conversation_root_id(token)


def test_terminal_without_root_id_uses_process_wide_controller():
    first = get_pause_controller()
    assert get_pause_controller() is first
    assert first is not get_session_pause_controller("any-session")


def test_root_id_selects_one_controller_per_session():
    with session_scope("session-a"):
        controller_a = get_pause_controller()
    with session_scope("session-b"):
        controller_b = get_pause_controller()
    with session_scope("session-a"):
        again_a = get_pause_controller()

    assert controller_a is get_session_pause_controller("session-a")
    assert controller_b is get_session_pause_controller("session-b")
    assert controller_a is not controller_b
    assert again_a is controller_a


async def _session_turn(root_id: str, observed: dict) -> None:
    with session_scope(root_id):
        controller = get_pause_controller()
        controller.request_steer(f"{root_id}-now", mode="now")
        controller.request_steer(f"{root_id}-queued", mode="queue")
        controller.pause()
        for _ in range(3):
            await asyncio.sleep(0)
        observed[root_id] = {
            "now": controller.drain_pending_steer_now(),
            "queued": controller.drain_pending_steer_queued(),
            "paused": controller.is_paused(),
        }
        controller.resume()


@pytest.mark.asyncio
async def test_concurrent_sessions_see_only_their_own_steers_and_pause_state():
    observed: dict = {}
    await asyncio.gather(
        _session_turn("A", observed),
        _session_turn("B", observed),
    )

    assert observed["A"]["now"] == ["A-now"]
    assert observed["A"]["queued"] == ["A-queued"]
    assert observed["B"]["now"] == ["B-now"]
    assert observed["B"]["queued"] == ["B-queued"]
    assert observed["A"]["paused"] is True
    assert observed["B"]["paused"] is True


@pytest.mark.asyncio
async def test_pause_in_one_session_does_not_pause_another():
    seen_by_b: dict = {}

    async def session_a() -> None:
        with session_scope("A"):
            get_pause_controller().pause()
            await asyncio.sleep(0)

    async def session_b() -> None:
        with session_scope("B"):
            await asyncio.sleep(0)
            seen_by_b["paused"] = get_pause_controller().is_paused()

    await asyncio.gather(session_a(), session_b())

    assert seen_by_b["paused"] is False
    assert get_session_pause_controller("A").is_paused() is True


def test_drop_session_controller_discards_its_state():
    with session_scope("session-a"):
        old = get_pause_controller()
        old.request_steer("pending", mode="now")

    drop_session_pause_controller("session-a")

    fresh = get_session_pause_controller("session-a")
    assert fresh is not old
    assert fresh.pending_steer_counts() == (0, 0)


def test_drop_unknown_session_is_noop():
    drop_session_pause_controller("never-created")
    drop_session_pause_controller("never-created")


@pytest.mark.asyncio
@pytest.mark.parametrize("spawn", ["create_task", "to_thread"])
async def test_spawned_work_inherits_session_controller(spawn: str):
    with session_scope("session-a"):
        parent = get_pause_controller()
        if spawn == "create_task":
            child = await asyncio.create_task(_return_controller())
        else:
            child = await asyncio.to_thread(get_pause_controller)

    assert child is parent


async def _return_controller():
    return get_pause_controller()


@pytest.mark.asyncio
async def test_cancel_drain_only_touches_current_session():
    with session_scope("A"):
        get_pause_controller().request_steer("A-pending", mode="now")
    with session_scope("B"):
        get_pause_controller().request_steer("B-pending", mode="now")

    with session_scope("A"):
        drain_pause_state_on_cancel()

    assert get_session_pause_controller("A").pending_steer_counts() == (0, 0)
    assert get_session_pause_controller("B").peek_pending_steer_queued() == []
    assert get_session_pause_controller("B").pending_steer_counts() == (1, 0)


@pytest.mark.asyncio
async def test_run_start_reset_only_defers_current_session_steers():
    with session_scope("A"):
        get_pause_controller().request_steer("A-now", mode="now")
    with session_scope("B"):
        get_pause_controller().request_steer("B-now", mode="now")

    with session_scope("A"):
        reset_pause_state_at_run_start()

    assert get_session_pause_controller("A").pending_steer_counts() == (0, 1)
    assert get_session_pause_controller("A").peek_pending_steer_queued() == ["A-now"]
    assert get_session_pause_controller("B").pending_steer_counts() == (1, 0)
