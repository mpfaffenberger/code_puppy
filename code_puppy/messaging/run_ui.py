"""Composed run-time UI: bottom bar + running line editor + key routing.

This is the glue the run path uses (Phase 3 of the bottom-bar rewrite):

* :func:`start_run_ui` — starts the bottom bar (scroll region), creates a
  :class:`~code_puppy.messaging.line_editor.RunningLineEditor`, and
  installs it as the key-listener feed target so typing works while the
  agent runs.
* :func:`stop_run_ui` — unregisters the editor and restores the terminal.
  Both are idempotent and safe on non-TTY stdout (headless ``-p`` mode,
  pipes, CI) where everything degrades to a no-op.
* :func:`run_ui` — context-manager wrapper (exception-safe start/stop).
* :func:`suspended_run_ui` — combined suspension for code that takes over
  the whole terminal (prompt_toolkit menus, ``ask_user_question`` TUI,
  interactive approval prompts): nests ``bottom_bar.suspended()`` with
  ``suspended_key_listener()`` so stdin AND the scroll region are both
  released, then restored.

Slash commands mid-run (Phase 5): typing ``/cmd`` on the persistent prompt
queues it on the editor; a submit listener schedules
:func:`_drain_pending_commands` onto the main event loop (captured at
:func:`start_run_ui` time), which pauses the agent via the message bus
(``PauseAgentCommand`` → the ``wait_if_paused`` gate in
``event_stream_handler``), executes the command(s) exactly like the idle
REPL would, then resumes (``ResumeAgentCommand``).

Execution-context decision: ``handle_command`` runs DIRECTLY in the
consumer coroutine — main thread, inside the running loop — because that
is byte-for-byte the context the idle REPL calls it from (a sync call in
an async loop's stack frame). Pushing it to an executor thread would
BREAK commands that touch asyncio or open prompt_toolkit apps (they
expect the main thread / a reachable running loop). Yes, a slow command
blocks the loop — that's fine: the agent is paused and waiting anyway.

Import note: the key-listener lives in ``code_puppy.agents`` which imports
``code_puppy.messaging`` — so this module lazy-imports it inside functions
to avoid an import cycle at package-init time.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from .bottom_bar import get_bottom_bar
from .line_editor import RunningLineEditor
from .chords import register_chord, unregister_chord
from .external_editor import make_external_edit_handler
from .run_ui_wiring import attach_completion, make_clipboard_handler

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_editor: Optional[RunningLineEditor] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_draining = False

# --- Persistent-prompt state (Phase A: the bar IS the prompt) -----------
# When persistent, the bar + editor + key listener live for the whole
# REPL; start_run_ui/stop_run_ui merely toggle _run_active so submission
# routing (idle = new turn, running = steer/slash-drain) stays correct.
_persistent = False
_run_active = False
_idle_queue: "Optional[asyncio.Queue]" = None


def _get_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Locked read of the captured loop (for run_ui_wiring helpers)."""
    with _lock:
        return _loop


_listener_handle = None  # KeyListenerHandle owned by the persistent UI
_EOF = object()  # idle-queue sentinel: Ctrl+D on an empty buffer

#: How long the consumer waits for the agent to actually park at its
#: pause boundary before running commands anyway (best-effort).
_PARK_TIMEOUT_S = 2.0

#: Commands that must NOT execute while an agent run is in flight, with a
#: one-line reason each. Conservative: anything that mutates the agent,
#: its message history, or the session is deferred to the idle REPL.
MID_RUN_DENYLIST: Dict[str, str] = {
    "exit": "terminates the app; cancel the run first (Ctrl+C)",
    "quit": "terminates the app; cancel the run first (Ctrl+C)",
    "agent": "switches/reloads the active agent while agent.run() is in flight",
    "clear": "wipes message history the in-flight run will commit at turn end",
    "truncate": "mutates message history mid-run",
    "autosave_load": "returns the __AUTOSAVE_LOAD__ sentinel only the idle REPL can service",
    "quick-resume": "loads a saved session into message history mid-run",
    "load_context": "replaces message history mid-run",
    "session": "switches/renames the session the in-flight run writes to",
    "undo": "reverts file changes the agent may be actively editing",
    "mcp": "starting/stopping MCP servers breaks in-flight tool calls",
}


