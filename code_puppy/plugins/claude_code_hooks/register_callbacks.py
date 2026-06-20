"""
Register callbacks for Claude Code hooks plugin.

Integrates the hook engine with Mist's callback system.

This bridge maps Claude Code hook events to Mist lifecycle callbacks:

    Claude Code event   →  Mist callback
    -----------------   →  -------------------
    PreToolUse          →  pre_tool_call
    PostToolUse         →  post_tool_call
    SessionStart        →  startup
    SessionEnd          →  session_end
    UserPromptSubmit    →  user_prompt_submit
    PreCompact          →  pre_compact
    Notification        →  notification
    Stop / SubagentStop →  agent_run_end

Hook stdout on exit code 0 is propagated to the agent context for the events
where Claude Code's spec says it should become "additional context"
(SessionStart, UserPromptSubmit, PreToolUse). See issue #298.
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
        "mist",
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

# Deferred-context buffer: SessionStart hook stdout is collected here at boot
# and injected into the very next user prompt (which is where Claude Code's
# spec says SessionStart "additional context" should land — the assistant's
# first turn). Cleared on first inject so it's a one-shot per session.
_pending_session_context: List[str] = []


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


def _collect_context_stdout(result: Any) -> List[str]:
    """Pull stdout from non-blocking, exit-0 hook results.

    Per Claude Code spec, only exit code 0 hooks contribute "additional
    context" — exit 1 blocks and exit 2 routes stderr back as a tool error.
    """
    chunks: List[str] = []
    for r in getattr(result, "results", []) or []:
        if getattr(r, "blocked", False):
            continue
        if getattr(r, "exit_code", 0) != 0:
            continue
        stdout = (getattr(r, "stdout", "") or "").strip()
        if stdout:
            chunks.append(stdout)
    return chunks


# ---------------------------------------------------------------------------
# PreToolUse / PostToolUse
# ---------------------------------------------------------------------------


async def on_pre_tool_call_hook(
    tool_name: str,
    tool_args: Dict[str, Any],
    context: Any = None,
) -> Optional[Dict[str, Any]]:
    """Pre-tool callback — executes hooks before tool runs. Can block AND
    inject stdout as additional context for the model."""
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

        # Exit code 0 hooks: propagate their stdout to the model context.
        # See issue #298. The pydantic_patches consumer reads
        # ``context_message`` and prepends it to the tool result.
        stdout_chunks = _collect_context_stdout(result)
        if stdout_chunks:
            return {"context_message": "\n\n".join(stdout_chunks)}
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
    """Post-tool callback — executes hooks after tool completes."""
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


# ---------------------------------------------------------------------------
# SessionStart  /  SessionEnd
# ---------------------------------------------------------------------------


async def on_startup_hook() -> None:
    """Startup callback — fires SessionStart hooks when Mist boots.

    Captures stdout into ``_pending_session_context`` so the first user prompt
    can be augmented with the SessionStart "additional context" (project
    constitutions, etc.). See issue #298.
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
        stdout_chunks = _collect_context_stdout(result)
        if stdout_chunks:
            _pending_session_context.extend(stdout_chunks)
            logger.debug(
                f"SessionStart captured {len(stdout_chunks)} stdout chunk(s) "
                f"for injection on next user prompt"
            )
    except Exception as e:
        logger.error(f"Error in SessionStart hook: {e}", exc_info=True)


async def on_session_end_hook() -> None:
    """Session-end callback — fires SessionEnd hooks (issue #298)."""
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


register_callback("startup", on_startup_hook)
register_callback("session_end", on_session_end_hook)


# ---------------------------------------------------------------------------
# UserPromptSubmit
# ---------------------------------------------------------------------------


async def on_user_prompt_submit_hook(
    prompt: str, session_id: Optional[str] = None
) -> Optional[str]:
    """Fire UserPromptSubmit hooks and inject their stdout (+ any pending
    SessionStart stdout) into the user prompt.

    Returns the (possibly augmented) prompt, or ``None`` if there's nothing
    to add. See issue #298.
    """
    chunks: List[str] = []

    # Drain any pending SessionStart context first.
    if _pending_session_context:
        chunks.extend(_pending_session_context)
        _pending_session_context.clear()

    if _hook_engine:
        event_data = EventData(
            event_type="UserPromptSubmit",
            tool_name="user_prompt",
            tool_args={"prompt": prompt},
            context={"session_id": session_id} if session_id else {},
        )

        try:
            result = await _hook_engine.process_event("UserPromptSubmit", event_data)
            chunks.extend(_collect_context_stdout(result))
        except Exception as e:
            logger.error(f"Error in UserPromptSubmit hook: {e}", exc_info=True)

    if not chunks:
        return None

    header = "\n\n".join(f"[hook context]\n{c}" for c in chunks)
    return f"{header}\n\n{prompt}"


register_callback("user_prompt_submit", on_user_prompt_submit_hook)


# ---------------------------------------------------------------------------
# PreCompact
# ---------------------------------------------------------------------------


async def on_pre_compact_hook(
    agent_name: str,
    strategy: str,
    message_count: int,
    token_count: int,
) -> None:
    """Fire PreCompact hooks before history compaction (issue #298)."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="PreCompact",
        tool_name="compact",
        tool_args={
            "agent_name": agent_name,
            "strategy": strategy,
            "message_count": message_count,
            "token_count": token_count,
        },
    )

    try:
        await _hook_engine.process_event("PreCompact", event_data)
    except Exception as e:
        logger.error(f"Error in PreCompact hook: {e}", exc_info=True)


register_callback("pre_compact", on_pre_compact_hook)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------


async def on_notification_hook(
    message: str, level: str = "info", context: Any = None
) -> None:
    """Fire Notification hooks when the agent surfaces a user-attention event."""
    if not _hook_engine:
        return

    event_data = EventData(
        event_type="Notification",
        tool_name="notification",
        tool_args={"message": message, "level": level},
        context={"context": context} if context else {},
    )

    try:
        await _hook_engine.process_event("Notification", event_data)
    except Exception as e:
        logger.error(f"Error in Notification hook: {e}", exc_info=True)


register_callback("notification", on_notification_hook)


# ---------------------------------------------------------------------------
# Stop / SubagentStop  (via agent_run_end)
# ---------------------------------------------------------------------------


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


register_callback("agent_run_end", on_agent_run_end_hook)

logger.info(
    "Claude Code hooks plugin registered (PreToolUse, PostToolUse, "
    "SessionStart, SessionEnd, UserPromptSubmit, PreCompact, "
    "Notification, Stop, SubagentStop)"
)
