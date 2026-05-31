"""Configuration for the hermes_governance plugin.

All settings persist via Code Puppy's standard config store
(``code_puppy.config.get_value`` / ``set_value``), so they survive restarts
and can be edited with ``/set <key>=<value>``.

Defaults are intentionally conservative — enforcement is OFF until armed.
"""

from __future__ import annotations

import logging

from code_puppy.config import get_value, set_value

logger = logging.getLogger(__name__)

# Config keys (stored in puppy.cfg [puppy] section)
KEY_ENABLED = "hermes_governance_enabled"
KEY_ONBOARDING = "hermes_governance_onboarding_budget"
KEY_MAX = "hermes_governance_max_budget"
KEY_NUDGE_INTERVAL = "hermes_governance_nudge_interval"
KEY_TASK_ENFORCE = "hermes_governance_task_enforcement"
KEY_REGEN_EACH_TURN = "hermes_governance_regenerate_each_turn"
KEY_TASK_FAIL_OPEN = "hermes_governance_task_enforcement_fail_open"

# Defaults (mirror Hermes: onboarding 5 -> unlock 90)
DEFAULT_ONBOARDING = 5
DEFAULT_MAX = 90
DEFAULT_NUDGE_INTERVAL = 6
DEFAULT_TASK_ENFORCE = False
# Per-turn regeneration ON by default: the budget is a per-turn allowance, not
# a monotonic lifetime cap that eventually locks the agent out for good.
DEFAULT_REGEN_EACH_TURN = True
# When the task system is unavailable, task enforcement fails OPEN by default
# (don't deadlock the agent on a missing optional subsystem). Set false to fail
# CLOSED (block when we can't verify a task) for a stricter posture.
DEFAULT_TASK_FAIL_OPEN = True


def _get_bool(key: str, default: bool) -> bool:
    raw = get_value(key)
    if raw is None or raw == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _get_int(key: str, default: int) -> int:
    raw = get_value(key)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid int for %s=%r, using default %d", key, raw, default)
        return default


def is_enabled() -> bool:
    """Whether enforcement is armed. OFF by default (opt-in)."""
    return _get_bool(KEY_ENABLED, False)


def set_enabled(value: bool) -> None:
    set_value(KEY_ENABLED, "true" if value else "false")


def get_onboarding_budget() -> int:
    return max(1, _get_int(KEY_ONBOARDING, DEFAULT_ONBOARDING))


def get_max_budget() -> int:
    return max(get_onboarding_budget(), _get_int(KEY_MAX, DEFAULT_MAX))


def get_nudge_interval() -> int:
    return max(1, _get_int(KEY_NUDGE_INTERVAL, DEFAULT_NUDGE_INTERVAL))


def is_task_enforcement_enabled() -> bool:
    return _get_bool(KEY_TASK_ENFORCE, DEFAULT_TASK_ENFORCE)


def is_regenerate_each_turn() -> bool:
    """Whether the spent counter refreshes each turn (per-turn vs lifetime cap)."""
    return _get_bool(KEY_REGEN_EACH_TURN, DEFAULT_REGEN_EACH_TURN)


def is_task_fail_open() -> bool:
    """Whether task enforcement allows tools when the task system is unavailable."""
    return _get_bool(KEY_TASK_FAIL_OPEN, DEFAULT_TASK_FAIL_OPEN)