def start_run_ui() -> Optional[RunningLineEditor]:
    """Start the bottom bar + line editor for an agent run.

    Idempotent: if already started, returns the existing editor. On
    non-TTY stdout the bar refuses to activate and NO editor is created
    (returns ``None``) — headless mode stays byte-identical.

    Persistent mode: the UI is already up for the REPL's whole life, so
    this merely flips the run-active flag (submission routing switches
    from idle-turn to steer/slash-drain).
    """
    global _editor, _loop, _run_active
    with _lock:
        if _persistent:
            _run_active = True
            return _editor
        if _editor is not None:
            return _editor
        bar = get_bottom_bar()
        bar.start()
        if not bar.is_active():
            return None  # non-TTY: no bar, no editor
        editor = RunningLineEditor()
        _editor = editor
        # Capture the main loop for the slash-command consumer — the
        # editor's feed() runs on the key-listener daemon thread, but
        # command execution needs the loop (see module docstring).
        try:
            _loop = asyncio.get_running_loop()
        except RuntimeError:
            _loop = None
    editor.add_submit_listener(_make_slash_listener(editor))
    editor.set_clipboard_handler(make_clipboard_handler(editor, _get_loop))
    # Ctrl+X Ctrl+E: edit the prompt in $EDITOR (chord registry — shell
    # kill/background chords are registered by command_runner while
    # shells run; this one lives for the UI's lifetime).
    register_chord(
        "\x05",
        make_external_edit_handler(editor, _get_loop),
        "Ctrl+E edit in $EDITOR",
    )
    attach_completion(editor, _get_loop)
    _set_feed_target(editor)
    editor.repaint()
    return editor


def stop_run_ui() -> None:
    """Tear down the run UI: unhook the editor, restore the terminal.

    Idempotent; never raises (runs in ``finally`` blocks on cancel and
    exception paths).
    """
    global _editor, _loop, _run_active
    with _lock:
        if _persistent:
            # The UI outlives the run — just drop back to idle routing.
            _run_active = False
            _clear_status_row()
            # Self-heal: if the REPL-lifetime listener died mid-run (its
            # thread crashed, or a per-run listener replaced-then-stopped
            # it), typing at the idle prompt would be dead forever.
            _ensure_persistent_listener_locked()
            return
        editor = _editor
        _editor = None
        _loop = None
    if editor is not None:
        _set_feed_target(None)
    unregister_chord("\x05")  # the handler closes over the dead editor
    _clear_status_row()
    try:
        get_bottom_bar().stop()
    except Exception:
        # Terminal restore is best-effort on teardown paths.
        logger.debug("bottom bar stop failed", exc_info=True)


def _clear_status_row() -> None:
    """Run over (finished OR cancelled): drop the token/context line.

    The status row only means something while an agent is working; a
    stale '5.5k/500k tokens' under an idle prompt is just noise — and
    clearing both slots collapses the row entirely (the bar reclaims
    it for the scroll region). Never raises: this runs on finally paths.
    """
    try:
        get_bottom_bar().set_status("")
    except Exception:
        logger.debug("status clear failed", exc_info=True)


def get_run_editor() -> Optional[RunningLineEditor]:
    """The live editor for the current run, or ``None``."""
    with _lock:
        return _editor


@contextmanager
def run_ui() -> Iterator[Optional[RunningLineEditor]]:
    """Context manager: run UI active for the duration of the block."""
    editor = start_run_ui()
    try:
        yield editor
    finally:
        stop_run_ui()


@contextmanager
def suspended_run_ui() -> Iterator[None]:
    """Release the scroll region AND stdin; restore both afterwards.

    Reentrant (both underlying suspensions are refcounted). Safe when
    neither the bar nor a key listener is active — everything no-ops.
    """
    with get_bottom_bar().suspended():
        with _suspended_key_listener()():
            yield


# =============================================================================
# Persistent prompt (Phase A: bar + editor + listener live for the REPL)
# =============================================================================


def start_persistent_ui(
    prompt_prefix: Optional[str] = None,
    prefix_sgrs: Optional[list] = None,
) -> bool:
    """Bring up the bar/editor/key-listener for the REPL's whole life.

    Returns False (and leaves nothing running) on non-TTY stdout so the
    caller can fall back to the classic prompt_toolkit path. Idempotent.
    """
    global _persistent, _run_active, _idle_queue
    with _lock:
        already = _persistent
    if already:
        return True
    editor = start_run_ui()  # builds bar + editor + captures the loop
    if editor is None:
        return False  # non-TTY: caller degrades to the classic prompt
    with _lock:
        _persistent = True
        _run_active = False
        _idle_queue = asyncio.Queue()
    if prompt_prefix:
        editor.set_prompt_prefix(prompt_prefix, prefix_sgrs)
    editor.set_submit_router(_persistent_router)
    editor.set_eof_handler(_handle_eof)
    _spawn_persistent_listener()
    return True


