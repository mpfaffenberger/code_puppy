"""Callback registration for shell command safety checking.

This module registers a callback that intercepts shell commands in yolo_mode
and assesses their safety risk before execution.
"""

from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import (
    get_global_model_name,
    get_safety_permission_level,
    get_yolo_mode,
)
from code_puppy.messaging import emit_info
from code_puppy.plugins.shell_safety.command_cache import (
    cache_assessment,
    get_cached_assessment,
)
from code_puppy.tools.command_runner import ShellSafetyAssessment

# OAuth model prefixes - these models have their own safety mechanisms
OAUTH_MODEL_PREFIXES = (
    "claude-code-",  # Anthropic OAuth
    "chatgpt-",  # OpenAI OAuth
    "gemini-oauth",  # Google OAuth
)


def is_oauth_model(model_name: str | None) -> bool:
    """Check if the model is an OAuth model that should skip safety checks.

    OAuth models have their own built-in safety mechanisms, so we skip
    the shell safety callback to avoid redundant checks and potential bugs.

    Args:
        model_name: The name of the current model

    Returns:
        True if the model is an OAuth model, False otherwise
    """
    if not model_name:
        return False
    return model_name.startswith(OAUTH_MODEL_PREFIXES)


# Risk level hierarchy for numeric comparison
# Lower numbers = safer commands, higher numbers = more dangerous
# This mapping allows us to compare risk levels as integers
RISK_LEVELS: Dict[str, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def compare_risk_levels(assessed_risk: Optional[str], threshold: str) -> bool:
    """Compare assessed risk against threshold.

    Args:
        assessed_risk: The risk level from the agent (can be None)
        threshold: The configured risk threshold

    Returns:
        True if the command should be blocked (risk exceeds threshold)
        False if the command is acceptable
    """
    # If assessment failed (None), treat as high risk (fail-safe behavior)
    if assessed_risk is None:
        assessed_risk = "high"

    # Convert risk levels to numeric values for comparison
    assessed_level = RISK_LEVELS.get(assessed_risk, 4)  # Default to critical if unknown
    threshold_level = RISK_LEVELS.get(threshold, 2)  # Default to medium if unknown

    # Block if assessed risk is GREATER than threshold
    # Note: Commands AT the threshold level are allowed (>, not >=)
    return assessed_level > threshold_level


async def shell_safety_callback(
    context: Any, command: str, cwd: Optional[str] = None, timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """Callback to assess shell command safety before execution.

    This callback is only active when yolo_mode is True. When yolo_mode is False,
    the user manually reviews every command, so we don't need the agent.

    Args:
        context: The execution context
        command: The shell command to execute
        cwd: Optional working directory
        timeout: Command timeout (unused here)

    Returns:
        None if command is safe to proceed
        Dict with rejection info if command should be blocked
    """
    # Skip safety checks for OAuth models - they have their own safety mechanisms
    current_model = get_global_model_name()
    if is_oauth_model(current_model):
        return None

    # Only check safety in yolo_mode - otherwise user is reviewing manually
    yolo_mode = get_yolo_mode()
    if not yolo_mode:
        return None

    # Get configured risk threshold
    threshold = get_safety_permission_level()

    try:
        # Check cache first (fast path - no LLM call)
        cached = get_cached_assessment(command, cwd)

        if cached:
            # Got a cached result - check against threshold
            if compare_risk_levels(cached.risk, threshold):
                # Cached result says it's too risky
                risk_display = cached.risk or "unknown"
                concise_reason = cached.reasoning or "No reasoning provided"
                error_msg = (
                    f"🛑 Command blocked (risk {risk_display.upper()} > permission {threshold.upper()}).\n"
                    f"Reason: {concise_reason}\n"
                    f"Override: /set yolo_mode true or /set safety_permission_level {risk_display}"
                )
                emit_info(error_msg)
                return {
                    "blocked": True,
                    "risk": cached.risk,
                    "reasoning": cached.reasoning,
                    "error_message": error_msg,
                }
            # Cached result is within threshold - allow silently
            return None

        # Cache miss - need LLM assessment
        # Import here to avoid circular imports
        from code_puppy.plugins.shell_safety.agent_shell_safety import ShellSafetyAgent

        # Create agent and assess command
        agent = ShellSafetyAgent()

        # Build the assessment prompt with optional cwd context
        prompt = f"Assess this shell command:\n\nCommand: {command}"
        if cwd:
            prompt += f"\nWorking directory: {cwd}"

        # Run async assessment with structured output type
        result = await agent.run_with_mcp(prompt, output_type=ShellSafetyAssessment)
        assessment = result.output

        # Cache the result for future use, but only if it's not a fallback assessment
        if not getattr(assessment, "is_fallback", False):
            cache_assessment(command, cwd, assessment.risk, assessment.reasoning)

        # Check if risk exceeds threshold (commands at threshold are allowed)
        if compare_risk_levels(assessment.risk, threshold):
            risk_display = assessment.risk or "unknown"
            concise_reason = assessment.reasoning or "No reasoning provided"
            error_msg = (
                f"🛑 Command blocked (risk {risk_display.upper()} > permission {threshold.upper()}).\n"
                f"Reason: {concise_reason}\n"
                f"Override: /set yolo_mode true or /set safety_permission_level {risk_display}"
            )
            emit_info(error_msg)

            # Return rejection info for the command runner
            return {
                "blocked": True,
                "risk": assessment.risk,
                "reasoning": assessment.reasoning,
                "error_message": error_msg,
            }

        # Command is within acceptable risk threshold - remain silent
        return None  # Allow command to proceed

    except Exception as e:
        # On any error, fail safe by blocking the command
        error_msg = (
            f"🛑 Command blocked (risk HIGH > permission {threshold.upper()}).\n"
            f"Reason: Safety assessment error: {str(e)}\n"
            f"Override: /set yolo_mode true or /set safety_permission_level high"
        )
        return {
            "blocked": True,
            "risk": "high",
            "reasoning": f"Safety assessment error: {str(e)}",
            "error_message": error_msg,
        }


def register():
    """Register the shell safety callback."""
    register_callback("run_shell_command", shell_safety_callback)


# Auto-register the callback when this module is imported
register()
