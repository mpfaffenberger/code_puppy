"""Tests for the ``PauseController`` resume-listener pub-sub."""

from __future__ import annotations

import pytest

from code_puppy.messaging.pause_controller import (
    PauseController,
    reset_pause_controller,
)


@pytest.fixture
def controller() -> PauseController:
    return PauseController()


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


# =============================================================================
# Registration / removal
# =============================================================================


def test_resume_listener_fires_on_paused_to_not_paused_transition(controller):
    calls: list[int] = []

    def _listener() -> None:
        calls.append(1)

    controller.add_resume_listener(_listener)

    controller.pause()
    controller.resume()

    assert calls == [1]


def test_resume_listener_does_not_fire_when_not_paused(controller):
    """A no-op resume() (we were already not paused) must NOT call listeners."""
    calls: list[int] = []
    controller.add_resume_listener(lambda: calls.append(1))

    controller.resume()  # already not paused

    assert calls == []


def test_resume_listener_only_fires_once_per_pause_resume_cycle(controller):
    calls: list[int] = []
    controller.add_resume_listener(lambda: calls.append(1))

    controller.pause()
    controller.resume()
    controller.resume()  # no-op second call
    controller.resume()  # no-op third call

    assert calls == [1]


def test_resume_listener_fires_again_after_next_pause(controller):
    calls: list[int] = []
    controller.add_resume_listener(lambda: calls.append(1))

    controller.pause()
    controller.resume()
    controller.pause()
    controller.resume()

    assert calls == [1, 1]


# =============================================================================
# Removal
# =============================================================================


def test_remove_resume_listener_stops_callbacks(controller):
    calls: list[int] = []

    def _listener() -> None:
        calls.append(1)

    controller.add_resume_listener(_listener)
    controller.remove_resume_listener(_listener)

    controller.pause()
    controller.resume()

    assert calls == []


def test_remove_unknown_listener_is_noop(controller):
    # Must not raise.
    controller.remove_resume_listener(lambda: None)


def test_add_resume_listener_dedupes(controller):
    calls: list[int] = []

    def _listener() -> None:
        calls.append(1)

    controller.add_resume_listener(_listener)
    controller.add_resume_listener(_listener)  # duplicate ignored

    controller.pause()
    controller.resume()

    assert calls == [1]


# =============================================================================
# Multiple listeners, error isolation
# =============================================================================


def test_multiple_listeners_all_fire_in_order(controller):
    calls: list[str] = []
    controller.add_resume_listener(lambda: calls.append("a"))
    controller.add_resume_listener(lambda: calls.append("b"))
    controller.add_resume_listener(lambda: calls.append("c"))

    controller.pause()
    controller.resume()

    assert calls == ["a", "b", "c"]


def test_broken_listener_does_not_break_others(controller):
    calls: list[str] = []

    def _broken() -> None:
        raise RuntimeError("listener boom")

    controller.add_resume_listener(lambda: calls.append("before"))
    controller.add_resume_listener(_broken)
    controller.add_resume_listener(lambda: calls.append("after"))

    # resume() itself must NOT raise.
    controller.pause()
    controller.resume()

    assert calls == ["before", "after"]


def test_listener_can_unregister_itself_without_deadlock(controller):
    """Snapshot-on-iterate means a listener that mutates the registry
    (e.g., removing itself) doesn't crash or deadlock the resume path.
    """
    calls: list[int] = []

    def _self_unregister() -> None:
        controller.remove_resume_listener(_self_unregister)
        calls.append(1)

    controller.add_resume_listener(_self_unregister)

    controller.pause()
    controller.resume()
    controller.pause()
    controller.resume()

    # Fired exactly once; second cycle didn't re-trigger after self-removal.
    assert calls == [1]
