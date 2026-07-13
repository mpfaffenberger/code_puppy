"""Tests for user-interaction responses during active WebSocket turns."""

import asyncio

import pytest

from code_puppy.api.ws.chat_turn_runner import handle_user_interaction_response
from code_puppy.messaging.bus import get_message_bus, reset_message_bus


@pytest.fixture(autouse=True)
def clean_bus():
    reset_message_bus()
    yield
    reset_message_bus()


async def _wait_for_prompt_id():
    bus = get_message_bus()
    for _ in range(100):
        message = bus.get_message_nowait()
        if message is not None:
            return message.prompt_id
        await asyncio.sleep(0.01)
    raise AssertionError("MessageBus request was not emitted")


@pytest.mark.asyncio
async def test_active_turn_handles_user_input_response():
    bus = get_message_bus()
    bus.mark_renderer_active()
    task = asyncio.create_task(bus.request_input("Name?"))
    prompt_id = await _wait_for_prompt_id()

    assert handle_user_interaction_response(
        {"type": "user_input_response", "prompt_id": prompt_id, "value": "Puppy"}
    )

    assert await asyncio.wait_for(task, timeout=1) == "Puppy"


@pytest.mark.asyncio
async def test_active_turn_handles_confirmation_response():
    bus = get_message_bus()
    bus.mark_renderer_active()
    task = asyncio.create_task(
        bus.request_confirmation("Proceed?", "Should we continue?", allow_feedback=True)
    )
    prompt_id = await _wait_for_prompt_id()

    assert handle_user_interaction_response(
        {
            "type": "confirmation_response",
            "prompt_id": prompt_id,
            "confirmed": True,
            "feedback": "looks good",
        }
    )

    assert await asyncio.wait_for(task, timeout=1) == (True, "looks good")


@pytest.mark.asyncio
async def test_active_turn_handles_selection_response():
    bus = get_message_bus()
    bus.mark_renderer_active()
    task = asyncio.create_task(bus.request_selection("Pick", ["A", "B"]))
    prompt_id = await _wait_for_prompt_id()

    assert handle_user_interaction_response(
        {
            "type": "selection_response",
            "prompt_id": prompt_id,
            "selected_index": 1,
            "selected_value": "B",
        }
    )

    assert await asyncio.wait_for(task, timeout=1) == (1, "B")


@pytest.mark.asyncio
async def test_active_turn_handles_ask_user_question_response():
    bus = get_message_bus()
    bus.mark_renderer_active()
    task = asyncio.create_task(
        bus.request_ask_user_question(
            [
                {
                    "header": "Pizza-Toppings",
                    "question": "Which toppings?",
                    "multi_select": True,
                    "input_mode": "select_or_text",
                    "options": [{"label": "Pepperoni", "description": "Classic"}],
                }
            ]
        )
    )
    prompt_id = await _wait_for_prompt_id()

    assert handle_user_interaction_response(
        {
            "type": "ask_user_question_response",
            "prompt_id": prompt_id,
            "answers": [
                {
                    "question_header": "Pizza-Toppings",
                    "selected_options": ["Pepperoni"],
                    "user_input": "extra cheese",
                }
            ],
            "cancelled": False,
        }
    )

    assert await asyncio.wait_for(task, timeout=1) == (
        [
            {
                "question_header": "Pizza-Toppings",
                "selected_options": ["Pepperoni"],
                "user_input": "extra cheese",
            }
        ],
        False,
    )


def test_non_interaction_message_returns_false():
    assert handle_user_interaction_response({"type": "message"}) is False