def stop_persistent_ui() -> None:
    """Tear the persistent UI down (REPL exit). Idempotent, never raises."""
    global _persistent, _run_active, _idle_queue, _listener_handle
    with _lock:
        was_persistent = _persistent
        _persistent = False
        _run_active = False
        _idle_queue = None
        handle = _listener_handle
        _listener_handle = None
    if was_persistent:
        editor = get_run_editor()
        if editor is not None:
            editor.set_submit_router(None)
            editor.set_eof_handler(None)
        stop_run_ui()  # persistent flag is off -> full teardown
    if handle is not None:
        try:
            from code_puppy.agents._key_listeners import set_active_handle

            set_active_handle(None)
        except ImportError:
            pass
        try:
            handle.stop()
            handle.thread.join(timeout=1.0)
        except Exception:
            logger.debug("persistent listener stop failed", exc_info=True)


def is_persistent() -> bool:
    """True while the persistent prompt owns the UI (REPL lifetime)."""
    with _lock:
        return _persistent


def is_run_active() -> bool:
    """True while an agent run is in flight.

    Persistent mode tracks an explicit flag (the editor exists either
    way); classic mode infers it from the per-run editor's existence.
    """
    with _lock:
        if _persistent:
            return _run_active
        return _editor is not None


async def wait_for_idle_submission() -> str:
    """Await the next idle submission from the persistent prompt.

    Raises EOFError on Ctrl+D-with-empty-buffer (mirrors the classic
    input path so the REPL's existing quit handling just works).
    """
    with _lock:
        q = _idle_queue
    if q is None:
        raise EOFError  # persistent UI gone -> treat as end of input
    item = await q.get()
    if item is _EOF:
        raise EOFError
    return item


def set_idle_prompt_prefix(prefix: str, prefix_sgrs: Optional[list] = None) -> None:
    """Refresh the prompt-row prefix (model/agent may change per turn)."""
    editor = get_run_editor()
    if editor is not None:
        editor.set_prompt_prefix(prefix, prefix_sgrs)


def clear_idle_buffer() -> None:
    """Ctrl+C at idle: wipe typed text, keep the REPL alive. No-op while
    a run is active (per-run handlers own Ctrl+C) or in classic mode."""
    if not is_persistent() or is_run_active():
        return
    editor = get_run_editor()
    if editor is not None:
        editor.clear_buffer()


def absorb_ctrl_c_if_composing() -> bool:
    """Buffer-first Ctrl+C mid-run (Claude Code / Gemini CLI convention).

    Composing (buffered text OR reverse-i-search active) → clear it,
    show a dim hint, return True: the SIGINT handler swallows the press
    instead of cancelling the run. Empty prompt → False. Only Ctrl+C/
    SIGINT is gated; remapped cancel hotkeys stay unconditional.
    """
    editor = get_run_editor()
    if editor is None or not editor.is_composing():
        return False
    editor.clear_buffer()
    try:
        get_bottom_bar().set_status(_cleared_hint())
    except Exception:
        logger.debug("ctrl+c hint paint failed", exc_info=True)
    return True


def _cleared_hint() -> str:
    """Status hint after a buffer-first Ctrl+C — names the REAL cancel key.

    When the cancel key IS ctrl+c (the default everywhere — the press
    that just cleared the buffer was the cancel gesture), say "again".
    When cancel is remapped (ctrl+k/ctrl+q), "press ctrl+c again" would
    be a lie — name the real key instead.
    """
    try:
        from code_puppy.keymap import (
            get_cancel_agent_display_name,
            get_cancel_agent_key,
        )

        if get_cancel_agent_key() == "ctrl+c":
            return "input cleared — press ctrl+c again to cancel the agent"
        key = get_cancel_agent_display_name().lower()
        return f"input cleared — press {key} to cancel the agent"
    except Exception:
        return "input cleared"


def _persistent_router(text: str, mode: str) -> Optional[str]:
    """Central idle-vs-running routing for the persistent prompt."""
    editor = get_run_editor()
    if is_run_active():
        # Mid-run: keep Phase 1-5 semantics (steer now / Alt+Enter queue /
        # slash -> drain queue, scheduled by the submit listener).
        if editor is not None:
            return editor.route_default(text, mode)
        return None
    # Idle: every submission (slash or not) is a new REPL line, dispatched
    # through the existing interactive-loop pipeline.
    _push_idle(text.strip())
    return None


