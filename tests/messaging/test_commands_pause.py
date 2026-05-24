"""Tests for routing PauseAgentCommand / ResumeAgentCommand / SteerAgentCommand
through MessageBus.provide_response() into the global PauseController."""

import pytest

from code_puppy.messaging.bus import get_message_bus, reset_message_bus
from code_puppy.messaging.commands import (
    PauseAgentCommand,
    ResumeAgentCommand,
    SteerAgentCommand,
)
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_message_bus()
    reset_pause_controller()
    yield
    reset_message_bus()
    reset_pause_controller()


def test_pause_command_pauses_controller():
    bus = get_message_bus()
    pc = get_pause_controller()
    assert pc.is_paused() is False

    bus.provide_response(PauseAgentCommand(reason="user hit a key"))

    assert pc.is_paused() is True


def test_resume_command_resumes_controller():
    bus = get_message_bus()
    pc = get_pause_controller()
    pc.pause()
    assert pc.is_paused() is True

    bus.provide_response(ResumeAgentCommand())

    assert pc.is_paused() is False


def test_steer_command_queues_text():
    bus = get_message_bus()
    pc = get_pause_controller()

    bus.provide_response(SteerAgentCommand(text="please use type hints"))
    bus.provide_response(SteerAgentCommand(text="and write more tests"))

    assert pc.has_pending_steer() is True
    # Default mode is "now".
    assert pc.drain_pending_steer_now() == [
        "please use type hints",
        "and write more tests",
    ]
    assert pc.has_pending_steer() is False


def test_steer_command_with_queue_mode_lands_in_queued_queue():
    bus = get_message_bus()
    pc = get_pause_controller()

    bus.provide_response(SteerAgentCommand(text="do later", mode="queue"))

    # MUST land in queued queue, not now queue.
    assert pc.has_pending_steer_queued() is True
    assert pc.has_pending_steer_now() is False
    assert pc.drain_pending_steer_queued() == ["do later"]


def test_steer_command_default_mode_is_now():
    bus = get_message_bus()
    pc = get_pause_controller()

    bus.provide_response(SteerAgentCommand(text="do now-ish"))

    assert pc.drain_pending_steer_now() == ["do now-ish"]
    assert pc.drain_pending_steer_queued() == []


def test_steer_command_routes_each_mode_independently():
    """Mixed bag: bus correctly demuxes by ``mode`` field."""
    bus = get_message_bus()
    pc = get_pause_controller()

    bus.provide_response(SteerAgentCommand(text="n1", mode="now"))
    bus.provide_response(SteerAgentCommand(text="q1", mode="queue"))
    bus.provide_response(SteerAgentCommand(text="n2", mode="now"))
    bus.provide_response(SteerAgentCommand(text="q2", mode="queue"))

    assert pc.drain_pending_steer_now() == ["n1", "n2"]
    assert pc.drain_pending_steer_queued() == ["q1", "q2"]


def test_steer_command_ignores_whitespace_text():
    bus = get_message_bus()
    pc = get_pause_controller()

    bus.provide_response(SteerAgentCommand(text="   "))

    assert pc.has_pending_steer() is False


def test_pause_resume_steer_do_not_enter_incoming_queue():
    """These commands are routed straight to the PauseController, not the
    generic agent incoming queue.
    """
    bus = get_message_bus()
    assert bus.incoming_qsize == 0

    bus.provide_response(PauseAgentCommand())
    bus.provide_response(ResumeAgentCommand())
    bus.provide_response(SteerAgentCommand(text="hello"))

    assert bus.incoming_qsize == 0
