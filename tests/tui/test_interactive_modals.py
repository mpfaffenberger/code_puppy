"""Phase 2d: interactive request modals always reply via the bus.

The critical property under test: every exit path (submit, button, select,
AND escape/cancel) produces a response command, so the agent's awaited Future
can never hang.
"""

import pytest

from code_puppy.messaging import (
    ConfirmationRequest,
    ConfirmationResponse,
    SelectionRequest,
    SelectionResponse,
    UserInputRequest,
    UserInputResponse,
    get_message_bus,
)
from code_puppy.tui.app import build_app
from code_puppy.tui.screens.interactive import (
    ConfirmModal,
    SelectionModal,
    TextInputModal,
)


def _capture_responses(monkeypatch):
    captured = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "provide_response", lambda cmd: captured.append(cmd))
    return captured


@pytest.mark.asyncio
async def test_handle_bus_message_opens_modal_for_request(monkeypatch):
    _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_bus_message(UserInputRequest(prompt_id="p1", prompt_text="Name?"))
        await pilot.pause(0.1)
        assert isinstance(app.screen, TextInputModal)


@pytest.mark.asyncio
async def test_user_input_submit_provides_value(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(UserInputRequest(prompt_id="p1", prompt_text="Name?"))
        await pilot.pause(0.1)
        await pilot.press(*"luc")
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert isinstance(captured[0], UserInputResponse)
    assert captured[0].prompt_id == "p1"
    assert captured[0].value == "luc"


@pytest.mark.asyncio
async def test_user_input_escape_still_responds(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(UserInputRequest(prompt_id="p1", prompt_text="Name?"))
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert isinstance(captured[0], UserInputResponse)


@pytest.mark.asyncio
async def test_confirm_first_option_confirms(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(
            ConfirmationRequest(prompt_id="c1", title="Sure?", description="do it")
        )
        await pilot.pause(0.1)
        assert isinstance(app.screen, ConfirmModal)
        await pilot.click("#opt-0")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert isinstance(captured[0], ConfirmationResponse)
    assert captured[0].confirmed is True


@pytest.mark.asyncio
async def test_confirm_escape_declines(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(
            ConfirmationRequest(prompt_id="c1", title="Sure?", description="do it")
        )
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert captured[0].confirmed is False


@pytest.mark.asyncio
async def test_selection_select_first(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(
            SelectionRequest(prompt_id="s1", prompt_text="Pick", options=["a", "b"])
        )
        await pilot.pause(0.1)
        assert isinstance(app.screen, SelectionModal)
        await pilot.press("enter")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert isinstance(captured[0], SelectionResponse)
    assert captured[0].selected_index == 0
    assert captured[0].selected_value == "a"


@pytest.mark.asyncio
async def test_selection_escape_cancels(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(
            SelectionRequest(prompt_id="s1", prompt_text="Pick", options=["a", "b"])
        )
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert len(captured) == 1
    assert captured[0].selected_index == -1
    assert captured[0].selected_value == ""
