"""
Register callbacks for Claude Code hooks plugin.

Integrates the hook engine with code_puppy's callback system.
"""

import logging
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.hook_engine import HookEngine, EventData
from .config import load_hooks_config

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
            logger.debug(f"Tool '{tool_name}' blocked by hook: {result.blocking_reason}")
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

logger.info("Claude Code hooks plugin registered")
