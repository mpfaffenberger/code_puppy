"""Prompt preparation logic for Claude Code OAuth models.

This module owns everything that's special about preparing prompts for
``claude-code-*`` models:

- The fixed system-instruction string Anthropic's Claude Code CLI expects.
- The ``is_claude_code_model`` predicate.
- A callback wired into the ``prepare_model_prompt`` hook which runs inside
  ``code_puppy.model_utils.prepare_prompt_for_model``.

Keeping this here (rather than in core ``model_utils``) keeps the core
model-agnostic and lets the claude-code behavior ship/fail as a single
plugin — exactly per the Contributing guide.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# The instruction override Anthropic's Claude Code CLI expects as the system
# prompt. When using OAuth-authenticated claude-code models, the *real* system
# prompt has to move into the user turn instead (see the callback below).
CLAUDE_CODE_INSTRUCTIONS = "You are Claude Code, Anthropic's official CLI for Claude."

# Prefix used by every claude-code-* model (as registered by this plugin).
_CLAUDE_CODE_PREFIX = "claude-code"


def is_claude_code_model(model_name: str) -> bool:
    """Return True if ``model_name`` is a claude-code OAuth model."""
    return model_name.startswith(_CLAUDE_CODE_PREFIX)


def get_claude_code_instructions() -> str:
    """Return the fixed Claude Code system instruction string."""
    return CLAUDE_CODE_INSTRUCTIONS


def prepare_claude_code_prompt(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> Optional[Dict[str, Any]]:
    """Callback for the ``prepare_model_prompt`` hook.

    For claude-code models, swap in the Anthropic-expected instruction string
    and (optionally) fold the caller's system prompt into the user message.

    Returns ``None`` for non-claude-code models so other handlers / the
    default passthrough can take over.
    """
    if not is_claude_code_model(model_name):
        return None

    modified_prompt = user_prompt
    if prepend_system_to_user and system_prompt:
        modified_prompt = f"{system_prompt}\n\n{user_prompt}"

    return {
        "handled": True,
        "instructions": CLAUDE_CODE_INSTRUCTIONS,
        "user_prompt": modified_prompt,
        "is_claude_code": True,
    }
