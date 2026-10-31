"""Gemini Flash lookup-first stop rule in the assembled system prompt."""

from unittest.mock import MagicMock

import pytest

from code_puppy.agents import _builder
from code_puppy.agents._builder import _assemble_instructions, _is_gemini_flash

HEADING = "## Check The Lookup The Code Actually Makes"


def _agent(model_name: str) -> MagicMock:
    agent = MagicMock()
    agent.get_system_prompt.return_value = "Base system prompt."
    agent.get_model_name.return_value = model_name
    agent.get_available_tools.return_value = ["grep", "read_file", "shell"]
    return agent


@pytest.fixture(autouse=True)
def _no_user_rules(monkeypatch):
    """Keep the user's AGENTS.md out of the assembled prompt."""
    monkeypatch.setattr(_builder, "load_puppy_rules", lambda: "")


@pytest.mark.parametrize(
    "model_name",
    [
        "gemini-3-flash",
        "gemini-3.8-flash",
        "Gemini-2.5-Flash-Lite",
        "gemini-flash-latest",
    ],
)
def test_gemini_flash_gets_the_stop_rule_once(model_name):
    instructions = _assemble_instructions(_agent(model_name), model_name).instructions
    assert instructions.startswith("Base system prompt.")
    assert instructions.count(HEADING) == 1
    assert "not set where the code reads it" in instructions
    assert "Stop rule: once the exact lookup has come back empty" in instructions


@pytest.mark.parametrize(
    "model_name",
    [
        "gemini-3-pro",
        "gemini-4-argon",
        "claude-sonnet-4-5",
        "gpt-5.6",
        "flash-attn-model",
        "",
        None,
    ],
)
def test_other_models_are_unchanged(model_name):
    instructions = _assemble_instructions(
        _agent(model_name or ""), model_name
    ).instructions
    assert HEADING not in instructions
    assert "Stop rule" not in instructions


def test_detection_needs_both_words():
    assert _is_gemini_flash("models/gemini-3-flash-preview")
    assert not _is_gemini_flash("gemini-3-pro")
    assert not _is_gemini_flash("some-flash-model")
    assert not _is_gemini_flash(None)
