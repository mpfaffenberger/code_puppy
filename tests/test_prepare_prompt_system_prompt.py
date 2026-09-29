"""Tests for the ``system_prompt`` seam on ``PreparedPrompt``.

A ``prepare_model_prompt`` plugin may return a standing ``system_prompt``; it
must ride through ``prepare_prompt_for_model`` and land on pydantic-ai's
``Agent(system_prompt=...)`` as its own ``SystemPromptPart``, ahead of the
``instructions`` block.
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart
from pydantic_ai.models.test import TestModel

from code_puppy.callbacks import clear_callbacks, register_callback
from code_puppy.model_utils import PreparedPrompt, prepare_prompt_for_model

IDENTITY = "You are a very good dog."
REAL_PROMPT = "Fetch things. Do not eat the couch."


_PROMPT_HOOKS = ("prepare_model_prompt", "get_model_system_prompt")


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Both prompt hooks feed ``prepare_prompt_for_model``; isolate both."""
    for phase in _PROMPT_HOOKS:
        clear_callbacks(phase)
    yield
    for phase in _PROMPT_HOOKS:
        clear_callbacks(phase)


def _register_splitting_plugin():
    def plugin(model_name, system_prompt, user_prompt, prepend_system_to_user=True):
        if not model_name.startswith("splitty"):
            return None
        return {
            "handled": True,
            "system_prompt": IDENTITY,
            "instructions": system_prompt,
            "user_prompt": user_prompt,
        }

    register_callback("prepare_model_prompt", plugin)


def test_default_has_no_standing_system_prompt():
    prepared = prepare_prompt_for_model("plain-model", REAL_PROMPT, "hi")

    assert prepared.system_prompt == ""
    assert prepared.system_prompt_parts == ()
    assert prepared.system_text == REAL_PROMPT


def test_hook_system_prompt_flows_through():
    _register_splitting_plugin()

    prepared = prepare_prompt_for_model("splitty-9000", REAL_PROMPT, "hi")

    assert prepared.system_prompt == IDENTITY
    assert prepared.instructions == REAL_PROMPT
    assert prepared.user_prompt == "hi"
    assert prepared.system_prompt_parts == (IDENTITY,)
    assert prepared.system_text == f"{IDENTITY}\n\n{REAL_PROMPT}"


def test_system_prompt_parts_becomes_a_separate_system_prompt_part():
    """End-to-end through pydantic-ai: identity is its own SystemPromptPart,
    the real prompt rides on ``ModelRequest.instructions``."""
    from pydantic_ai import Agent

    prepared = PreparedPrompt(
        instructions=REAL_PROMPT,
        user_prompt="hi",
        is_claude_code=False,
        system_prompt=IDENTITY,
    )
    agent = Agent(
        TestModel(),
        system_prompt=prepared.system_prompt_parts,
        instructions=prepared.instructions,
    )

    result = agent.run_sync("hi")

    first = result.all_messages()[0]
    assert isinstance(first, ModelRequest)
    assert isinstance(first.parts[0], SystemPromptPart)
    assert first.parts[0].content == IDENTITY
    assert isinstance(first.parts[1], UserPromptPart)
    assert first.parts[1].content == "hi"
    assert first.instructions == REAL_PROMPT
