"""Model-related utilities shared across agents and tools.

This module centralizes logic for handling model-specific behaviors.
"""

from dataclasses import dataclass


@dataclass
class PreparedPrompt:
    """Result of preparing a prompt for a specific model.

    Attributes:
        instructions: The system instructions to use for the agent
        user_prompt: The user prompt
        is_claude_code: Whether this is a claude-code model
    """

    instructions: str
    user_prompt: str
    is_claude_code: bool


def is_claude_code_model(model_name: str) -> bool:
    """Check if a model is a claude-code model."""
    return model_name.startswith("claude-code")


def is_chatgpt_codex_model(model_name: str) -> bool:
    """Check if a model is a ChatGPT Codex model."""
    return model_name.startswith("chatgpt-")


def is_gemini_model(model_name: str) -> bool:
    """Check if a model is a Gemini model.

    Gemini models don't support SSE streaming through the proxy,
    so we disable streaming for these models.
    """
    if not model_name:
        return False
    lower_name = model_name.lower()
    return "gemini" in lower_name


def prepare_prompt_for_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> PreparedPrompt:
    """Prepare instructions and prompt for a specific model.

    No special model-specific handling - just pass through.
    """
    return PreparedPrompt(
        instructions=system_prompt,
        user_prompt=user_prompt,
        is_claude_code=is_claude_code_model(model_name),
    )


def get_default_extended_thinking(model_name: str) -> str:
    """Return the default extended_thinking mode for an Anthropic model.

    Opus 4-6 models default to ``"adaptive"`` thinking; all other
    Anthropic models default to ``"enabled"``.

    Args:
        model_name: The model name string (e.g. ``"claude-opus-4-6"``).

    Returns:
        ``"adaptive"`` for Opus 4-6 variants, ``"enabled"`` otherwise.
    """
    lower = model_name.lower()
    if (
        "opus-4-6" in lower
        or "4-6-opus" in lower
        or "opus-4-7" in lower
        or "4-7-opus" in lower
    ):
        return "adaptive"
    return "enabled"


def should_use_anthropic_thinking_summary(model_name: str) -> bool:
    """Return whether Anthropic adaptive thinking should request summary display.

    Anthropic's newer Opus 4.7 models require ``display: \"summarized\"`` alongside
    ``thinking={"type": "adaptive"}``.
    """
    lower = model_name.lower()
    return "opus-4-7" in lower or "4-7-opus" in lower
