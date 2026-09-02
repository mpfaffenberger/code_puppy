"""Factory helpers for key-listener callbacks used by ``run_with_mcp``.

Extracted from ``_runtime.py`` to keep that module under the 600-line cap.
Each factory returns a thread-safe callable that closes over the agent
task + event loop and schedules the right action from the key-listener
daemon thread.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from code_puppy.command_line.attachments import resolve_steer_content
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.agent_tools import _active_subagent_tasks

# =============================================================================
# Run-detach seam — the escape hatch for zombie cancellations
# =============================================================================
#
# A cancelled run with sub-agents/MCP servers can get stuck unwinding (anyio
# cancel-scope teardown, plugin cancel hooks, ...). The REPL awaits the run
# task, the persistent prompt stays visually alive, and every quit gesture is
# gated on ``is_run_active()`` — so a stuck unwind freezes the whole app.
# The seam below lets repeated cancel gestures escalate to "abandon the run":
# ``run_prompt_with_attachments`` installs an event and races it against the
# agent task, so setting it unblocks the REPL even if the task never finishes.

#: A second cancel gesture this many seconds after the first one on a run
#: that STILL hasn't finished unwinding escalates to a detach.
CANCEL_ESCALATE_AFTER_S = 3.0

_detach_event: Optional[asyncio.Event] = None


def install_detach_event(event: asyncio.Event) -> None:
    """Register the top-level run's detach event (cli_runner owns it)."""
    global _detach_event
    _detach_event = event


def clear_detach_event() -> None:
    """Drop the seam once the run's await has resolved (normal or detached)."""
    global _detach_event
    _detach_event = None


def request_run_detach() -> bool:
    """Fire the detach event. Loop-thread only. Returns True if one was armed."""
    if _detach_event is None:
        return False
    _detach_event.set()
    return True


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

    # Closure state: monotonic time of the first cancel request, so a later
    # gesture on a still-stuck unwind can escalate to a detach (list, not a
    # bare float, to stay writable from the nested function without nonlocal
    # gymnastics on multiple call sites).
    first_cancel_at: list = []

    def schedule_agent_cancel(force: bool = False) -> None:
        from code_puppy.tools.command_runner import (
            _RUNNING_PROCESSES,
            _tear_down_live_panels,
            kill_all_running_shell_processes,
        )

        if agent_task.done():
            return
        # Escalation: the user already cancelled, waited, and is cancelling
        # again — the unwind is stuck. Abandon the run so the REPL (and
        # every quit gesture it gates) comes back. The zombie task is left
        # to finish — or not — in the background.
        now = time.monotonic()
        if first_cancel_at and now - first_cancel_at[0] >= CANCEL_ESCALATE_AFTER_S:
            _tear_down_live_panels()
            emit_warning(
                "\nRun is stuck cancelling — abandoning it and returning "
                "to the prompt..."
            )
            loop.call_soon_threadsafe(request_run_detach)
            return
        if not first_cancel_at:
            first_cancel_at.append(now)
        if _RUNNING_PROCESSES and not force:
            # Ordering matters (see _shell_sigint_handler): banner BEFORE the
            # kill — the sweep blocks this thread ~2s per process, so the
            # user deserves instant feedback.
            _tear_down_live_panels()
            # Key-agnostic wording: on POSIX this only runs via a REMAPPED
            # cancel key (ctrl+c routes through _shell_sigint_handler), so
            # "Ctrl-C detected!" would be a lie there.
            emit_warning(
                "\nCancel requested! Stopping the agent (shells + all sub-agents)..."
            )
            kill_all_running_shell_processes()
        if _active_subagent_tasks:
            # Hide the sub-agent status panel (inside the spinner's Live) like
            # the steer flow, so the cancel banner isn't repainted over.
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
#   - a ``now`` steer that missed the final model boundary lingers into the
#     next run instead of the queued turn the user expects; and
#   - a run that crashed mid-pause leaves it paused, freezing the next run.
# Both bugs are bad. The two helpers below scrub that state.


def reset_pause_state_at_run_start() -> None:
    """Scrub stale ``PauseController`` state before a fresh agent run.

    Called from the top of ``run_with_mcp`` BEFORE any agent work begins.
    Undelivered ``now`` steers are preserved as queued turns: they missed
    their intended history-processor boundary, but they are still user input.
    """
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    # Clear any stale paused state (e.g. from a prior run that crashed
    # mid-pause). Safe / idempotent if already resumed.
    pc.resume()
    stale_compactions = pc.drain_compaction_requests()
    if stale_compactions:
        emit_warning(
            f"Discarded {stale_compactions} stale compaction request(s) from a previous run."
        )
    deferred_steers = pc.defer_pending_steer_now()
    if deferred_steers:
        emit_info(
            f"Queued {deferred_steers} steering message(s) that missed the previous run."
        )


def prepare_queued_steer_injection(agent: Any, result: Any) -> Optional[Any]:
    """Drain ONE queue-mode steer and prep for between-turns injection.

    Called from ``_runtime._do_run``'s while-loop after each ``agent.run()``.
    Returns the steer content to inject as the next user turn — a plain
    string, or a multimodal list when the steer carries attachments
    (clipboard images, ``@file`` paths, URLs) — or ``None`` if no
    queue-mode steer is pending.

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
    return content


def inject_interrupted_subagent_notes(agent: Any) -> None:
    """Tell the agent about any sub-agents interrupted since the last run.

    Ctrl+C cancels both the delegated sub-agent task and the parent run, and
    the parent's return-less ``invoke_agent`` tool call is pruned from history
    as a dangling call -- so without this the model would have no memory that
    it ever delegated. We drain the records left by the sub-agent cancel path
    and append one plain user-message note per interrupted session (the same
    injection shape the steer processor uses), which survives the interrupted
    tool-call prune because it is a valid standalone message.

    Called at run start (never nested) so a foreground cancel surfaces on the
    user's next turn, and a ``/fork`` cancelled while the agent was idle
    surfaces on the next run too.
    """
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from code_puppy.tools.subagent_invocation import drain_interrupted_subagents

    if not hasattr(agent, "_message_history"):
        return
    records = drain_interrupted_subagents()
    if not records:
        return

    injected = []
    for rec in records:
        session_id = rec["session_id"]
        saved = rec["saved_count"]
        saved_phrase = (
            f"{saved} message(s) of its work were saved"
            if saved is not None
            else "no completed messages had been produced yet"
        )
        note = (
            f"[system note] The sub-agent '{rec['agent_name']}' you invoked was "
            f"interrupted by the user before it finished; {saved_phrase}. Its "
            f"partial session is saved as '{session_id}'."
        )
        injected.append(ModelRequest(parts=[UserPromptPart(content=note)]))
        emit_info(
            f"Noting interrupted sub-agent '{rec['agent_name']}' "
            f"(session {session_id}) for the agent's next turn."
        )

    agent._message_history = list(agent._message_history) + injected


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
    "CANCEL_ESCALATE_AFTER_S",
    "clear_detach_event",
    "drain_pause_state_on_cancel",
    "inject_interrupted_subagent_notes",
    "install_detach_event",
    "make_schedule_cancel",
    "prepare_queued_steer_injection",
    "request_run_detach",
    "reset_pause_state_at_run_start",
    "sigint_should_cancel",
]
