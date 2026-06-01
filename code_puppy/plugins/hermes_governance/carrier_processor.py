"""History processor that keeps the carrier in sync with live budget state.

Attached to the pydantic-ai agent via the ``wrap_pydantic_agent`` hook. It runs
on *every* model call (including between tool calls within one turn), AFTER
compaction, mirroring the pattern in ``code_puppy/agents/_steer_processor.py``.

Each call it:
  1. loads state from the carrier the first time (restores counts on resume),
  2. writes the current live state back into a freshly-pinned carrier so it
     rides in the protected tail and survives the next compaction,
  3. mirrors the mutation into ``agent._message_history`` so it persists across
     the turn boundary and gets autosaved.

When disarmed it strips any carrier it finds, so toggling the plugin off leaves
clean history.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List

from . import budget, carrier
from .config import is_enabled

logger = logging.getLogger(__name__)


def make_carrier_processor(agent: Any) -> Callable[[List[Any]], List[Any]]:
    """Build a pydantic-ai history processor bound to ``agent``."""

    def carrier_processor(messages: List[Any]) -> List[Any]:
        try:
            if not is_enabled():
                # Plugin disarmed: ensure no stale carrier lingers in context.
                stripped = carrier._strip_carriers(list(messages))
                if hasattr(agent, "_message_history"):
                    agent._message_history = carrier._strip_carriers(
                        list(agent._message_history)
                    )
                return stripped

            # 1. First pass this process: hydrate live state from carrier.
            budget.load_from_carrier(messages)

            # 2. Re-pin an up-to-date carrier into the protected tail.
            state = budget.snapshot()
            new_messages = carrier.write_state(messages, state)

            # 3. Mirror into the durable history (autosave + turn boundary).
            if hasattr(agent, "_message_history"):
                agent._message_history = carrier.write_state(
                    agent._message_history, state
                )

            return new_messages
        except Exception:
            logger.debug("hermes_governance carrier_processor failed", exc_info=True)
            return messages

    return carrier_processor


def _ensure_escape_hatch_tool(pydantic_agent: Any) -> None:
    """Attach ``skill_manage`` directly to the pydantic agent.

    Why this is necessary: the budget gate blocks every non-exempt tool once the
    onboarding budget is spent, and the *only* way to unlock is a skill action
    (``skill_manage`` / ``activate_skill``). But ``register_tools`` merely places
    ``skill_manage`` into the global ``TOOL_REGISTRY`` — it does **not** advertise
    it to any agent's tool list (``register_tools_for_agent`` only attaches tools
    an agent explicitly requests, and no agent lists ``skill_manage``). Without
    this, an armed gate dead-ends: the escape tool the gate demands never reaches
    the model.

    So we self-attach it here, on the same hook that installs the carrier. This
    keeps the plugin self-sufficient on a stock code_puppy (no dependency on the
    newer ``register_agent_tools`` advertising hook). Idempotent: pydantic-ai
    raises if a tool name is registered twice, so we swallow that.
    """
    from .skill_manage import register_skill_manage

    try:
        register_skill_manage(pydantic_agent)
    except Exception:
        # Most likely "tool already registered" on an agent rebuild — fine.
        logger.debug(
            "hermes_governance: skill_manage already attached (or attach failed)",
            exc_info=True,
        )


def wrap_agent(agent: Any, pydantic_agent: Any, **_kwargs: Any) -> Any:
    """``wrap_pydantic_agent`` hook: attach the carrier processor + escape hatch.

    Returns the same pydantic agent (we don't replace it, just append a history
    processor and ensure the unlock tool is present). Fails open — never breaks
    agent construction.
    """
    try:
        processor = make_carrier_processor(agent)
        existing = list(getattr(pydantic_agent, "history_processors", []) or [])
        existing.append(processor)
        pydantic_agent.history_processors = existing
    except Exception:
        logger.debug("hermes_governance wrap_agent failed", exc_info=True)

    # Guarantee the budget gate always has a working escape hatch. Only when
    # enforcement is armed — a disarmed plugin must add nothing.
    if is_enabled():
        _ensure_escape_hatch_tool(pydantic_agent)

    return pydantic_agent
