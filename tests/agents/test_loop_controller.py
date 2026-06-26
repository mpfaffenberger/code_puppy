import pytest

from code_puppy.agents._loop_controller import (
    LoopAction,
    LoopController,
    LoopState,
)


def test_loop_lifecycle_and_accounting():
    loop = LoopController(max_hook_retries=2)
    loop.start()
    loop.record_model_call()

    assert (
        loop.next_action(steer_available=True, hook_retry_requested=True)
        is LoopAction.STEER
    )
    loop.record_model_call()
    assert (
        loop.next_action(steer_available=False, hook_retry_requested=True)
        is LoopAction.HOOK_RETRY
    )
    loop.record_model_call()
    assert (
        loop.next_action(steer_available=False, hook_retry_requested=False)
        is LoopAction.STOP
    )
    assert loop.state is LoopState.COMPLETED
    assert loop.model_calls == 3
    assert loop.queued_steers == 1
    assert loop.hook_retries == 1


def test_steers_have_priority_over_hook_retries():
    loop = LoopController(max_hook_retries=1)
    loop.start()

    action = loop.next_action(steer_available=True, hook_retry_requested=True)

    assert action is LoopAction.STEER
    assert loop.hook_retries == 0


def test_budgets_stop_runaway_continuations():
    loop = LoopController(max_hook_retries=1, max_queued_steers=1)
    loop.start()
    assert (
        loop.next_action(steer_available=True, hook_retry_requested=False)
        is LoopAction.STEER
    )
    assert (
        loop.next_action(steer_available=True, hook_retry_requested=True)
        is LoopAction.HOOK_RETRY
    )
    assert (
        loop.next_action(steer_available=True, hook_retry_requested=True)
        is LoopAction.STOP
    )


def test_invalid_transition_is_rejected():
    loop = LoopController(max_hook_retries=1)
    with pytest.raises(RuntimeError):
        loop.transition(LoopState.COMPLETED)


def test_fail_and_cancel_are_terminal():
    failed = LoopController(max_hook_retries=1)
    failed.start()
    failed.fail()
    assert failed.state is LoopState.FAILED

    cancelled = LoopController(max_hook_retries=1)
    cancelled.cancel()
    assert cancelled.state is LoopState.CANCELLED
