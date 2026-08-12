"""
Register callbacks for Claude Code hooks plugin.

Integrates the hook engine with code_puppy's callback system.

This bridge maps Claude Code hook events to code_puppy lifecycle callbacks:

    Claude Code event   →  code_puppy callback
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
from typing import Any, Dict, List, Optional, Union

from code_puppy.callbacks import PromptBlocked, register_callback
from code_puppy.hook_engine import EventData, HookEngine
from code_puppy.session_context import get_session_id

from .config import load_hooks_config


def _is_subagent_run(agent_name: Optional[str]) -> bool:
    """Whether the run that just ended was a sub-agent's.

    Decided by the sub-agent depth ContextVar, which is what actually tracks
    nesting. The name is only a fallback for a caller that ends a run outside
    the ``subagent_context`` manager.

    This deliberately does NOT guess from the agent's name alone: the DEFAULT
    agent is called ``code-puppy``, so a name-matching list containing it
    classified every top-level turn as a sub-agent and ``Stop`` never fired at
    all. A sub-agent can also be named anything, so the name was never a sound
    signal in either direction.
    """
    try:
        from code_puppy.tools.subagent_context import is_subagent

        if is_subagent():
            return True
    except Exception:
        pass

    lowered = (agent_name or "").lower()
    return any(name in lowered for name in _FALLBACK_SUBAGENT_NAMES)


# Names checked only when the depth ContextVar is unavailable. ``code-puppy``
# and ``code_puppy`` are absent on purpose — that is the default agent.
_FALLBACK_SUBAGENT_NAMES = frozenset(
    {
        "pack_leader",
        "bloodhound",
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


def _event_context(
    extra: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build an ``EventData.context`` that carries the current run's session id.

    ``_build_stdin_payload`` reads ``session_id`` from here. Without it every
    event falls back to the placeholder ``"codepuppy-session"``, so a hook
    script cannot tell one run from another.

    An explicit *session_id* wins (the callback was handed one); otherwise we
    fall back to the run-scoped ContextVar. The key is omitted entirely when
    neither is available, so the payload builder's own default still applies.
    """
    ctx: Dict[str, Any] = dict(extra or {})
    resolved = session_id or ctx.get("session_id") or get_session_id()
    if resolved:
        ctx["session_id"] = resolved
    else:
        ctx.pop("session_id", None)
    return ctx


def _block_reason(result: Any) -> str:
    """The human-facing reason a hook blocked, preferring the hook's own stderr.

    ``ProcessEventResult.blocking_reason`` is a diagnostic string of the form
    ``Hook '<full command line>' failed: <stderr>``. That is useful in a log and
    poor in front of a user — it leaks the hook's path and says "failed" for a
    hook that deliberately blocked. The individual result carries the stderr on
    its own, so use that and fall back to the diagnostic form.
    """
    for r in getattr(result, "results", []) or []:
        if not getattr(r, "blocked", False):
            continue
        for candidate in (getattr(r, "stderr", ""), getattr(r, "error", "")):
            text = (candidate or "").strip()
            if text:
                return text
    reason = (getattr(result, "blocking_reason", "") or "").strip()
    return reason or "No reason was provided by the hook."


