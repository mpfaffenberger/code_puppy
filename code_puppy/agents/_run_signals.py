"""Factory helpers for key-listener callbacks used by ``run_with_mcp``.

Extracted from ``_runtime.py`` to keep that module under the 600-line cap.
Each factory returns a thread-safe callable that closes over the agent
task + event loop and schedules the right action from the key-listener
daemon thread.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from code_puppy.command_line.attachments import resolve_steer_content
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.agent_tools import _active_subagent_tasks


def sigint_should_cancel() -> bool:
    """Buffer-first Ctrl+C gate for the run's SIGINT handler.

    Returns False when the press was absorbed by composing input (text
    in the persistent editor / reverse-search active — the editor is
    cleared and a hint shown instead). Applies ONLY to the Ctrl+C/SIGINT
    cancel path: remapped cancel hotkeys and the shell-tool SIGINT
    handler (tool interrupt) are deliberately not gated. Fails open —
    cancellation must never break because a UI check raised.
    """
    try:
        from code_puppy.messaging.run_ui import absorb_ctrl_c_if_composing

        return not absorb_ctrl_c_if_composing()
    except Exception:
        return True


def make_schedule_cancel(
    agent_task: "asyncio.Task[Any]",
    loop: asyncio.AbstractEventLoop,
) -> Callable[[], None]:
    """Build the ``schedule_agent_cancel`` callback for the key listener.

    The returned callback accepts ``force``: when ``True`` it skips the
    kill-running-shells step. The shell SIGINT handler uses
    ``force=True`` because it kills all shells *before* requesting the
    cancel, so sweeping them again here would be redundant.

    When ``force`` is False and shells ARE running, the callback kills
    them first and then cancels — mirroring ``_shell_sigint_handler``
    (the out-of-band SIGINT fallback path). This is load-bearing on
    EVERY platform now that Ctrl+C is a pure keybinding: Windows strips
    ENABLE_PROCESSED_INPUT and POSIX disables the tty INTR char while
    the key listener owns stdin, so ^C never becomes a SIGINT — it
    arrives as a raw ``\\x03`` and lands HERE instead of in the shell
    SIGINT handler. The old behavior (refuse + "press Ctrl+X") left
    Ctrl+C dead for the entire lifetime of every shell command:
    the run stayed active, new submissions queued as steers,
    and the eventual cancel discarded them. Killing the shells first
    preserves the guard's anti-orphan rationale (a cancelled executor
    await would otherwise leave the subprocess spewing into the
    terminal) while letting the cancel actually proceed.
    """

    def schedule_agent_cancel(force: bool = False) -> None:
        from code_puppy.tools.command_runner import (
            _RUNNING_PROCESSES,
            _tear_down_live_panels,
            kill_all_running_shell_processes,
        )

        if agent_task.done():
            return
        if _RUNNING_PROCESSES and not force:
            # Ordering matters (see _shell_sigint_handler): hide the
            # panel and show the banner BEFORE the kill — the sweep
            # blocks this (key-listener) thread up to ~2s per process,
            # and the user deserves instant feedback.
            _tear_down_live_panels()
            # Key-agnostic wording: on POSIX this branch is only reachable
            # via a REMAPPED cancel hotkey (ctrl+k/ctrl+q — SIGINT owns
            # ctrl+c and routes through _shell_sigint_handler instead),
            # so "Ctrl-C detected!" would be a lie there.
            emit_warning(
                "\nCancel requested! Stopping the agent (shells + all sub-agents)..."
            )
            kill_all_running_shell_processes()
        if _active_subagent_tasks:
            # Hide the sub-agent status panel (rendered inside the spinner's
            # Live) the same way the steer flow does, so the cancel banner
            # isn't instantly repainted over. Mirrors _shell_sigint_handler.
            _tear_down_live_panels()
            emit_warning(
                f"Cancelling {len(_active_subagent_tasks)} active subagent task(s)..."
            )
            for task in list(_active_subagent_tasks):
                if not task.done():
                    loop.call_soon_threadsafe(task.cancel)
        loop.call_soon_threadsafe(agent_task.cancel)

    return schedule_agent_cancel


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


def prepare_queued_steer_injection(agent: Any, result: Any) -> Optional[tuple]:
    """Drain ONE queue-mode steer and prep for between-turns injection.

    Called from ``_runtime._do_run``'s while-loop after each ``agent.run()``.
    Returns ``(content, echo_text)`` where ``content`` is the steer payload to
    inject (plain string or multimodal list) and ``echo_text`` is a plain-text
    preview for UI display — or ``None`` if no queue-mode steer is pending.

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
    content, preview_text = resolve_steer_content(steer_text)
    n_extras = len(content) - 1 if isinstance(content, list) else 0
    suffix = f" (+{n_extras} attachment(s))" if n_extras else ""
    preview = preview_text[:80] + ("..." if len(preview_text) > 80 else "")
    emit_info(
        f"Injecting queued steer between turns — agent will see: {preview!r}{suffix}"
    )
    # Return (content, echo_text) so _do_run can fire the prompt-echo
    # stream_event synchronously (on the event loop, ordered before the
    # next agent.run() stream deltas). Bus emit was removed: it has a
    # 10 ms polling delay that races with the next turn's stream events.
    return content, preview_text


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
    "prepare_queued_steer_injection",
    "reset_pause_state_at_run_start",
    "sigint_should_cancel",
]
