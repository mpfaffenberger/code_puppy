"""Skill nudges — mirrors Hermes' ``SKILLS_GUIDANCE``.

The cadence counters live in the budget state dict (see :mod:`budget`), so they
ride in the conversation carrier and survive compaction / resume just like the
budget itself. This module only decides *what* reminder to surface and *when*.

The ``user_prompt_submit`` hook calls :func:`consume_nudge`; if a reminder is
due it is prepended to the prompt and the relevant counter is reset.
"""

from __future__ import annotations

import logging

from . import budget
from .config import get_nudge_interval, is_enabled

logger = logging.getLogger(__name__)

_SKILL_REMINDER = (
    "[SKILL REMINDER] You've made {n} tool calls since your last skill action. "
    "If you notice a reusable pattern, capture it with "
    'skill_manage(action="create", ...). If an existing skill is outdated, '
    'patch it immediately with skill_manage(action="patch", ...).'
)

_VERIFY_REMINDER = (
    "[POST-ACTING REMINDER] You've made several implementation changes. "
    "Before finishing: verify the result actually works, and consider saving "
    "the approach as a skill so it's reusable next time."
)


def consume_nudge() -> str | None:
    """Return a reminder string if one is due, else None.

    Resets the relevant counter so each reminder fires once per threshold
    crossing. Acting nudges take priority over generic ones.
    """
    if not is_enabled():
        return None

    interval = get_nudge_interval()
    calls, acting = budget.nudge_counts()

    if acting >= interval:
        budget.reset_nudge_counters()
        return _VERIFY_REMINDER
    # Generic reminder: gated on having done *some* acting, so analysis-only
    # work (reading to understand a system) is never nagged.
    if calls >= interval and acting > 0:
        budget.reset_nudge_counters()
        return _SKILL_REMINDER.format(n=calls)
    return None
