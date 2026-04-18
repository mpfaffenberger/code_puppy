"""Model-related utilities shared across agents and tools.

This module is intentionally model-agnostic. Anything model-family-specific
(e.g. claude-code OAuth prompt handling) lives in its own plugin and hooks
into the ``prepare_model_prompt`` or ``get_model_system_prompt`` callbacks.

Plugins can register:

- ``prepare_model_prompt``: fully take over prompt prep for a model family.
- ``get_model_system_prompt``: augment/override the system prompt for a model.
"""

from dataclasses import dataclass


@dataclass
class PreparedPrompt:
    """Result of preparing a prompt for a specific model.

    Attributes:
        instructions: The system instructions to use for the agent
        user_prompt: The user prompt (possibly modified)
        is_claude_code: Whether this is a claude-code model (set by the
            claude_code_oauth plugin via the ``prepare_model_prompt`` hook).
    """

    instructions: str
    user_prompt: str
    is_claude_code: bool


def prepare_prompt_for_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> PreparedPrompt:
    """Prepare instructions and prompt for a specific model.

    Core fires two hooks to let plugins customize prompt prep:

    1. ``prepare_model_prompt`` — first winner with ``handled=True`` takes
       over entirely (used by the claude_code_oauth plugin).
    2. ``get_model_system_prompt`` — legacy per-model system-prompt hook;
       still fired for compatibility with plugins (e.g. agent_skills) that
       rely on it.

    If no plugin handles the model, we return the original system/user prompt
    unchanged.

    Args:
        model_name: The name of the model being used.
        system_prompt: The default system prompt from the agent.
        user_prompt: The user's prompt/message.
        prepend_system_to_user: Whether to prepend the system prompt to the
            user prompt (only meaningful for plugins that opt into it).

    Returns:
        PreparedPrompt ready for the model.
    """
    from code_puppy import callbacks

    # 1) Give the dedicated prepare_model_prompt hook first crack. First
    #    plugin to claim ``handled=True`` wins.
    for result in callbacks.on_prepare_model_prompt(
        model_name, system_prompt, user_prompt, prepend_system_to_user
    ):
        if result and isinstance(result, dict) and result.get("handled"):
            return PreparedPrompt(
                instructions=result.get("instructions", system_prompt),
                user_prompt=result.get("user_prompt", user_prompt),
                is_claude_code=bool(result.get("is_claude_code", False)),
            )

    # 2) Fall back to the legacy per-model system-prompt hook for plugins
    #    that still register there.
    for result in callbacks.on_get_model_system_prompt(
        model_name, system_prompt, user_prompt
    ):
        if result and isinstance(result, dict) and result.get("handled"):
            return PreparedPrompt(
                instructions=result.get("instructions", system_prompt),
                user_prompt=result.get("user_prompt", user_prompt),
                is_claude_code=bool(result.get("is_claude_code", False)),
            )

    # 3) No plugin handled it — return the caller's prompts unchanged.
    return PreparedPrompt(
        instructions=system_prompt,
        user_prompt=user_prompt,
        is_claude_code=False,
    )


def get_default_extended_thinking(model_name: str) -> str:
    """Return the default extended_thinking mode for an Anthropic model.

    Opus 4-6 and Opus 4-7 models default to ``"adaptive"`` thinking; all
    other Anthropic models default to ``"enabled"``.

    Args:
        model_name: The model name string (e.g. ``"claude-opus-4-7"``).

    Returns:
        ``"adaptive"`` for Opus 4-6/4-7 variants, ``"enabled"`` otherwise.
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
