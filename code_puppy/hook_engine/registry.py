"""
Registry management for hooks.

Builds and manages the HookRegistry from configuration dictionaries.
"""

import logging
from typing import Any, Dict, List, Optional

from .models import HookConfig, HookRegistry

logger = logging.getLogger(__name__)

# Supported event types
SUPPORTED_EVENT_TYPES = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "UserPromptSubmit",
    "Notification",
]


def build_registry_from_config(config: Dict[str, Any]) -> HookRegistry:
    """
    Build a HookRegistry from a configuration dictionary.

    Args:
        config: Hook configuration dictionary

    Returns:
        Populated HookRegistry
    """
    registry = HookRegistry()

    for event_type, hook_groups in config.items():
        if event_type.startswith("_"):
            continue  # skip comment keys

        if not isinstance(hook_groups, list):
            logger.warning(f"Hook groups for '{event_type}' must be a list, skipping")
            continue

        for group in hook_groups:
            if not isinstance(group, dict):
                continue

            matcher = group.get("matcher", "*")
            hooks_data = group.get("hooks", [])

            for hook_data in hooks_data:
                if not isinstance(hook_data, dict):
                    continue
                if hook_data.get("type") == "command" and not hook_data.get("command"):
                    continue

                try:
                    hook = HookConfig(
                        matcher=matcher,
                        type=hook_data.get("type", "command"),
                        command=hook_data.get("command", hook_data.get("prompt", "")),
                        timeout=hook_data.get("timeout", 5000),
                        once=hook_data.get("once", False),
                        enabled=hook_data.get("enabled", True),
                        id=hook_data.get("id"),
                    )
                    registry.add_hook(event_type, hook)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid hook in {event_type}: {e}")

    return registry


def get_registry_stats(registry: HookRegistry) -> Dict[str, Any]:
    """Get statistics about a registry."""
    stats: Dict[str, Any] = {
        "total_hooks": registry.count_hooks(),
        "enabled_hooks": 0,
        "disabled_hooks": 0,
        "by_event": {},
    }

    for attr in ['pre_tool_use', 'post_tool_use', 'session_start',
                 'session_end', 'pre_compact', 'user_prompt_submit', 'notification']:
        hooks = getattr(registry, attr)
        enabled = sum(1 for h in hooks if h.enabled)
        disabled = len(hooks) - enabled
        stats["enabled_hooks"] += enabled
        stats["disabled_hooks"] += disabled
        if hooks:
            event_name = attr.replace("_", " ").title().replace(" ", "")
            stats["by_event"][event_name] = {
                "total": len(hooks),
                "enabled": enabled,
                "disabled": disabled,
            }

    return stats
