"""Tests for the actionable output-budget exhaustion hint."""

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior

from code_puppy.agents._token_limit_hint import resolve_model_name, token_limit_hint

REAL_MESSAGE = (
    "Model token limit (30000) exceeded before any response was generated. "
    "Increase the `max_tokens` model setting, or simplify the prompt to result in a shorter response"
)


def test_hint_names_model_cap_and_the_menu_steps():
    hint = token_limit_hint(UnexpectedModelBehavior(REAL_MESSAGE), "claude-opus-5-5")
    assert "claude-opus-5-5" in hint
    assert "30000" in hint
    assert "/model_settings" in hint
    assert "Max Output Tokens" in hint


def test_provider_default_variant_is_handled():
    message = REAL_MESSAGE.replace("(30000)", "(provider default)")
    hint = token_limit_hint(UnexpectedModelBehavior(message), "m")
    assert "provider-default" in hint


def test_markup_in_the_cap_slot_is_never_echoed():
    message = REAL_MESSAGE.replace("(30000)", "([bold]x[/bold])")
    hint = token_limit_hint(UnexpectedModelBehavior(message), "m")
    assert "[bold]x" not in hint


def test_hint_without_a_model_name_is_generic():
    hint = token_limit_hint(UnexpectedModelBehavior(REAL_MESSAGE), None)
    assert hint.startswith("The model")


def test_finds_the_message_through_the_cause_chain():
    try:
        try:
            raise UnexpectedModelBehavior(REAL_MESSAGE)
        except UnexpectedModelBehavior as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert "30000" in token_limit_hint(outer, "m")


def test_finds_the_message_through_the_context_chain():
    try:
        try:
            raise UnexpectedModelBehavior(REAL_MESSAGE)
        except UnexpectedModelBehavior:
            raise RuntimeError("while handling")
    except RuntimeError as outer:
        assert "30000" in token_limit_hint(outer, "m")


@pytest.mark.parametrize(
    "message",
    [
        "Model token limit (30000) exceeded while generating a tool call",
        "Exceeded maximum output retries (3)",
        "something else entirely",
    ],
)
def test_other_errors_get_no_hint(message):
    assert token_limit_hint(UnexpectedModelBehavior(message), "m") is None


def test_model_name_markup_is_escaped():
    hint = token_limit_hint(UnexpectedModelBehavior(REAL_MESSAGE), "[red]evil[/red]")
    assert "\\[red]evil\\[/red]" in hint


def test_hostile_str_never_raises():
    class Hostile(Exception):
        def __str__(self):
            raise RuntimeError("no")

    assert token_limit_hint(Hostile(), "m") is None


def test_cyclic_chain_terminates():
    first, second = RuntimeError("a"), RuntimeError("b")
    first.__cause__, second.__cause__ = second, first
    assert token_limit_hint(first, "m") is None


def test_resolve_model_name_swallows_agent_failures():
    class Broken:
        def get_model_name(self):
            raise RuntimeError("boom")

    class Fine:
        def get_model_name(self):
            return "gpt-x"

    assert resolve_model_name(Broken()) is None
    assert resolve_model_name(Fine()) == "gpt-x"
