"""
Register callbacks for Claude Code hooks plugin.

Integrates the hook engine with code_puppy's callback system.

Responsibilities:
    * Route code_puppy callback phases to the hook engine's event types.
    * Propagate hook ``stdout`` (exit code 0) back into the agent context for
      ``SessionStart``, ``UserPromptSubmit``, and ``PreToolUse`` events.
    * Honour block signals (exit code 1) from PreToolUse hooks.
    * Wire the Claude-Code-compatible event surface (``SessionEnd``,
      ``PreCompact``, ``UserPromptSubmit``, ``Notification``) that previously
      only existed in the schema.

Hooks that are observation-only (``PostToolUse``, ``Stop``, ``SubagentStop``,
``SessionEnd``, ``PreCompact``, ``Notification``) intentionally don't inject
stdout anywhere — there's no model context to put it in at that point.
"""

import logging
from typing import Any, Dict, List, Optional

from code_puppy.callbacks import register_callback
from code_puppy.hook_engine import EventData, HookEngine

from .config import load_hooks_config

_SUBAGENT_NAMES = frozenset(
    {
        "pack_leader",
        "bloodhound",
        "code-puppy",
        "code_puppy",
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

# Cache of stdout captured from ``SessionStart`` hooks. Drained into the system
# prompt via ``load_prompt`` on the first agent run, then cleared so repeat
# reloads don't double-inject. Lives at module scope because SessionStart fires
# once per process but system-prompt assembly happens per agent build.
_session_start_context: List[str] = []


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


def _collect_stdout(result) -> str:
    """Join successful-hook stdout into a single string (empty if none)."""
    parts: List[str] = []
    for execution in result.results:
        if execution.success and execution.stdout and execution.stdout.strip():
            parts.append(execution.stdout.strip())
    return "\n\n".join(parts)


async def on_pre_tool_call_hook(
    tool_name: str,
    tool_args: Dict[str, Any],
    context: Any = None,
) -> Optional[Dict[str, Any]]:
    """Pre-tool callback — executes hooks before tool runs. Can block OR inject."""
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

        stdout = _collect_stdout(result)
        if stdout:
            logger.debug(
                f"PreToolUse hook produced {len(stdout)} chars of context for '{tool_name}'"
            )
            return {"inject_context": stdout}
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


async def on_startup_hook() -> None:
    """Startup callback — fires SessionStart hooks and caches any stdout.

    Captured stdout is drained into the system prompt via :func:`load_prompt`
    on the next agent build, so a SessionStart hook can load a project
    constitution or style guide by simply printing it.
    """
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="SessionStart",
        tool_name="session",
        tool_args={},
    )

    try:
        result = await _hook_engine.process_event("SessionStart", event_data)
        stdout = _collect_stdout(result)
        if stdout:
            _session_start_context.append(stdout)
            logger.debug(
                f"SessionStart hooks contributed {len(stdout)} chars to system prompt"
            )
    except Exception as e:
        logger.error(f"Error in SessionStart hook: {e}", exc_info=True)


def load_prompt_additions() -> Optional[str]:
    """Return cached SessionStart stdout for injection into the system prompt."""
    if not _session_start_context:
        return None
    return "\n\n".join(_session_start_context)


async def on_user_prompt_submit_hook(
    prompt: str, **kwargs: Any
) -> Optional[Dict[str, Any]]:
    """UserPromptSubmit callback — may mutate the prompt via stdout or veto it."""
    if not _hook_engine:
        return None

    event_data = EventData(
        event_type="UserPromptSubmit",
        tool_name="user_prompt",
        tool_args={"prompt": prompt},
        context={k: v for k, v in kwargs.items() if v is not None},
    )

    try:
        result = await _hook_engine.process_event("UserPromptSubmit", event_data)

        if result.blocked:
            logger.debug(f"UserPromptSubmit blocked: {result.blocking_reason}")
            return {
                "blocked": True,
                "reason": result.blocking_reason,
            }

        stdout = _collect_stdout(result)
        if stdout:
            logger.debug(
                f"UserPromptSubmit hooks contributed {len(stdout)} chars of context"
            )
            return {"inject_context": stdout}
        return None
    except Exception as e:
        logger.error(f"Error in UserPromptSubmit hook: {e}", exc_info=True)
        return None


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


async def on_session_end_hook() -> None:
    """shutdown/session_end callback — fires SessionEnd hooks (observation)."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="SessionEnd",
        tool_name="session",
        tool_args={},
    )

    try:
        await _hook_engine.process_event("SessionEnd", event_data)
    except Exception as e:
        logger.error(f"Error in SessionEnd hook: {e}", exc_info=True)


def on_pre_compact_hook(
    agent_name: str,
    session_id: Optional[str],
    message_history: List[Any],
    incoming_messages: List[Any],
) -> None:
    """message_history_processor_start callback — fires PreCompact hooks.

    This callback is synchronous to match the ``message_history_processor_start``
    contract, so we kick the async hook dispatch onto the running loop as a
    fire-and-forget task. If there's no loop (shouldn't happen in practice),
    we just log and skip — never blocking compaction.
    """
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="PreCompact",
        tool_name="compaction",
        tool_args={
            "agent_name": agent_name,
            "session_id": session_id,
            "history_len": len(message_history),
            "incoming_len": len(incoming_messages),
        },
    )

    import asyncio

    async def _fire() -> None:
        try:
            await _hook_engine.process_event("PreCompact", event_data)
        except Exception as e:
            logger.error(f"Error in PreCompact hook: {e}", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_fire())
    except RuntimeError:
        logger.debug("PreCompact fired outside an event loop; skipping")


async def on_notification_hook(notification_type: str, payload: Any = None) -> None:
    """notification callback — fires Notification hooks (observation only)."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="Notification",
        tool_name="notification",
        tool_args={"type": notification_type, "payload": payload},
    )

    try:
        await _hook_engine.process_event("Notification", event_data)
    except Exception as e:
        logger.error(f"Error in Notification hook: {e}", exc_info=True)


# --- Registration ------------------------------------------------------------

register_callback("pre_tool_call", on_pre_tool_call_hook)
register_callback("post_tool_call", on_post_tool_call_hook)
register_callback("startup", on_startup_hook)
register_callback("load_prompt", load_prompt_additions)
register_callback("user_prompt_submit", on_user_prompt_submit_hook)
register_callback("agent_run_end", on_agent_run_end_hook)
register_callback("shutdown", on_session_end_hook)
register_callback("session_end", on_session_end_hook)
register_callback("message_history_processor_start", on_pre_compact_hook)
register_callback("notification", on_notification_hook)

logger.info("Claude Code hooks plugin registered")
