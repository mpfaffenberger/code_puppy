"""Factory helpers for key-listener callbacks used by ``run_with_mcp``.

Extracted from ``_runtime.py`` to keep that module under the 600-line cap.
Each factory returns a thread-safe callable that closes over the agent
task + event loop and schedules the right action from the key-listener
daemon thread.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.agent_tools import _active_subagent_tasks


def make_schedule_cancel(
    agent_task: "asyncio.Task[Any]",
    loop: asyncio.AbstractEventLoop,
) -> Callable[[], None]:
    """Build the ``schedule_agent_cancel`` callback for the key listener."""

    def schedule_agent_cancel() -> None:
        from code_puppy.tools.command_runner import _RUNNING_PROCESSES

        if _RUNNING_PROCESSES:
            emit_warning(
                "Refusing to cancel Agent while a shell command is running — "
                "press Ctrl+X to cancel the shell command."
            )
            return
        if agent_task.done():
            return
        if _active_subagent_tasks:
            emit_warning(
                f"Cancelling {len(_active_subagent_tasks)} active subagent task(s)..."
            )
            for task in list(_active_subagent_tasks):
                if not task.done():
                    loop.call_soon_threadsafe(task.cancel)
        loop.call_soon_threadsafe(agent_task.cancel)

    return schedule_agent_cancel


def make_schedule_pause(
    agent_task: "asyncio.Task[Any]",
    loop: asyncio.AbstractEventLoop,
) -> Callable[[], None]:
    """Build the ``schedule_agent_pause`` callback for the key listener.

    Fires the ``agent_pause_requested`` callback so plugins (e.g.
    ``agent_steering``) can collect a steering message + drive the
    pause→steer→resume bus dance.

    Unlike ``make_schedule_cancel``, this is **safe to invoke during a
    running shell command**: the renderer buffers all output while the
    PauseController is paused, so shell stdout/stderr can't trash the
    steering prompt. Cancel still refuses mid-shell because cancel ends
    the task and could orphan the subprocess.
    """

    def schedule_agent_pause() -> None:
        if agent_task.done():
            return
        # Re-pause while paused = duplicate keypress — silently ignore so
        # we don't spawn N steering editors on top of each other.
        from code_puppy.messaging.pause_controller import get_pause_controller

        if get_pause_controller().is_paused():
            return
        from code_puppy.callbacks import on_agent_pause_requested

        try:
            asyncio.run_coroutine_threadsafe(on_agent_pause_requested(), loop)
        except RuntimeError:
            # Loop closed; nothing to do.
            pass

    return schedule_agent_pause


# =============================================================================
# PauseController hygiene — prevent cross-run leakage
# =============================================================================
#
# ``PauseController`` is a process-wide singleton. Without explicit hygiene:
#   - A cancelled run that left ``request_steer`` items in the queue would
#     have those items consumed by the NEXT agent run (possibly a totally
#     different session / agent), as if the user had typed them.
#   - A run that crashed mid-pause would leave the controller in a paused
#     state, freezing the next run's spinner + event stream.
# Both bugs are bad. The two helpers below scrub that state.


def reset_pause_state_at_run_start() -> None:
    """Scrub stale ``PauseController`` state before a fresh agent run.

    Called from the top of ``run_with_mcp`` BEFORE any agent work begins.
    If we find pending steers from a prior cancelled run, emit a warning
    (with a preview of the first one) so the user knows we discarded
    something rather than silently swallowing it.
    """
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    # Clear any stale paused state (e.g. from a prior run that crashed
    # mid-pause). Safe / idempotent if already resumed.
    pc.resume()
    stale_steers = pc.drain_pending_steer()
    if stale_steers:
        emit_warning(
            f"Discarded {len(stale_steers)} stale steering message(s) from a previous run."
        )


def prepare_queued_steer_injection(agent: Any, result: Any) -> Optional[str]:
    """Drain ONE queue-mode steer and prep for between-turns injection.

    Called from ``_runtime._do_run``'s while-loop after each ``agent.run()``.
    Returns the steer text to inject as the next user turn, or ``None`` if
    no queue-mode steer is pending.

    Side-effects:
      - Persists ``result.all_messages()`` into ``agent._message_history``
        so the steer turn sees the just-completed turn's context.
      - Re-queues any leftover steers (we deliberately process ONE per
        loop iteration to keep turn boundaries clean for the model).
      - Emits a diagnostic with a preview of the steer text.
    """
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    pending = pc.drain_pending_steer_queued()
    if not pending:
        return None
    if hasattr(result, "all_messages"):
        agent._message_history = list(result.all_messages())
    steer_text = pending[0]
    for leftover in pending[1:]:
        pc.request_steer(leftover, mode="queue")
    preview = steer_text[:80] + ("..." if len(steer_text) > 80 else "")
    emit_info(f"📨 Injecting queued steer between turns — agent will see: {preview!r}")
    return steer_text


def drain_pause_state_on_cancel() -> None:
    """Clear ``PauseController`` state when a run is cancelled.

    Called from every cancel-y exception branch in the runtime so a
    half-typed steering message from a Ctrl+C'd run doesn't leak into
    the next run.
    """
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    pc.resume()  # in case we're cancelling from a paused state
    drained = pc.drain_pending_steer()
    if drained:
        emit_info(
            f"🧹 Discarded {len(drained)} undelivered steering message(s) on cancel."
        )


__all__ = [
    "drain_pause_state_on_cancel",
    "make_schedule_cancel",
    "make_schedule_pause",
    "prepare_queued_steer_injection",
    "reset_pause_state_at_run_start",
]