def _handle_eof() -> None:
    """Ctrl+D on an empty buffer: quit — but only at idle."""
    if is_run_active():
        return
    _push_idle(_EOF)


def _push_idle(item) -> None:
    """Thread-safe hand-off from the key-listener thread to the loop."""
    with _lock:
        loop = _loop
        q = _idle_queue
    if loop is None or q is None or loop.is_closed():
        if isinstance(item, str):
            _warn_command_dropped(item)
        return
    try:
        loop.call_soon_threadsafe(q.put_nowait, item)
    except RuntimeError:
        if isinstance(item, str):
            _warn_command_dropped(item)


def _spawn_persistent_listener() -> None:
    """Spawn the REPL-lifetime key listener (unless one already runs)."""
    global _listener_handle
    try:
        from code_puppy.agents import _key_listeners
    except ImportError:
        return  # no listener infra: prompt still works via nothing-to-feed
    stop_event = threading.Event()
    # Atomic reuse-or-spawn: if someone else already owns stdin we back
    # off (spawned=False) and deliberately do NOT record their handle as
    # ours — stop_persistent_ui must never stop a listener it didn't spawn.
    handle, spawned = _key_listeners.acquire_listener(
        stop_event, on_escape=lambda: None
    )
    if handle is None or not spawned:
        return
    with _lock:
        _listener_handle = handle


def _ensure_persistent_listener_locked() -> None:
    """Respawn the persistent listener if it died. Caller holds ``_lock``.

    Never raises — this runs on ``finally`` teardown paths.
    """
    global _listener_handle
    handle = _listener_handle
    if (
        handle is not None
        and handle.thread.is_alive()
        and not handle.stop_event.is_set()
    ):
        return  # healthy
    try:
        from code_puppy.agents import _key_listeners
    except ImportError:
        return
    try:
        # Drop the stale registration (if it's still ours) so
        # acquire_listener doesn't refuse to spawn over a corpse.
        if handle is not None and _key_listeners.get_active_handle() is handle:
            _key_listeners.set_active_handle(None)
        _listener_handle = None
        stop_event = threading.Event()
        new_handle, spawned = _key_listeners.acquire_listener(
            stop_event, on_escape=lambda: None
        )
        if new_handle is not None and spawned:
            _listener_handle = new_handle
    except Exception:
        logger.debug("persistent listener respawn failed", exc_info=True)


# =============================================================================
# Slash-command consumer (Phase 5)
# =============================================================================


def is_draining() -> bool:
    """True while the slash-command consumer owns a pause window.

    ``event_stream_handler``'s pause gate uses this to re-arm an expired
    pause instead of force-resuming underneath a running command.
    """
    with _lock:
        return _draining


def _make_slash_listener(editor: RunningLineEditor):
    """Build a submit listener that schedules the drain for ``editor``.

    The closure captures the editor so pending commands survive even if
    ``stop_run_ui()`` nulls the module reference before the consumer runs
    (the run-just-finished edge case — the command still executes; pause/
    resume on a finished run are harmless flag flips).
    """

    def _listener(text: str, mode: str) -> None:
        if not text.startswith("/"):
            return
        with _lock:
            loop = _loop
        if loop is None or loop.is_closed():
            _warn_command_dropped(text)
            return
        try:
            asyncio.run_coroutine_threadsafe(_drain_pending_commands(editor), loop)
        except RuntimeError:
            # Loop shut down between the check and the call.
            _warn_command_dropped(text)

    return _listener


def _warn_command_dropped(text: str) -> None:
    """Tell the user their command didn't run instead of eating it."""
    try:
        from .message_queue import emit_warning

        emit_warning(
            f"{text} couldn't run — the agent run just ended. Retype it at the prompt."
        )
    except Exception:
        logger.debug("failed to emit dropped-command warning", exc_info=True)


async def _drain_pending_commands(editor: RunningLineEditor) -> None:
    """Consume every queued slash command inside ONE pause window.

    Runs on the main loop. A global ``_draining`` guard collapses
    concurrent schedules — the active drain's while-loop picks up any
    command queued while it works.
    """
    global _draining
    with _lock:
        if _draining:
            return
        _draining = True
    try:
        first = editor.get_pending_command()
        if first is None:
            return
        await _run_paused_commands(editor, first)
    finally:
        with _lock:
            _draining = False