def _blocked_prompt_replacement(reason: Optional[str]) -> str:
    """The prompt substituted for one a ``UserPromptSubmit`` hook blocked.

    The user's original text is deliberately dropped — that is the entire point
    of a block — so it never reaches the model. ``run_with_mcp`` sends whatever
    string this returns in place of the prompt.
    """
    detail = (reason or "").strip() or "No reason was provided by the hook."
    return (
        "[BLOCKED BY HOOK] The user's prompt was withheld by a UserPromptSubmit "
        "policy hook and is not available to you.\n\n"
        f"Reason: {detail}\n\n"
        "Do not guess at, reconstruct, or act on the withheld prompt. Tell the "
        "user their prompt was blocked, relay the reason above, and stop."
    )


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
        context=_event_context({"context": context} if context else None),
    )

    try:
        result = await _hook_engine.process_event("PreToolUse", event_data)

        if result.blocked:
            reason = _block_reason(result)
            logger.debug(f"Tool '{tool_name}' blocked by hook: {reason}")
            return {
                "blocked": True,
                "reason": reason,
                "error_message": reason,
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
) -> Optional[Dict[str, Any]]:
    """Post-tool callback — executes hooks after a tool completes.

    A blocking hook here withholds the tool's OUTPUT from the model; the tool
    itself has already run. Returns the block verdict for ``_run_post_tool_call``
    to act on, or ``None`` to pass the result through untouched.
    """
    if not _hook_engine:
        return None

    event_data = EventData(
        event_type="PostToolUse",
        tool_name=tool_name,
        tool_args=tool_args,
        context=_event_context(
            {"result": result, "duration_ms": duration_ms, "context": context}
        ),
    )

    try:
        outcome = await _hook_engine.process_event("PostToolUse", event_data)
        if outcome.blocked:
            reason = _block_reason(outcome)
            logger.debug(f"Output of '{tool_name}' withheld by hook: {reason}")
            return {"blocked": True, "reason": reason, "error_message": reason}
        return None
    except Exception as e:
        logger.error(f"Error in post-tool hook: {e}", exc_info=True)
        return None


register_callback("pre_tool_call", on_pre_tool_call_hook)
register_callback("post_tool_call", on_post_tool_call_hook)


# ---------------------------------------------------------------------------
# SessionStart  /  SessionEnd
# ---------------------------------------------------------------------------


async def on_startup_hook() -> None:
    """Startup callback — fires SessionStart hooks when code_puppy boots.

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
        context=_event_context(),
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
        context=_event_context(),
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
) -> Optional[Union[str, PromptBlocked]]:
    """Fire UserPromptSubmit hooks and inject their stdout (+ any pending
    SessionStart stdout) into the user prompt.

    A blocking hook (exit code 1, or a ``deny`` / ``block`` stdout control
    payload) returns a :class:`PromptBlocked`, which cancels the turn on a
    top-level run and substitutes a block notice on a nested one. Either way
    the prompt text never reaches the model.

    Returns ``PromptBlocked``, the augmented prompt, or ``None`` if there's
    nothing to add. See issue #298.
    """
    hook_chunks: List[str] = []

    if _hook_engine:
        event_data = EventData(
            event_type="UserPromptSubmit",
            tool_name="user_prompt",
            tool_args={"prompt": prompt},
            context=_event_context(session_id=session_id),
        )

        try:
            result = await _hook_engine.process_event("UserPromptSubmit", event_data)
            if result.blocked:
                reason = _block_reason(result)
                logger.debug(f"Prompt blocked by hook: {reason}")
                # _pending_session_context is deliberately left intact: this
                # prompt never runs, so its SessionStart context still belongs
                # to the next prompt that does.
                return PromptBlocked(
                    reason=reason,
                    replacement=_blocked_prompt_replacement(reason),
                )
            hook_chunks = _collect_context_stdout(result)
        except Exception as e:
            logger.error(f"Error in UserPromptSubmit hook: {e}", exc_info=True)

    chunks: List[str] = []

    # Drain any pending SessionStart context first.
    if _pending_session_context:
        chunks.extend(_pending_session_context)
        _pending_session_context.clear()

    chunks.extend(hook_chunks)

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
        context=_event_context(),
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
        context=_event_context({"context": context} if context else None),
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

    event_type = "SubagentStop" if _is_subagent_run(agent_name) else "Stop"

    event_data = EventData(
        event_type=event_type,
        tool_name=agent_name or "agent",
        tool_args={},
        context=_event_context(
            {
                "agent_name": agent_name,
                "model_name": model_name,
                "success": success,
                "error": str(error) if error else None,
                "response_text": response_text,
                "metadata": metadata,
            },
            session_id=session_id,
        ),
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
