"""Model-related utilities shared across agents and tools.

This module centralizes logic for handling model-specific behaviors,
particularly for claude-code models which require special prompt handling.
"""

from dataclasses import dataclass

# The instruction override used for claude-code models
CLAUDE_CODE_INSTRUCTIONS = "You are Claude Code, Anthropic's official CLI for Claude."


@dataclass
class PreparedPrompt:
    """Result of preparing a prompt for a specific model.

    Attributes:
        instructions: The system instructions to use for the agent
        user_prompt: The user prompt (possibly modified)
        is_claude_code: Whether this is a claude-code model
    """

    instructions: str
    user_prompt: str
    is_claude_code: bool


def is_claude_code_model(model_name: str) -> bool:
    """Check if a model is a claude-code model.

    Args:
        model_name: The name of the model to check

    Returns:
        True if the model is a claude-code model, False otherwise
    """
    return model_name.startswith("claude-code")


def prepare_prompt_for_model(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    prepend_system_to_user: bool = True,
) -> PreparedPrompt:
    """Prepare instructions and prompt for a specific model.

    Claude-code models require special handling:
    - The system instructions are replaced with a fixed string
    - The original system prompt is prepended to the user's first message

    This function centralizes that logic so it's not duplicated across
    base_agent.py, agent_tools.py, shell_safety, summarization, etc.

    Args:
        model_name: The name of the model being used
        system_prompt: The original system prompt/instructions
        user_prompt: The user's prompt message
        prepend_system_to_user: If True and model is claude-code, prepend
            the system prompt to the user prompt. Set to False when you
            only need to swap the instructions (e.g., for agent creation
            where the prompt will be handled separately).

    Returns:
        PreparedPrompt with the (possibly modified) instructions and user_prompt

    Example:
        >>> result = prepare_prompt_for_model(
        ...     "claude-code-sonnet",
        ...     "You are a helpful coding assistant.",
        ...     "Write a hello world program"
        ... )
        >>> result.instructions
        "You are Claude Code, Anthropic's official CLI for Claude."
        >>> result.user_prompt
        "You are a helpful coding assistant.\n\nWrite a hello world program"
        >>> result.is_claude_code
        True
    """
    if is_claude_code_model(model_name):
        modified_prompt = user_prompt
        if prepend_system_to_user and system_prompt:
            modified_prompt = f"{system_prompt}\n\n{user_prompt}"

        return PreparedPrompt(
            instructions=CLAUDE_CODE_INSTRUCTIONS,
            user_prompt=modified_prompt,
            is_claude_code=True,
        )

    return PreparedPrompt(
        instructions=system_prompt,
        user_prompt=user_prompt,
        is_claude_code=False,
    )


def get_claude_code_instructions() -> str:
    """Get the standard claude-code instructions string.

    Returns:
        The fixed instruction string for claude-code models
    """
    return CLAUDE_CODE_INSTRUCTIONS
