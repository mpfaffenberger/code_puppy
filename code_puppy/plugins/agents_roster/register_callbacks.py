"""Inject the available specialist-agents roster into the dynamic prompt.

Why this exists
---------------
The default agent has ``list_agents`` / ``invoke_agent`` but no in-context view
of WHAT specialists exist. So when a task needs a capability the main agent
lacks (e.g. web/browser automation), it tends to confidently declare "I can't
do that" instead of delegating to the agent that can (``qa-kitten`` ships with
Playwright browser automation). The user then has to push repeatedly.

This plugin appends a short roster of available agents + their one-line
descriptions to the runtime system prompt, so the agent always knows its
delegation options. Paired with the "verify before claiming a limit" prompt
rule, it removes the "had to keep pushing" failure mode.

The roster is computed once and cached for the process (agents rarely change
mid-session); call ``invalidate_roster_cache()`` after an agent reload.
"""

from __future__ import annotations

from typing import Optional

from code_puppy.callbacks import register_callback

_MAX_DESC_LEN = 160
_cached_roster: Optional[str] = None


def invalidate_roster_cache() -> None:
    global _cached_roster
    _cached_roster = None


def _short(text: str) -> str:
    text = " ".join((text or "").split())
    return text[: _MAX_DESC_LEN - 1] + "…" if len(text) > _MAX_DESC_LEN else text


def _build_roster() -> str:
    from code_puppy.agents.agent_manager import (
        get_agent_descriptions,
        get_current_agent,
    )

    descriptions = get_agent_descriptions() or {}
    try:
        current = get_current_agent().name
    except Exception:
        current = None

    lines = []
    for name, desc in sorted(descriptions.items()):
        if name == current:
            continue  # don't list yourself as a delegation target
        lines.append(f"- {name}: {_short(desc)}")
    if not lines:
        return ""

    return (
        "## Specialist agents you can delegate to (via `invoke_agent`)\n"
        + "\n".join(lines)
        + "\nBefore telling the user a task is impossible, check this roster — a "
        "specialist may cover it (e.g. web/browser automation). Don't assert a "
        "capability limit you haven't verified; delegate when one fits."
    )


def _on_load_prompt() -> Optional[str]:
    global _cached_roster
    if _cached_roster is None:
        try:
            _cached_roster = _build_roster()
        except Exception:
            _cached_roster = ""
    return _cached_roster or None


register_callback("load_prompt", _on_load_prompt)
