"""
Configuration validation for hooks.

Validates hook configuration dictionaries and provides actionable error messages.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VALID_EVENT_TYPES = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "UserPromptSubmit",
    "Notification",
    "Stop",
    "SubagentStop",
]

VALID_HOOK_TYPES = ["command", "prompt"]


def validate_hooks_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a hooks configuration dictionary.

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors: List[str] = []

    if not isinstance(config, dict):
        return False, ["Configuration must be a dictionary"]

    for event_type, hook_groups in config.items():
        if event_type.startswith("_"):
            continue  # skip comment keys

        if event_type not in VALID_EVENT_TYPES:
            errors.append(
                f"Unknown event type '{event_type}'. "
                f"Valid types: {', '.join(VALID_EVENT_TYPES)}"
            )
            continue

        if not isinstance(hook_groups, list):
            errors.append(f"'{event_type}' must be a list of hook groups")
            continue

        for i, group in enumerate(hook_groups):
            if not isinstance(group, dict):
                errors.append(
                    f"'{event_type}[{i}]' must be a dict with 'matcher' and 'hooks'"
                )
                continue

            if "matcher" not in group:
                errors.append(f"'{event_type}[{i}]' missing required field 'matcher'")

            if "hooks" not in group:
                errors.append(f"'{event_type}[{i}]' missing required field 'hooks'")
                continue

            if not isinstance(group["hooks"], list):
                errors.append(f"'{event_type}[{i}].hooks' must be a list")
                continue

            for j, hook in enumerate(group["hooks"]):
                hook_errors = _validate_hook(event_type, i, j, hook)
                errors.extend(hook_errors)

    return len(errors) == 0, errors


def _validate_hook(
    event_type: str, group_idx: int, hook_idx: int, hook: Any
) -> List[str]:
    errors: List[str] = []
    prefix = f"'{event_type}[{group_idx}].hooks[{hook_idx}]'"

    if not isinstance(hook, dict):
        return [f"{prefix} must be a dict"]

    hook_type = hook.get("type")
    if not hook_type:
        errors.append(f"{prefix} missing required field 'type'")
    elif hook_type not in VALID_HOOK_TYPES:
        errors.append(
            f"{prefix} invalid type '{hook_type}'. Must be one of: {', '.join(VALID_HOOK_TYPES)}"
        )

    if hook_type == "command" and not hook.get("command"):
        errors.append(f"{prefix} missing required field 'command' for type 'command'")
    elif hook_type == "prompt" and not hook.get("prompt") and not hook.get("command"):
        errors.append(
            f"{prefix} missing required field 'prompt' (or 'command') for type 'prompt'"
        )

    timeout = hook.get("timeout")
    if timeout is not None:
        if not isinstance(timeout, (int, float)) or timeout < 100:
            errors.append(f"{prefix} 'timeout' must be >= 100ms, got: {timeout}")

    return errors


def format_validation_report(
    is_valid: bool, errors: List[str], suggestions: Optional[List[str]] = None
) -> str:
    lines = []
    if is_valid:
        lines.append("✓ Configuration is valid")
    else:
        lines.append(f"✗ Configuration has {len(errors)} error(s):")
        for error in errors:
            lines.append(f"  • {error}")

    if suggestions:
        lines.append("\nSuggestions:")
        for suggestion in suggestions:
            lines.append(f"  → {suggestion}")

    return "\n".join(lines)


def get_config_suggestions(config: Dict[str, Any], errors: List[str]) -> List[str]:
    suggestions: List[str] = []

    for error in errors:
        if "Unknown event type" in error:
            suggestions.append("Valid event types are: " + ", ".join(VALID_EVENT_TYPES))
            break

    if any("missing required field 'command'" in e for e in errors):
        suggestions.append(
            "Hook commands should be shell commands like: "
            "'bash .claude/hooks/my-hook.sh'"
        )

    return suggestions
