"""Wire up the hermes_governance plugin (v2 — state rides in the conversation).

Registers all hooks at module scope (per Code Puppy plugin convention). Every
hook fails gracefully and is a no-op while enforcement is disarmed.

Placement: there is **no** standalone slash command. Governance is controlled
entirely through config (every puppy.cfg key is exposed in ``/set``
tab-completion automatically):

    /set hermes_governance_enabled=true     # arm the gate + nudges
    /set hermes_governance_enabled=false    # disarm
    /set hermes_governance_onboarding_budget=5
    /set hermes_governance_max_budget=90

Skill consolidation runs automatically on ``session_end`` (Hermes-style
background curation), and on demand via the ``skill_manage`` tool.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback

from . import budget, carrier_processor, curator, enforcer, nudges
from .config import is_enabled

logger = logging.getLogger(__name__)


# --- Tool registration ----------------------------------------------------


def _register_tools() -> List[Dict[str, Any]]:
    from .skill_manage import register_skill_manage

    return [{"name": "skill_manage", "register_func": register_skill_manage}]


# --- Pre/post tool-call gate ----------------------------------------------


def _pre_tool_call(
    tool_name: str, tool_args: dict, context: Any = None
) -> Optional[Dict[str, Any]]:
    try:
        return enforcer.pre_tool_call(tool_name, tool_args, context)
    except Exception:
        logger.debug("hermes_governance pre_tool_call failed", exc_info=True)
        return None


async def _post_tool_call(
    tool_name: str,
    tool_args: dict,
    result: Any = None,
    duration_ms: float = 0.0,
    context: Any = None,
) -> None:
    try:
        enforcer.post_tool_call(tool_name, tool_args, result, duration_ms, context)
    except Exception:
        logger.debug("hermes_governance post_tool_call failed", exc_info=True)


# --- Carrier (state-in-conversation) --------------------------------------


def _wrap_pydantic_agent(agent, pydantic_agent, **kwargs):
    return carrier_processor.wrap_agent(agent, pydantic_agent, **kwargs)


# --- Per-session lifecycle ------------------------------------------------


def _agent_run_start(
    agent_name: str, model_name: str, session_id: Optional[str] = None, **kwargs
) -> None:
    # Forget live state so the next carrier pass reloads this session's counts.
    try:
        budget.reset()
    except Exception:
        logger.debug("hermes_governance session reset failed", exc_info=True)


async def _session_end() -> None:
    # Hermes-style background curation: archive stale agent-created skills.
    if not is_enabled():
        return
    try:
        counts = curator.apply_automatic_transitions()
        if counts.get("archived"):
            logger.info(
                "hermes_governance curator archived %d stale skill(s)",
                counts["archived"],
            )
    except Exception:
        logger.debug("hermes_governance curator failed", exc_info=True)


# --- Nudge injection ------------------------------------------------------


def _user_prompt_submit(prompt: str, session_id: Optional[str] = None) -> Optional[str]:
    try:
        reminder = nudges.consume_nudge()
    except Exception:
        logger.debug("hermes_governance nudge failed", exc_info=True)
        return None
    if not reminder:
        return None
    return f"<system-reminder>\n{reminder}\n</system-reminder>\n\n{prompt}"


# --- Registration (module scope) ------------------------------------------

register_callback("register_tools", _register_tools)
register_callback("pre_tool_call", _pre_tool_call)
register_callback("post_tool_call", _post_tool_call)
register_callback("wrap_pydantic_agent", _wrap_pydantic_agent)
register_callback("agent_run_start", _agent_run_start)
register_callback("session_end", _session_end)
register_callback("user_prompt_submit", _user_prompt_submit)

logger.debug("hermes_governance plugin registered (v2, enforcement opt-in)")