async def _run_paused_commands(editor: RunningLineEditor, first_cmd: str) -> None:
    """Pause → execute queued command(s) → resume. Exception-safe."""
    from .bus import get_message_bus
    from .commands import PauseAgentCommand, ResumeAgentCommand
    from .message_queue import emit_info, emit_warning
    from .pause_controller import get_pause_controller

    bus = get_message_bus()
    pc = get_pause_controller()
    bus.provide_response(PauseAgentCommand(reason="slash command"))
    try:
        # Pause is a flag, not a rendezvous: wait (briefly) for the agent
        # to actually park at its safe boundary before taking over the
        # terminal. Best-effort — between model calls the gate is never
        # reached, so proceed anyway on timeout. Poll asynchronously:
        # blocking the loop here would prevent the agent from ever
        # REACHING the pause gate (it runs on this same loop).
        await _await_parked(pc, _PARK_TIMEOUT_S)
        cmd: Optional[str] = first_cmd
        while cmd is not None:
            name = cmd[1:].split()[0].lower() if len(cmd) > 1 else ""
            reason = MID_RUN_DENYLIST.get(name)
            if reason is not None:
                emit_warning(
                    f"/{name} can't run while the agent is working "
                    f"({reason}) — finish the run first."
                )
            elif not pc.is_paused():
                # Only event_stream_handler's wait_if_paused timeout (or a
                # cancel path) resumes behind our back — the pause window
                # is gone, so running now would interleave with streaming.
                emit_warning(
                    f"⏸ pause expired before {cmd} could run — skipped; "
                    "run it again when the agent finishes."
                )
            else:
                emit_info(f"⏸ agent paused — running {cmd}")
                with suspended_run_ui():
                    result = _execute_command(cmd)
                _handle_command_result(cmd, result)
            cmd = editor.get_pending_command()
    finally:
        # ALWAYS resume + let the transcript know, even on exceptions.
        try:
            bus.provide_response(ResumeAgentCommand())
        except Exception:
            pc.resume()
        emit_info("▶ resumed")


async def _await_parked(pc, timeout: float) -> bool:
    """Async-poll until a waiter parks in wait_if_paused (or timeout)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not pc.is_parked():
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.05)
    return True


def _execute_command(cmd: str):
    """Run ``handle_command`` in idle-REPL context (main thread, in-loop).

    Never raises — command failures must not break the resume path.
    """
    from .message_queue import emit_error

    try:
        from code_puppy.command_line.command_handler import handle_command

        return handle_command(cmd)
    except Exception as e:
        try:
            emit_error(f"Command error: {e}")
        except Exception:
            pass
        return True


def _handle_command_result(cmd: str, result) -> None:
    """Map ``handle_command`` return values to mid-run semantics.

    The idle REPL treats a returned string as "process this as user
    input" (e.g. markdown commands that expand to a prompt). Mid-run the
    equivalent is a queue-mode steer: it becomes a fresh user turn once
    the current ``agent.run()`` completes.
    """
    from .message_queue import emit_info, emit_warning
    from .pause_controller import get_pause_controller

    if not isinstance(result, str):
        return
    if result == "__AUTOSAVE_LOAD__":
        # Defense-in-depth: /autosave_load is denylisted, but a plugin
        # could return the sentinel too.
        emit_warning("That command needs the idle prompt — finish the run first.")
        return
    get_pause_controller().request_steer(result, mode="queue")
    emit_info(f"⏭ {cmd} expanded to a prompt — queued as the next turn.")


# TODO(deferred): invert this messaging→agents lazy import — have the
# key-listener register itself into a small registry owned by messaging
# instead of run_ui reaching across packages. (Flagged by review; not
# worth the churn mid-rewrite.)
def _set_feed_target(editor: Optional[RunningLineEditor]) -> None:
    """Install/clear the key-listener feed target (lazy import, no cycle)."""
    try:
        from code_puppy.agents._key_listeners import set_line_editor
    except ImportError:
        # No listener infrastructure (tests, exotic embeds): typing just
        # won't reach the editor; everything else still works.
        return
    set_line_editor(editor)


def _suspended_key_listener():
    """Resolve ``suspended_key_listener`` lazily (see module docstring)."""
    try:
        from code_puppy.agents._key_listeners import suspended_key_listener

        return suspended_key_listener
    except ImportError:  # pragma: no cover - import failure fallback
        from contextlib import nullcontext

        return nullcontext


__all__ = [
    "MID_RUN_DENYLIST",
    "clear_idle_buffer",
    "get_run_editor",
    "is_draining",
    "is_persistent",
    "is_run_active",
    "run_ui",
    "set_idle_prompt_prefix",
    "start_persistent_ui",
    "start_run_ui",
    "stop_persistent_ui",
    "stop_run_ui",
    "suspended_run_ui",
    "wait_for_idle_submission",
]
