"""Lock in the structural rules of Mist's default system prompt.

These tests don't aim to copy-edit the prompt — they ensure the budget stays
under the 12k ceiling and that the bare-filename rule (the fix for the
"read IN_PLACE_STATUS_PLAN.md" failure) stays in place. If a future edit
removes or rephrases the rule so these tests can't match, the author should
either update the rule or update the test — but not silently let the prompt
grow without bound.
"""

from __future__ import annotations

import re

import pytest

from code_puppy.agents.agent_code_puppy import MistAgent


# 12k chars is the soft ceiling the user asked us to stay under. We assert a
# generous headroom (10k) so accidental prompt bloat fails CI loudly instead
# of silently approaching the limit.
_PROMPT_CHAR_CEILING = 10_000


@pytest.fixture
def prompt() -> str:
    return MistAgent().get_system_prompt()


def test_prompt_stays_under_ceiling(prompt: str):
    assert len(prompt) < _PROMPT_CHAR_CEILING, (
        f"System prompt is {len(prompt)} chars; ceiling is {_PROMPT_CHAR_CEILING}."
    )


def test_prompt_contains_bare_filename_rule(prompt: str):
    """The rule added after the IN_PLACE_STATUS_PLAN.md failure must remain."""
    assert "Resolving file references" in prompt
    assert "without a path" in prompt
    assert "list_files" in prompt
    assert "grep" in prompt
    # The trap we're guarding against: using grep to find files by name.
    assert "don't use `grep` to find a file by name" in prompt or re.search(
        r"don't use `grep`.*find.*file", prompt, re.IGNORECASE
    )


def test_prompt_still_preserves_core_identity(prompt: str):
    """Sanity: the bare-filename addition shouldn't crowd out identity lines."""
    assert "I am Mist" in prompt
    assert "Rahul Bajaj" in prompt
    assert "DRY" in prompt or "YAGNI" in prompt
