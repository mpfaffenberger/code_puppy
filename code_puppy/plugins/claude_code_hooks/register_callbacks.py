"""
Register callbacks for Claude Code hooks plugin.

Integrates the hook engine with code_puppy's callback system.
"""

import logging
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.hook_engine import EventData, HookEngine

from .config import load_hooks_config

_SUBAGENT_NAMES = frozenset(
    {
        "pack_leader",
        "bloodhound",
        "husky",
        "retriever",
        "shepherd",
        "terrier",
        "watchdog",
        "subagent",
        "sub_agent",
    }
)

logger = logging.getLogger(__name__)

_hook_engine: Optional[HookEngine] = None


def _initialize_engine() -> Optional[HookEngine]:
    config = load_hooks_config()

    if not config:
        logger.info("No hooks configuration found - Claude Code hooks disabled")
        return None

    try:
        engine = HookEngine(config, strict_validation=False)
        stats = engine.get_stats()
        logger.info(
            f"Hook engine ready - Total: {stats['total_hooks']}, "
            f"Enabled: {stats['enabled_hooks']}"
        )
        return engine
    except Exception as e:
        logger.error(f"Failed to initialize hook engine: {e}", exc_info=True)
        return None


_hook_engine = _initialize_engine()


async def on_pre_tool_call_hook(
    tool_name: str,
    tool_args: Dict[str, Any],
    context: Any = None,
) -> Optional[Dict[str, Any]]:
    """Pre-tool callback — executes hooks before tool runs. Can block."""
    if not _hook_engine:
        return None

    event_data = EventData(
        event_type="PreToolUse",
        tool_name=tool_name,
        tool_args=tool_args,
        context={"context": context} if context else {},
    )

    try:
        result = await _hook_engine.process_event("PreToolUse", event_data)

        if result.blocked:
            logger.debug(
                f"Tool '{tool_name}' blocked by hook: {result.blocking_reason}"
            )
            return {
                "blocked": True,
                "reason": result.blocking_reason,
                "error_message": result.blocking_reason,
            }
        return None
    except Exception as e:
        logger.error(f"Error in pre-tool hook: {e}", exc_info=True)
        return None


async def on_post_tool_call_hook(
    tool_name: str,
    tool_args: Dict[str, Any],
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    """Post-tool callback — executes hooks after tool completes (observation only)."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="PostToolUse",
        tool_name=tool_name,
        tool_args=tool_args,
        context={"result": result, "duration_ms": duration_ms, "context": context},
    )

    try:
        await _hook_engine.process_event("PostToolUse", event_data)
    except Exception as e:
        logger.error(f"Error in post-tool hook: {e}", exc_info=True)


register_callback("pre_tool_call", on_pre_tool_call_hook)
register_callback("post_tool_call", on_post_tool_call_hook)


async def on_startup_hook() -> None:
    """Startup callback — fires SessionStart hooks when code_puppy boots."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="SessionStart",
        tool_name="session",
        tool_args={},
    )

    try:
        await _hook_engine.process_event("SessionStart", event_data)
    except Exception as e:
        logger.error(f"Error in SessionStart hook: {e}", exc_info=True)


async def on_agent_run_end_hook(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """agent_run_end callback — fires Stop or SubagentStop hooks."""
    if not _hook_engine:
        return

    agent_lower = (agent_name or "").lower()
    is_subagent = any(name in agent_lower for name in _SUBAGENT_NAMES)
    event_type = "SubagentStop" if is_subagent else "Stop"

    event_data = EventData(
        event_type=event_type,
        tool_name=agent_name or "agent",
        tool_args={},
        context={
            "agent_name": agent_name,
            "model_name": model_name,
            "session_id": session_id,
            "success": success,
            "error": str(error) if error else None,
        },
    )

    try:
        await _hook_engine.process_event(event_type, event_data)
    except Exception as e:
        logger.error(f"Error in {event_type} hook: {e}", exc_info=True)


register_callback("startup", on_startup_hook)
register_callback("agent_run_end", on_agent_run_end_hook)

logger.info("Claude Code hooks plugin registered")
