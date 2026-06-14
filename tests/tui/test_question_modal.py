"""Tests for the Textual ask_user_question modal (split-panel picker).

Mirrors test_interactive_modals.py: the critical property is that every exit
path (submit, cancel button, Escape) produces a QuestionResponse so the agent's
awaited Future can never hang.
"""

import pytest

from code_puppy.messaging import (
    QuestionRequest,
    QuestionResponse,
    get_message_bus,
)
from code_puppy.tui.app import build_app
from code_puppy.tui.screens.question import QuestionModal


def _capture_responses(monkeypatch):
    captured = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "provide_response", lambda cmd: captured.append(cmd))
    return captured


def _single_request():
    return QuestionRequest(
        prompt_id="q1",
        questions=[
            {
                "question": "Which database?",
                "header": "Database",
                "multi_select": False,
                "options": [
                    {"label": "PostgreSQL", "description": "Relational"},
                    {"label": "MongoDB", "description": "Document store"},
                ],
            }
        ],
    )


def _multi_request():
    return QuestionRequest(
        prompt_id="q2",
        questions=[
            {
                "question": "Pick toppings",
                "header": "Toppings",
                "multi_select": True,
                "options": [
                    {"label": "Cheese", "description": ""},
                    {"label": "Bacon", "description": ""},
                    {"label": "Onion", "description": ""},
                ],
            }
        ],
    )


@pytest.mark.asyncio
async def test_question_request_opens_modal(monkeypatch):
    _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.handle_bus_message(_single_request())
        await pilot.pause(0.1)
        assert isinstance(app.screen, QuestionModal)


@pytest.mark.asyncio
async def test_escape_provides_cancelled_response(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_single_request())
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert len(captured) == 1
    resp = captured[0]
    assert isinstance(resp, QuestionResponse)
    assert resp.prompt_id == "q1"
    assert resp.cancelled is True
    assert resp.answers == []


@pytest.mark.asyncio
async def test_single_select_submit(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_single_request())
        await pilot.pause(0.1)
        # Highlight + activate the first option, then submit.
        modal = app.screen
        assert isinstance(modal, QuestionModal)
        modal._activate_option(0)
        modal.action_submit()
        await pilot.pause(0.1)
    assert len(captured) == 1
    resp = captured[0]
    assert isinstance(resp, QuestionResponse)
    assert resp.cancelled is False
    assert resp.answers[0]["question_header"] == "Database"
    assert resp.answers[0]["selected_options"] == ["PostgreSQL"]


@pytest.mark.asyncio
async def test_single_select_replaces_previous(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_single_request())
        await pilot.pause(0.1)
        modal = app.screen
        modal._activate_option(0)
        modal._activate_option(1)  # second pick wins for single-select
        modal.action_submit()
        await pilot.pause(0.1)
    assert captured[0].answers[0]["selected_options"] == ["MongoDB"]


@pytest.mark.asyncio
async def test_multi_select_toggles(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_multi_request())
        await pilot.pause(0.1)
        modal = app.screen
        modal._activate_option(0)  # Cheese on
        modal._activate_option(2)  # Onion on
        modal._activate_option(0)  # Cheese off again
        modal.action_submit()
        await pilot.pause(0.1)
    assert captured[0].answers[0]["selected_options"] == ["Onion"]


@pytest.mark.asyncio
async def test_other_text_entry(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_single_request())
        await pilot.pause(0.1)
        modal = app.screen
        other_idx = modal._other_index(0)
        assert other_idx == 2  # after the 2 real options
        # Simulate selecting Other + typing a custom value.
        from textual.widgets import Input

        modal._activate_option(other_idx)  # reveals + focuses the input
        await pilot.pause(0.1)
        other_input = modal.query_one("#other-input", Input)
        other_input.value = "SQLite"
        modal.on_input_submitted(Input.Submitted(other_input, "SQLite"))
        modal.action_submit()
        await pilot.pause(0.1)
    answer = captured[0].answers[0]
    assert answer["selected_options"] == ["Other"]
    assert answer["other_text"] == "SQLite"


@pytest.mark.asyncio
async def test_selected_marker_survives_markup(monkeypatch):
    """[x]/[ ] markers must render literally, not be eaten as Rich markup."""
    from rich.text import Text
    from textual.widgets import OptionList

    _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._show_request_modal(_multi_request())
        await pilot.pause(0.1)
        modal = app.screen
        modal._activate_option(0)  # select Cheese
        await pilot.pause(0.1)
        prompts = []
        for op in modal.query_one("#options", OptionList)._options:
            p = op.prompt
            prompts.append(p.plain if isinstance(p, Text) else str(p))
    assert prompts[0].startswith("[x] ")
    assert prompts[1].startswith("[ ] ")


@pytest.mark.asyncio
async def test_cancel_button(monkeypatch):
    captured = _capture_responses(monkeypatch)
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app._show_request_modal(_single_request())
        await pilot.pause(0.1)
        modal = app.screen
        modal.action_cancel()
        await pilot.pause(0.1)
    assert captured[0].cancelled is True
