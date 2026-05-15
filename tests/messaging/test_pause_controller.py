"""Tests for code_puppy.messaging.pause_controller - PauseController + singleton."""

import asyncio
import time

import pytest

from code_puppy.messaging.pause_controller import (
    PauseController,
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture
def controller():
    return PauseController()


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


# =========================================================================
# Basic pause / resume / is_paused
# =========================================================================


def test_is_paused_defaults_false(controller):
    assert controller.is_paused() is False


def test_pause_sets_paused_true(controller):
    controller.pause()
    assert controller.is_paused() is True


def test_resume_flips_paused_back_to_false(controller):
    controller.pause()
    assert controller.is_paused() is True
    controller.resume()
    assert controller.is_paused() is False


def test_pause_and_resume_are_idempotent(controller):
    controller.pause()
    controller.pause()
    assert controller.is_paused() is True
    controller.resume()
    controller.resume()
    assert controller.is_paused() is False


# =========================================================================
# wait_if_paused
# =========================================================================


@pytest.mark.asyncio
async def test_wait_if_paused_returns_true_when_not_paused(controller):
    result = await controller.wait_if_paused()
    assert result is True


@pytest.mark.asyncio
async def test_wait_if_paused_blocks_until_resumed_from_other_thread(controller):
    controller.pause()
    loop = asyncio.get_running_loop()

    def _resume_after_delay():
        time.sleep(0.1)
        controller.resume()

    # Kick off a background thread that resumes us shortly.
    fut = loop.run_in_executor(None, _resume_after_delay)

    start = time.monotonic()
    result = await controller.wait_if_paused()
    elapsed = time.monotonic() - start

    await fut

    assert result is True
    assert controller.is_paused() is False
    # We should have actually waited a bit (but not forever).
    assert elapsed >= 0.05
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_wait_if_paused_times_out_and_force_resumes(controller):
    controller.pause()
    result = await controller.wait_if_paused(timeout=0.1)
    assert result is False
    # Timeout should have force-resumed the controller.
    assert controller.is_paused() is False


@pytest.mark.asyncio
async def test_wait_if_paused_resumes_normally_returns_true(controller):
    controller.pause()
    loop = asyncio.get_running_loop()

    async def _resume_soon():
        await asyncio.sleep(0.05)
        controller.resume()

    loop.create_task(_resume_soon())
    result = await controller.wait_if_paused(timeout=1.0)
    assert result is True


# =========================================================================
# Steering queue — backwards-compat surface (drain BOTH queues)
# =========================================================================


def test_request_steer_and_drain(controller):
    # Default mode is "now".
    controller.request_steer("hi")
    assert controller.has_pending_steer() is True
    drained = controller.drain_pending_steer()
    assert drained == ["hi"]
    # Second drain is empty.
    assert controller.drain_pending_steer() == []
    assert controller.has_pending_steer() is False


def test_request_steer_preserves_order(controller):
    controller.request_steer("one")
    controller.request_steer("two")
    controller.request_steer("three")
    assert controller.drain_pending_steer() == ["one", "two", "three"]


@pytest.mark.parametrize("bad", ["", "   ", "\n\t  ", None])
def test_request_steer_ignores_empty_or_whitespace(controller, bad):
    controller.request_steer(bad)  # type: ignore[arg-type]
    assert controller.has_pending_steer() is False
    assert controller.drain_pending_steer() == []


@pytest.mark.parametrize("mode", ["now", "queue"])
@pytest.mark.parametrize("bad", ["", "   ", "\n\t  ", None])
def test_request_steer_whitespace_check_applies_regardless_of_mode(
    controller, mode, bad
):
    controller.request_steer(bad, mode=mode)  # type: ignore[arg-type]
    assert controller.has_pending_steer() is False


def test_has_pending_steer_false_initially(controller):
    assert controller.has_pending_steer() is False


# =========================================================================
# Two-queue routing — now vs queue mode
# =========================================================================


def test_now_mode_lands_in_now_queue_only(controller):
    controller.request_steer("do it now", mode="now")
    assert controller.has_pending_steer_now() is True
    assert controller.has_pending_steer_queued() is False
    assert controller.drain_pending_steer_now() == ["do it now"]
    assert controller.drain_pending_steer_queued() == []


def test_queue_mode_lands_in_queued_queue_only(controller):
    controller.request_steer("do it after", mode="queue")
    assert controller.has_pending_steer_queued() is True
    assert controller.has_pending_steer_now() is False
    assert controller.drain_pending_steer_queued() == ["do it after"]
    assert controller.drain_pending_steer_now() == []


def test_drain_now_does_not_touch_queued(controller):
    """Isolation: history processor must not eat queue-mode steers."""
    controller.request_steer("now-one", mode="now")
    controller.request_steer("queue-one", mode="queue")
    assert controller.drain_pending_steer_now() == ["now-one"]
    # Queued queue is untouched.
    assert controller.drain_pending_steer_queued() == ["queue-one"]


def test_drain_queued_does_not_touch_now(controller):
    """Isolation: runtime loop must not eat now-mode steers."""
    controller.request_steer("now-one", mode="now")
    controller.request_steer("queue-one", mode="queue")
    assert controller.drain_pending_steer_queued() == ["queue-one"]
    assert controller.drain_pending_steer_now() == ["now-one"]


def test_drain_pending_steer_combines_both_queues_queued_first(controller):
    """Backwards-compat: the cancel-path uses drain_pending_steer() to wipe
    everything. Queued first matches the order the runtime would have
    processed them in.
    """
    controller.request_steer("now-one", mode="now")
    controller.request_steer("queue-one", mode="queue")
    controller.request_steer("now-two", mode="now")
    controller.request_steer("queue-two", mode="queue")
    drained = controller.drain_pending_steer()
    assert drained == ["queue-one", "queue-two", "now-one", "now-two"]
    # Both queues now empty.
    assert controller.has_pending_steer() is False


def test_has_pending_steer_true_when_only_queued(controller):
    controller.request_steer("q", mode="queue")
    assert controller.has_pending_steer() is True


def test_has_pending_steer_true_when_only_now(controller):
    controller.request_steer("n", mode="now")
    assert controller.has_pending_steer() is True


def test_default_mode_is_now(controller):
    """Backwards-compat: legacy callers passing only ``text`` get ``now``."""
    controller.request_steer("default mode")
    assert controller.drain_pending_steer_now() == ["default mode"]
    assert controller.drain_pending_steer_queued() == []


# =========================================================================
# Singleton
# =========================================================================


def test_get_pause_controller_returns_same_instance():
    a = get_pause_controller()
    b = get_pause_controller()
    assert a is b


def test_reset_pause_controller_gives_fresh_instance():
    a = get_pause_controller()
    reset_pause_controller()
    b = get_pause_controller()
    assert a is not b
