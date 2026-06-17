"""Tests for the sync->bus bridge that powers ask_user_question in the TUI.

Covers:
* the bus ``ask_questions_blocking`` graceful fallback when no UI loop exists
* the handler routing to the bus in textual mode (mapping all three outcomes)
"""

import code_puppy.tools.ask_user_question.handler as handler_mod
from code_puppy.messaging import get_message_bus, reset_message_bus
from code_puppy.tools.ask_user_question.handler import ask_user_question

_QUESTIONS = [
    {
        "question": "Which database?",
        "header": "Database",
        "options": [
            {"label": "PostgreSQL"},
            {"label": "MongoDB"},
        ],
    }
]


def test_ask_questions_blocking_no_loop_returns_cancelled():
    """No registered UI loop -> cancelled, never a hang."""
    reset_message_bus()
    bus = get_message_bus()
    bus.set_event_loop(None)
    answers, cancelled, timed_out = bus.ask_questions_blocking(_QUESTIONS, 5)
    assert answers == []
    assert cancelled is True
    assert timed_out is False


def test_handler_routes_to_bus_in_textual_mode(monkeypatch):
    """In textual mode the handler bridges to the bus and maps answers back."""
    monkeypatch.setattr(handler_mod, "is_subagent", lambda: False)
    monkeypatch.setattr(handler_mod, "is_wiggum_active", lambda: False)
    monkeypatch.setattr("code_puppy.config._TUI_MODE", True)

    captured = {}

    def fake_blocking(serialized, timeout):
        captured["serialized"] = serialized
        captured["timeout"] = timeout
        return (
            [
                {
                    "question_header": "Database",
                    "selected_options": ["PostgreSQL"],
                    "other_text": None,
                }
            ],
            False,
            False,
        )

    monkeypatch.setattr(get_message_bus(), "ask_questions_blocking", fake_blocking)

    result = ask_user_question(_QUESTIONS, timeout=42)
    assert result.success
    assert result.get_selected("Database") == ["PostgreSQL"]
    assert captured["timeout"] == 42
    # Questions are serialized to plain dicts for transport.
    assert captured["serialized"][0]["header"] == "Database"


def test_handler_maps_cancelled(monkeypatch):
    monkeypatch.setattr(handler_mod, "is_subagent", lambda: False)
    monkeypatch.setattr(handler_mod, "is_wiggum_active", lambda: False)
    monkeypatch.setattr("code_puppy.config._TUI_MODE", True)
    monkeypatch.setattr(
        get_message_bus(),
        "ask_questions_blocking",
        lambda s, t: ([], True, False),
    )
    result = ask_user_question(_QUESTIONS)
    assert result.cancelled is True
    assert result.error is None


def test_handler_maps_timeout(monkeypatch):
    monkeypatch.setattr(handler_mod, "is_subagent", lambda: False)
    monkeypatch.setattr(handler_mod, "is_wiggum_active", lambda: False)
    monkeypatch.setattr("code_puppy.config._TUI_MODE", True)
    monkeypatch.setattr(
        get_message_bus(),
        "ask_questions_blocking",
        lambda s, t: ([], False, True),
    )
    result = ask_user_question(_QUESTIONS, timeout=7)
    assert result.timed_out is True
