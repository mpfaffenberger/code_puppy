import asyncio
import contextvars
import ctypes
import os
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from typing import Callable, List, Literal, Optional, Set

from pydantic import BaseModel
from pydantic_ai import RunContext
from rich.text import Text

from code_puppy.callbacks import on_run_shell_command_output
from code_puppy.config import get_command_timeout_seconds
from code_puppy.messaging import (  # Structured messaging types
    AgentReasoningMessage,
    ShellOutputMessage,
    ShellStartMessage,
    emit_error,
    emit_info,
    emit_shell_line,
    emit_warning,
    get_message_bus,
)
from code_puppy.tools.common import generate_group_id, get_user_approval_async
from code_puppy.tools.shell_backgrounding import (
    DivertLog,
    background_generation,
    close_divert_log_on_exit,
    request_background_all,
)
from code_puppy.tools.subagent_context import is_subagent

# Maximum line length for shell command output to prevent massive token usage
# This helps avoid exceeding model context limits when commands produce very long lines
MAX_LINE_LENGTH = 256


def _truncate_line(line: str) -> str:
    """Truncate a line to MAX_LINE_LENGTH if it exceeds the limit."""
    if len(line) > MAX_LINE_LENGTH:
        return line[:MAX_LINE_LENGTH] + "... [truncated]"
    return line


# Windows-specific: Check if pipe has data available without blocking
# This is needed because select() doesn't work on pipes on Windows
if sys.platform.startswith("win"):
    import msvcrt

    # Load kernel32 for PeekNamedPipe
    _kernel32 = ctypes.windll.kernel32

    def _win32_pipe_has_data(pipe) -> bool:
        """Check if a Windows pipe has data available without blocking.

        Uses PeekNamedPipe from kernel32.dll to check if there's data
        in the pipe buffer without actually reading it.

        Args:
            pipe: A file object with a fileno() method (e.g., process.stdout)

        Returns:
            True if data is available, False otherwise (including on error)
        """
        try:
            # Get the Windows handle from the file descriptor
            handle = msvcrt.get_osfhandle(pipe.fileno())

            # PeekNamedPipe parameters:
            # - hNamedPipe: handle to the pipe
            # - lpBuffer: buffer to receive data (NULL = don't read)
            # - nBufferSize: size of buffer (0 = don't read)
            # - lpBytesRead: receives bytes read (NULL)
            # - lpTotalBytesAvail: receives total bytes available
            # - lpBytesLeftThisMessage: receives bytes left (NULL)
            bytes_available = ctypes.c_ulong(0)

            result = _kernel32.PeekNamedPipe(
                handle,
                None,  # Don't read data
                0,  # Buffer size 0
                None,  # Don't care about bytes read
                ctypes.byref(bytes_available),  # Get bytes available
                None,  # Don't care about bytes left in message
            )

            if result:
                return bytes_available.value > 0
            return False
        except (ValueError, OSError, ctypes.ArgumentError):
            # Handle closed, invalid, or other errors
            return False
else:
    # POSIX stub - not used, but keeps the code clean
    def _win32_pipe_has_data(pipe) -> bool:
        return False


_AWAITING_USER_INPUT = threading.Event()

_CONFIRMATION_LOCK = threading.Lock()


# Track running shell processes so we can kill them on Ctrl-C from the UI
_RUNNING_PROCESSES: Set[subprocess.Popen] = set()
_RUNNING_PROCESSES_LOCK = threading.Lock()
_USER_KILLED_PROCESSES = set()

# Per-session process tracking via ContextVar
_session_running_processes: ContextVar[Optional[Set[subprocess.Popen]]] = ContextVar(
    "session_running_processes", default=None
)
_session_killed_processes: ContextVar[Optional[Set[int]]] = ContextVar(
    "session_killed_processes", default=None
)
_session_awaiting_input: ContextVar[Optional[threading.Event]] = ContextVar(
    "session_awaiting_input", default=None
)


def _get_running_processes() -> Set[subprocess.Popen]:
    """Get the running processes set for the current session context."""
    session_set = _session_running_processes.get(None)
    if session_set is not None:
        return session_set
    return _RUNNING_PROCESSES


def _get_killed_processes() -> Set[int]:
    """Get the killed processes set for the current session context."""
    session_set = _session_killed_processes.get(None)
    if session_set is not None:
        return session_set
    return _USER_KILLED_PROCESSES


def _get_awaiting_input_event() -> threading.Event:
    """Get the awaiting-input event for the current session context."""
    session_evt = _session_awaiting_input.get(None)
    if session_evt is not None:
        return session_evt
    return _AWAITING_USER_INPUT


def init_session_process_tracking() -> None:
    """Initialize per-session process tracking. Call at WS session start."""
    _session_running_processes.set(set())
    _session_killed_processes.set(set())
    _session_awaiting_input.set(threading.Event())
    _session_active_stop_events.set(set())
    _session_keyboard_refcount.set(0)
    _session_ctrl_x_stop_event.set(None)
    _session_ctrl_x_thread.set(None)


def cleanup_session_process_tracking() -> None:
    """Tear down per-session process tracking. Call at WS session end.

    Kills any still-running session processes, then clears the per-session
    process and killed-process sets to release any held Popen references.
    """
    # Kill any still-running session processes first
    session_procs = _session_running_processes.get(None)
    if session_procs is not None:
        for p in list(session_procs):
            try:
                if p.poll() is None:
                    _kill_process_group(p)
            except Exception:
                pass
        session_procs.clear()
    session_killed = _session_killed_processes.get(None)
    if session_killed is not None:
        session_killed.clear()
    session_stop = _session_active_stop_events.get(None)
    if session_stop is not None:
        for evt in session_stop:
            evt.set()  # Signal before discarding!
        session_stop.clear()
    # Clean up keyboard context
    session_ctrl_x = _session_ctrl_x_stop_event.get(None)
    if session_ctrl_x is not None:
        session_ctrl_x.set()  # Signal stop
    session_thread = _session_ctrl_x_thread.get(None)
    if session_thread is not None and session_thread.is_alive():
        try:
            session_thread.join(timeout=0.2)
        except Exception:
            pass
    _session_keyboard_refcount.set(None)
    _session_ctrl_x_stop_event.set(None)
    _session_ctrl_x_thread.set(None)
    # Reset to None so subsequent calls fall back to global
    _session_running_processes.set(None)
    _session_killed_processes.set(None)
    _session_awaiting_input.set(None)
    _session_active_stop_events.set(None)


# Global state for shell command keyboard handling
_SHELL_CTRL_X_STOP_EVENT: Optional[threading.Event] = None
_SHELL_CTRL_X_THREAD: Optional[threading.Thread] = None
_SHELL_CTRL_X_HANDLE = None  # KeyListenerHandle when WE spawned the listener
_ORIGINAL_SIGINT_HANDLER = None

# Bridge from the shell SIGINT handler back to the active agent run's cancel
# callback (``make_schedule_cancel``'s closure). Registered by the runtime at
# run start, cleared at run end. Lets a single Ctrl+C during a sub-agent swarm
# kill the shells AND cancel every sub-agent task + the main agent, instead of
# only killing the current batch of shells (which forced the user to mash
# Ctrl+C once per still-running sub-agent).
_AGENT_CANCEL_CB: Optional[Callable[..., None]] = None
# One-shot dedupe so mashing Ctrl+C during teardown doesn't reprint the banner
# or re-fire the cancel sweep N times. Reset when a new cancel cb registers.
_SIGINT_CANCEL_REQUESTED = False

# Reference-counted keyboard context - stays active while ANY command is running
_KEYBOARD_CONTEXT_REFCOUNT = 0
_KEYBOARD_CONTEXT_LOCK = threading.Lock()

# Per-session keyboard context refcount (ContextVar for WS session isolation)
_session_keyboard_refcount: ContextVar[Optional[int]] = ContextVar(
    "session_keyboard_refcount", default=None
)
_session_ctrl_x_stop_event: ContextVar[Optional[threading.Event]] = ContextVar(
    "session_ctrl_x_stop_event", default=None
)
_session_ctrl_x_thread: ContextVar[Optional[threading.Thread]] = ContextVar(
    "session_ctrl_x_thread", default=None
)

# Thread-safe registry of active stop events for concurrent shell commands
_ACTIVE_STOP_EVENTS: Set[threading.Event] = set()
_ACTIVE_STOP_EVENTS_LOCK = threading.Lock()

# Per-session stop events (ContextVar for session isolation)
_session_active_stop_events: ContextVar[Optional[Set[threading.Event]]] = ContextVar(
    "session_active_stop_events", default=None
)


def _get_keyboard_refcount() -> int:
    """Get keyboard context refcount for the current session."""
    session_val = _session_keyboard_refcount.get(None)
    if session_val is not None:
        return session_val
    return _KEYBOARD_CONTEXT_REFCOUNT


def _set_keyboard_refcount(value: int) -> None:
    """Set keyboard context refcount for the current session."""
    if _session_keyboard_refcount.get(None) is not None:
        _session_keyboard_refcount.set(value)
    else:
        global _KEYBOARD_CONTEXT_REFCOUNT
        _KEYBOARD_CONTEXT_REFCOUNT = value


def _get_ctrl_x_stop_event() -> Optional[threading.Event]:
    """Get Ctrl+X stop event for the current session."""
    session_evt = _session_ctrl_x_stop_event.get(None)
    if session_evt is not None:
        return session_evt
    return _SHELL_CTRL_X_STOP_EVENT


def _get_ctrl_x_thread() -> Optional[threading.Thread]:
    """Get Ctrl+X thread for the current session."""
    session_thread = _session_ctrl_x_thread.get(None)
    if session_thread is not None:
        return session_thread
    return _SHELL_CTRL_X_THREAD


def _get_active_stop_events() -> Set[threading.Event]:
    """Get the active stop events set for the current session context."""
    session_set = _session_active_stop_events.get(None)
    if session_set is not None:
        return session_set
    return _ACTIVE_STOP_EVENTS


@contextmanager
def _guarded_set(collection, global_ref, lock):
    """Acquire *lock* only when *collection* is the shared global *global_ref*.

    Per-session sets (ContextVar-backed) are single-writer within their
    asyncio task context and don't need locking.
    """
    if collection is global_ref:
        with lock:
            yield collection
    else:
        yield collection


# Mid-flight backgrounding (Ctrl+X Ctrl+B) machinery lives in
# ``shell_backgrounding`` (600-line cap); re-exported here because the
# chord handler and the streaming pumps are the consumers.


# Thread pool for running blocking shell commands without blocking the event loop
# This allows multiple sub-agents to run shell commands in parallel
_SHELL_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="shell_cmd_")


def _register_process(proc: subprocess.Popen) -> None:
    procs = _get_running_processes()
    with _guarded_set(procs, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
        procs.add(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    procs = _get_running_processes()
    with _guarded_set(procs, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
        procs.discard(proc)


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Attempt to aggressively terminate a process and its group.

    Cross-platform best-effort. On POSIX, uses process groups. On Windows, tries taskkill with /T flag for tree kill.
    """
    try:
        if sys.platform.startswith("win"):
            # On Windows, use taskkill to kill the process tree
            # /F = force, /T = kill tree (children), /PID = process ID
            try:
                import subprocess as sp

                # Try taskkill first - more reliable on Windows
                sp.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                time.sleep(0.3)
            except Exception:
                # Fallback to Python's built-in methods
                pass

            # Double-check it's dead, if not use proc.kill()
            if proc.poll() is None:
                try:
                    proc.kill()
                    time.sleep(0.3)
                except Exception:
                    pass
            return

        # POSIX
        pid = proc.pid
        try:
            pgid = os.getpgid(pid)
            # SAFETY: never signal our OWN process group. Production spawns
            # every child with start_new_session=True/os.setsid so it lands
            # in its own group -- but a child spawned WITHOUT that isolation
            # inherits our group, and killpg(our_pgid, SIGKILL) would take
            # out this process (pytest, or the CI runner's step shell) too.
            # That footgun is exactly what canceled CI. Fall back to a
            # single-process kill when the group isn't isolated.
            if pgid == os.getpgrp():
                raise ProcessLookupError("refusing to killpg our own process group")
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(1.0)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGINT)
                time.sleep(0.6)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
                time.sleep(0.5)
        except (OSError, ProcessLookupError):
            # Fall back to direct kill of the process
            try:
                if proc.poll() is None:
                    proc.kill()
            except (OSError, ProcessLookupError):
                pass

        if proc.poll() is None:
            # Last ditch attempt; may be unkillable zombie
            try:
                for _ in range(3):
                    os.kill(proc.pid, signal.SIGKILL)
                    time.sleep(0.2)
                    if proc.poll() is not None:
                        break
            except Exception:
                pass
    except Exception as e:
        emit_error(f"Kill process error: {e}")


def kill_all_running_shell_processes() -> int:
    """Kill all currently tracked running shell processes and stop reader threads.

    Returns the number of processes signaled.
    """
    # Signal all active reader threads to stop
    active_stop = _get_active_stop_events()
    with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
        for evt in active_stop:
            evt.set()

    procs: list[subprocess.Popen]
    running = _get_running_processes()
    killed = _get_killed_processes()
    with _guarded_set(running, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
        procs = list(running)
    count = 0
    for p in procs:
        try:
            # Close pipes first to unblock readline()
            try:
                if p.stdout and not p.stdout.closed:
                    p.stdout.close()
                if p.stderr and not p.stderr.closed:
                    p.stderr.close()
                if p.stdin and not p.stdin.closed:
                    p.stdin.close()
            except (OSError, ValueError):
                pass

            if p.poll() is None:
                _kill_process_group(p)
                count += 1
                killed.add(p.pid)
        finally:
            _unregister_process(p)
    return count


def get_running_shell_process_count() -> int:
    """Return the number of currently-active shell processes being tracked."""
    running = _get_running_processes()
    with _guarded_set(running, _RUNNING_PROCESSES, _RUNNING_PROCESSES_LOCK):
        alive = 0
        stale: Set[subprocess.Popen] = set()
        for proc in running:
            if proc.poll() is None:
                alive += 1
            else:
                stale.add(proc)
        for proc in stale:
            running.discard(proc)
    return alive


# Function to check if user input is awaited
def is_awaiting_user_input():
    """Check if command_runner is waiting for user input."""
    return _get_awaiting_input_event().is_set()


# Function to set user input flag
def set_awaiting_user_input(awaiting=True):
    """Set the flag indicating if user input is awaited.

    NOTE: this only toggles the flag. Components that actually take over
    the terminal for input (approval prompts, ask_user_question TUI) are
    responsible for wrapping themselves in
    ``code_puppy.messaging.run_ui.suspended_run_ui()``.

    This is also the single authoritative source for "the agent is parked on
    a human": it fires the ``awaiting_user_input`` callback so observers (the
    herdr state reporter, notifiers, status bars) learn about *every*
    interactive wait -- shell-command approval, file approval,
    ``ask_user_question``, and every menu/picker -- from one place, rather
    than each prompt having to announce itself (or an external watcher having
    to guess from the screen).
    """
    if awaiting:
        _get_awaiting_input_event().set()
    else:
        _get_awaiting_input_event().clear()

    # Best-effort notification; never let an observer disturb the prompt path.
    try:
        from code_puppy.callbacks import on_awaiting_user_input

        on_awaiting_user_input(bool(awaiting))
    except Exception:
        pass


class ShellCommandOutput(BaseModel):
    success: bool
    command: str | None
    error: str | None = ""
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    execution_time: float | None
    timeout: bool | None = False
    user_interrupted: bool | None = False
    user_feedback: str | None = None  # User feedback when command is rejected
    background: bool = False  # True if command was run in background mode
    log_file: str | None = None  # Path to temp log file for background commands
    pid: int | None = None  # Process ID for background commands


class ShellSafetyAssessment(BaseModel):
    """Assessment of shell command safety risks.

    This model represents the structured output from the shell safety checker agent.
    It provides a risk level classification and reasoning for that assessment.

    Attributes:
        risk: Risk level classification. Can be one of:
              'none' (completely safe), 'low' (minimal risk), 'medium' (moderate risk),
              'high' (significant risk), 'critical' (severe/destructive risk).
        reasoning: Brief explanation (max 1-2 sentences) of why this risk level
                   was assigned. Should be concise and actionable.
        is_fallback: Whether this assessment is a fallback due to parsing failure.
                     Fallback assessments are not cached to allow retry with fresh LLM responses.
    """

    risk: Literal["none", "low", "medium", "high", "critical"]
    reasoning: str
    is_fallback: bool = False


def _spawn_ctrl_x_key_listener(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
) -> Optional[threading.Thread]:
    """Spawn the unified key listener with a Ctrl+X handler.

    Thin shim over ``_key_listeners.acquire_listener`` so there is exactly
    ONE stdin-listener implementation in the codebase. Two cbreak readers on
    the same stdin is how CPR replies got eaten ("your terminal doesn't
    support cursor position requests") and keystrokes went missing.

    ``acquire_listener`` makes the reuse-or-spawn decision atomic AND
    registers a spawned listener as the active handle — previously the
    shell listener was invisible to ``get_active_handle()``, so
    ``suspended_key_listener()`` no-op'd around it and other components
    could spawn a second reader on the same stdin.

    Returns the spawned listener's thread, or ``None`` when an existing
    listener already owns stdin (shell actions ride the Ctrl+X chords
    registered in ``messaging.chords``) or stdin isn't a TTY.
    """
    global _SHELL_CTRL_X_HANDLE
    from code_puppy.agents import _key_listeners

    handle, spawned = _key_listeners.acquire_listener(stop_event, on_escape=on_escape)
    if not spawned or handle is None:
        return None
    _SHELL_CTRL_X_HANDLE = handle
    return handle.thread


@contextmanager
def _shell_command_keyboard_context():
    """Context manager to handle keyboard interrupts during shell command execution.

    This context manager:
    1. Disables the agent's Ctrl-C handler (so it doesn't cancel the agent)
    2. Routes Ctrl-X to kill the running shell process
    3. Restores the original Ctrl-C handler when done

    Delegates to the shared start/stop helpers so this path and the
    refcounted ``_acquire_keyboard_context`` path can never drift apart
    (they used to be copy-pasta of each other).
    """
    _start_keyboard_listener()
    try:
        yield
    finally:
        _stop_keyboard_listener()


def _handle_ctrl_x_press() -> None:
    """Chord Ctrl+X Ctrl+X (bare Ctrl+X headless): kill all shells."""
    emit_warning("\nCtrl+X -- interrupting all shell commands...")
    kill_all_running_shell_processes()


def _handle_ctrl_b_press() -> None:
    """Chord Ctrl+X Ctrl+B: background all running shell commands.

    Every streaming pump detaches: the tool call returns a
    ``background=True`` result immediately while the process keeps
    running with its remaining output diverted to a log file.
    """
    emit_warning("\nCtrl+X Ctrl+B -- backgrounding all shell commands...")
    request_background_all()


def _register_shell_chords() -> None:
    """Bind the shell chords for as long as commands are in flight.

    Registered on the first command, unregistered after the last — the
    armed-chord hint only advertises them when there's something to
    act on.
    """
    try:
        from code_puppy.messaging.chords import register_chord

        register_chord("\x18", _handle_ctrl_x_press, "Ctrl+X kill shells")
        register_chord("\x02", _handle_ctrl_b_press, "Ctrl+B background shells")
    except ImportError:
        pass  # exotic embeds without the messaging stack


def _unregister_shell_chords() -> None:
    try:
        from code_puppy.messaging.chords import unregister_chord

        unregister_chord("\x18")
        unregister_chord("\x02")
    except ImportError:
        pass


def _tear_down_live_panels() -> None:
    """Clear the sub-agent panel rows on swarm cancel.

    The panel now lives on the bottom bar's reserved rows (Phase 4).
    On Ctrl+C swarm-cancel the plugin's event-driven repaints stop
    arriving (tasks are being killed), so stale rows would linger — wipe
    them here. Collapsing the panel also hands the rows back to the
    scroll region so the cancel banner has maximum space.

    Never raises — called from the SIGINT handler.
    """
    try:
        from code_puppy.messaging.bottom_bar import get_bottom_bar

        get_bottom_bar().set_panel_lines([])
    except Exception:
        pass


def _shell_sigint_handler(_sig, _frame):
    """SIGINT during shell execution: stop the swarm responsively.

    Ctrl+C is a pure keybinding — with a raw-mode key listener owning
    stdin, ^C arrives as ``\\x03`` and cancels via the key-listener path
    (``make_schedule_cancel``) instead of here. This handler is the
    out-of-band fallback: ``kill -INT``, piped stdin (no TTY listener),
    or ^C landing in a cooked-mode gap between raw readers.

    ORDER MATTERS, and it's the opposite of what you'd naively expect:

    1. **Hide the panel** (``_tear_down_live_panels``) -- instant, non-blocking.
    2. **Emit the banner** -- instant; the user gets immediate feedback.
    3. **Kill the shells** (``kill_all_running_shell_processes``) -- SLOW and
       BLOCKING. ``_kill_process_group`` sleeps up to ~2.1s *per process*
       (SIGTERM->SIGINT->SIGKILL escalation), so a deep swarm with N nested
       sub-agents each holding a ``sleep`` shell can block the main thread for
       N x ~2s. If we killed first (the old order), the spinner's Rich Live
       kept repainting the sub-agent panel for that entire window and the
       teardown/banner only landed *after* every shell died -- which is
       precisely the "panel stays up until all the shells finally stop" bug.
    4. **Cancel the swarm** (``_AGENT_CANCEL_CB(force=True)``). Shells are
       already dead by here, so the anti-orphan reason for force-cancel holds.

    A one-shot ``_SIGINT_CANCEL_REQUESTED`` flag dedupes the banner + sweep
    so mashing Ctrl+C during teardown doesn't spam either.
    """
    global _SIGINT_CANCEL_REQUESTED

    if _SIGINT_CANCEL_REQUESTED:
        # Already tearing this run down; swallow extra presses silently.
        # Keep the panel hidden in case a late frame tried to bring it back.
        _tear_down_live_panels()
        kill_all_running_shell_processes()
        return

    if _AGENT_CANCEL_CB is not None:
        _SIGINT_CANCEL_REQUESTED = True
        # 1+2: hide the panel and announce the cancel BEFORE the slow kill,
        # so the UI responds instantly instead of after every shell dies.
        _tear_down_live_panels()
        emit_warning(
            "\nCtrl-C detected! Stopping the agent (shells + all sub-agents)..."
        )
        # 3: the slow, blocking part -- panel is already gone, banner is shown.
        kill_all_running_shell_processes()
        try:
            # 4: force=True -- we just killed the shells, so the agent-cancel
            # guard's anti-orphan reason no longer applies.
            _AGENT_CANCEL_CB(force=True)
        except Exception:
            # A cancel-callback failure must never crash the signal handler.
            pass
    else:
        # Headless / tool-only invocation with no active agent run to cancel.
        _tear_down_live_panels()
        emit_warning("\nCtrl-C detected! Interrupting all shell commands...")
        kill_all_running_shell_processes()


def register_agent_cancel(cb: Optional[Callable[..., None]]) -> None:
    """Publish the active agent run's cancel callback for the SIGINT handler.

    Called by the runtime at run start so a Ctrl+C arriving while shells are
    running can collapse the whole agent/sub-agent tree, not just the shells.
    Resets the one-shot dedupe flag so each fresh run can be cancelled once.
    """
    global _AGENT_CANCEL_CB, _SIGINT_CANCEL_REQUESTED
    _AGENT_CANCEL_CB = cb
    _SIGINT_CANCEL_REQUESTED = False


def clear_agent_cancel() -> None:
    """Drop the registered cancel callback at run end so it can't outlive its task."""
    global _AGENT_CANCEL_CB, _SIGINT_CANCEL_REQUESTED
    _AGENT_CANCEL_CB = None
    _SIGINT_CANCEL_REQUESTED = False


def _start_keyboard_listener() -> None:
    """Register the shell chords and install the SIGINT handler.

    Called when the first shell command starts.

    Interactive sessions get Ctrl+X CHORDS via ``messaging.chords``
    (Ctrl+X Ctrl+X kill, Ctrl+X Ctrl+B background); the listener/editor
    already own stdin — spawning a second cbreak reader is how CPR
    replies got eaten and the terminal ended up wedged. Only headless
    invocations (no editor, no listener) spawn their own listener,
    where a bare Ctrl+X keeps the historical kill-everything meaning.
    """
    global _SHELL_CTRL_X_STOP_EVENT, _SHELL_CTRL_X_THREAD, _ORIGINAL_SIGINT_HANDLER

    _register_shell_chords()
    # Reuse-or-spawn is atomic inside the shim: an agent-run/persistent
    # listener is reused (the chords above own Ctrl+X dispatch); only
    # headless / tool-only invocations actually spawn.
    _SHELL_CTRL_X_STOP_EVENT = threading.Event()
    _SHELL_CTRL_X_THREAD = _spawn_ctrl_x_key_listener(
        _SHELL_CTRL_X_STOP_EVENT,
        _handle_ctrl_x_press,
    )

    # Replace SIGINT handler temporarily
    try:
        _ORIGINAL_SIGINT_HANDLER = signal.signal(signal.SIGINT, _shell_sigint_handler)
    except (ValueError, OSError):
        # Can't set signal handler (maybe not main thread?)
        _ORIGINAL_SIGINT_HANDLER = None


def _stop_keyboard_listener() -> None:
    """Stop routing Ctrl-X and restore the SIGINT handler.

    Called when the last shell command finishes.
    """
    global \
        _SHELL_CTRL_X_STOP_EVENT, \
        _SHELL_CTRL_X_THREAD, \
        _SHELL_CTRL_X_HANDLE, \
        _ORIGINAL_SIGINT_HANDLER

    from code_puppy.agents import _key_listeners

    _unregister_shell_chords()

    # Clean up: stop our own listener (only spawned in headless mode)
    if _SHELL_CTRL_X_STOP_EVENT:
        _SHELL_CTRL_X_STOP_EVENT.set()

    # Deregister BEFORE joining so nobody tries to suspend a dying listener.
    if (
        _SHELL_CTRL_X_HANDLE is not None
        and _key_listeners.get_active_handle() is _SHELL_CTRL_X_HANDLE
    ):
        _key_listeners.set_active_handle(None)

    if _SHELL_CTRL_X_THREAD and _SHELL_CTRL_X_THREAD.is_alive():
        try:
            _SHELL_CTRL_X_THREAD.join(timeout=0.2)
        except Exception:
            pass

    # Restore original SIGINT handler
    if _ORIGINAL_SIGINT_HANDLER is not None:
        try:
            signal.signal(signal.SIGINT, _ORIGINAL_SIGINT_HANDLER)
        except (ValueError, OSError):
            pass

    # Clean up global state
    _SHELL_CTRL_X_STOP_EVENT = None
    _SHELL_CTRL_X_THREAD = None
    _SHELL_CTRL_X_HANDLE = None
    _ORIGINAL_SIGINT_HANDLER = None


def _acquire_keyboard_context() -> None:
    """Acquire the shared keyboard context (reference counted).

    Starts the Ctrl-X listener when the first command starts.
    Safe to call from any thread.
    """
    global _KEYBOARD_CONTEXT_REFCOUNT

    should_start = False
    with _KEYBOARD_CONTEXT_LOCK:
        _KEYBOARD_CONTEXT_REFCOUNT += 1
        if _KEYBOARD_CONTEXT_REFCOUNT == 1:
            should_start = True

    # Start listener OUTSIDE the lock to avoid blocking other commands
    if should_start:
        _start_keyboard_listener()


def _release_keyboard_context() -> None:
    """Release the shared keyboard context (reference counted).

    Stops the Ctrl-X listener when the last command finishes.
    Safe to call from any thread.
    """
    global _KEYBOARD_CONTEXT_REFCOUNT

    should_stop = False
    with _KEYBOARD_CONTEXT_LOCK:
        _KEYBOARD_CONTEXT_REFCOUNT -= 1
        if _KEYBOARD_CONTEXT_REFCOUNT <= 0:
            _KEYBOARD_CONTEXT_REFCOUNT = 0  # Safety clamp
            should_stop = True

    # Stop listener OUTSIDE the lock to avoid blocking other commands
    if should_stop:
        _stop_keyboard_listener()


def run_shell_command_streaming(
    process: subprocess.Popen,
    timeout: int = 60,
    command: str = "",
    group_id: str = None,
    silent: bool = False,
):
    stop_event = threading.Event()
    active_stop = _get_active_stop_events()
    with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
        active_stop.add(stop_event)

    start_time = time.time()
    last_output_time = [start_time]

    # Foreground duration limit. Reaching it detaches rather than killing;
    # inactivity remains the guard for genuinely wedged commands.
    foreground_limit_seconds = get_command_timeout_seconds()

    stdout_lines = []
    stderr_lines = []

    stdout_thread = None
    stderr_thread = None

    # Mid-flight backgrounding (Ctrl+X Ctrl+B): once the divert log is
    # set, the reader threads pump every further line into it instead of
    # the transcript -- keeping the pipes drained so the child can't
    # block on a full pipe buffer after this function returns.
    bg_generation_at_start = background_generation()
    divert_log: list = [None]

    def _sink(line, lines_list, stream):
        log = divert_log[0]
        if log is not None:
            log.write_line(stream, line)
            return
        lines_list.append(line)
        if not silent:
            emit_shell_line(line, stream=stream)

    def read_stdout():
        try:
            fd = process.stdout.fileno()
        except (ValueError, OSError):
            return

        try:
            while True:
                # Check stop event first
                if stop_event.is_set():
                    break

                # Use select to check if data is available (with timeout)
                if sys.platform.startswith("win"):
                    # Windows doesn't support select on pipes
                    # Use PeekNamedPipe via _win32_pipe_has_data() to check
                    # if data is available without blocking
                    try:
                        if _win32_pipe_has_data(process.stdout):
                            line = process.stdout.readline()
                            if not line:  # EOF
                                break
                            line = line.rstrip("\r\n")
                            line = _truncate_line(line)
                            _sink(line, stdout_lines, "stdout")
                            last_output_time[0] = time.time()
                        else:
                            # No data available, check if process has exited
                            if process.poll() is not None:
                                # Process exited, do one final drain
                                try:
                                    remaining = process.stdout.read()
                                    if remaining:
                                        for line in remaining.split("\n"):
                                            # Normalize trailing CR/LF to match
                                            # the main readline path; otherwise
                                            # Windows CRLF leaves a stray \r that
                                            # can re-trigger the renderer's redraw
                                            # bypass.
                                            line = line.rstrip("\r\n")
                                            line = _truncate_line(line)
                                            _sink(line, stdout_lines, "stdout")
                                except (ValueError, OSError):
                                    pass
                                break
                            # Sleep briefly to avoid busy-waiting (100ms like POSIX)
                            time.sleep(0.1)
                    except (ValueError, OSError):
                        break
                else:
                    # POSIX: use select with timeout
                    try:
                        ready, _, _ = select.select([fd], [], [], 0.1)  # 100ms timeout
                    except (ValueError, OSError, select.error):
                        break

                    if ready:
                        line = process.stdout.readline()
                        if not line:  # EOF
                            break
                        line = line.rstrip("\r\n")
                        line = _truncate_line(line)
                        _sink(line, stdout_lines, "stdout")
                        last_output_time[0] = time.time()
                    # If not ready, loop continues and checks stop event again
        except (ValueError, OSError):
            pass
        except Exception:
            pass

    def read_stderr():
        try:
            fd = process.stderr.fileno()
        except (ValueError, OSError):
            return

        try:
            while True:
                # Check stop event first
                if stop_event.is_set():
                    break

                if sys.platform.startswith("win"):
                    # Windows doesn't support select on pipes
                    # Use PeekNamedPipe via _win32_pipe_has_data() to check
                    # if data is available without blocking
                    try:
                        if _win32_pipe_has_data(process.stderr):
                            line = process.stderr.readline()
                            if not line:  # EOF
                                break
                            line = line.rstrip("\r\n")
                            line = _truncate_line(line)
                            _sink(line, stderr_lines, "stderr")
                            last_output_time[0] = time.time()
                        else:
                            # No data available, check if process has exited
                            if process.poll() is not None:
                                # Process exited, do one final drain
                                try:
                                    remaining = process.stderr.read()
                                    if remaining:
                                        for line in remaining.split("\n"):
                                            # Normalize trailing CR/LF to match
                                            # the main readline path; otherwise
                                            # Windows CRLF leaves a stray \r that
                                            # can re-trigger the renderer's redraw
                                            # bypass.
                                            line = line.rstrip("\r\n")
                                            line = _truncate_line(line)
                                            _sink(line, stderr_lines, "stderr")
                                except (ValueError, OSError):
                                    pass
                                break
                            # Sleep briefly to avoid busy-waiting (100ms like POSIX)
                            time.sleep(0.1)
                    except (ValueError, OSError):
                        break
                else:
                    try:
                        ready, _, _ = select.select([fd], [], [], 0.1)
                    except (ValueError, OSError, select.error):
                        break

                    if ready:
                        line = process.stderr.readline()
                        if not line:  # EOF
                            break
                        line = line.rstrip("\r\n")
                        line = _truncate_line(line)
                        _sink(line, stderr_lines, "stderr")
                        last_output_time[0] = time.time()
        except (ValueError, OSError):
            pass
        except Exception:
            pass

    def cleanup_process_and_threads(timeout_type: str = "unknown"):
        nonlocal stdout_thread, stderr_thread

        def nuclear_kill(proc):
            _kill_process_group(proc)

        try:
            # Signal reader threads to stop first
            stop_event.set()

            if process.poll() is None:
                nuclear_kill(process)

            try:
                if process.stdout and not process.stdout.closed:
                    process.stdout.close()
                if process.stderr and not process.stderr.closed:
                    process.stderr.close()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            except (OSError, ValueError):
                pass

            # Unregister once we're done cleaning up
            _unregister_process(process)

            if stdout_thread and stdout_thread.is_alive():
                stdout_thread.join(timeout=3)
                if stdout_thread.is_alive() and not silent:
                    emit_warning(
                        f"stdout reader thread failed to terminate after {timeout_type} timeout",
                        message_group=group_id,
                    )

            if stderr_thread and stderr_thread.is_alive():
                stderr_thread.join(timeout=3)
                if stderr_thread.is_alive() and not silent:
                    emit_warning(
                        f"stderr reader thread failed to terminate after {timeout_type} timeout",
                        message_group=group_id,
                    )

        except Exception as e:
            if not silent:
                emit_warning(
                    f"Error during process cleanup: {e}", message_group=group_id
                )

        execution_time = time.time() - start_time
        return ShellCommandOutput(
            **{
                "success": False,
                "command": command,
                "stdout": "\n".join(stdout_lines[-256:]),
                "stderr": "\n".join(stderr_lines[-256:]),
                "exit_code": -9,
                "execution_time": execution_time,
                "timeout": True,
                "error": f"Command timed out after {timeout} seconds",
            }
        )

    def detach_to_background(*, automatic: bool = False):
        """Stop foreground streaming while keeping the process running.

        The reader threads stay alive and divert every further line into
        a log file (pipes keep draining -- a full pipe buffer would
        block the child). The process leaves the kill-all registry: it's
        a background job now, not a running shell. A daemon janitor
        appends the exit footer and closes the log when it finishes.
        """
        log = DivertLog(command)
        divert_log[0] = log
        _unregister_process(process)
        with _ACTIVE_STOP_EVENTS_LOCK:
            _ACTIVE_STOP_EVENTS.discard(stop_event)
        threading.Thread(
            target=close_divert_log_on_exit, args=(process, log), daemon=True
        ).start()
        execution_time = time.time() - start_time
        cause = (
            f"Automatically backgrounded after {foreground_limit_seconds}s"
            if automatic
            else "The user backgrounded this command"
        )
        if not silent:
            emit_warning(
                f"{cause} (PID {process.pid}) -- output continues in {log.path}"
            )
        return ShellCommandOutput(
            success=True,
            command=command,
            stdout="\n".join(stdout_lines[-256:]),
            stderr="\n".join(stderr_lines[-256:]),
            exit_code=None,
            execution_time=execution_time,
            timeout=False,
            background=True,
            log_file=log.path,
            pid=process.pid,
            user_feedback=(
                f"{cause} while the command was still running. It has NOT"
                " finished: stdout/stderr above are partial, exit_code is"
                f" unknown, and the process (PID {process.pid}) keeps running"
                f" with further output appended to {log.path} (an exit-code"
                " footer is written when it finishes). Do NOT wait, sleep,"
                " poll, or re-run the command. Move on immediately; only read"
                " that log later if a subsequent task genuinely needs the"
                " result."
            ),
        )

    try:
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        while process.poll() is None:
            current_time = time.time()

            if background_generation() != bg_generation_at_start:
                return detach_to_background()

            if current_time - start_time > foreground_limit_seconds:
                return detach_to_background(automatic=True)

            if current_time - last_output_time[0] > timeout:
                if not silent:
                    emit_error(
                        "Process killed: inactivity timeout reached",
                        message_group=group_id,
                    )
                return cleanup_process_and_threads("inactivity")

            time.sleep(0.1)

        if stdout_thread:
            stdout_thread.join(timeout=5)
        if stderr_thread:
            stderr_thread.join(timeout=5)

        exit_code = process.returncode
        execution_time = time.time() - start_time

        try:
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
            if process.stderr and not process.stderr.closed:
                process.stderr.close()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except (OSError, ValueError):
            pass

        _unregister_process(process)

        # Apply line length limits to stdout/stderr before returning
        truncated_stdout = stdout_lines[-256:]
        truncated_stderr = stderr_lines[-256:]

        # Emit structured ShellOutputMessage for the UI (skip for silent sub-agents)
        if not silent:
            shell_output_msg = ShellOutputMessage(
                command=command,
                stdout="\n".join(truncated_stdout),
                stderr="\n".join(truncated_stderr),
                exit_code=exit_code,
                duration_seconds=execution_time,
            )
            get_message_bus().emit(shell_output_msg)

        active_stop = _get_active_stop_events()
        with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
            active_stop.discard(stop_event)

        if exit_code != 0:
            time.sleep(1)
            return ShellCommandOutput(
                success=False,
                command=command,
                error="""The process didn't exit cleanly! If the user_interrupted flag is true,
                please stop all execution and ask the user for clarification!""",
                stdout="\n".join(truncated_stdout),
                stderr="\n".join(truncated_stderr),
                exit_code=exit_code,
                execution_time=execution_time,
                timeout=False,
                user_interrupted=process.pid in _get_killed_processes(),
            )

        return ShellCommandOutput(
            success=True,
            command=command,
            stdout="\n".join(truncated_stdout),
            stderr="\n".join(truncated_stderr),
            exit_code=exit_code,
            execution_time=execution_time,
            timeout=False,
        )

    except Exception as e:
        active_stop = _get_active_stop_events()
        with _guarded_set(active_stop, _ACTIVE_STOP_EVENTS, _ACTIVE_STOP_EVENTS_LOCK):
            active_stop.discard(stop_event)
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error during streaming execution: {str(e)}",
            stdout="\n".join(stdout_lines[-256:]),
            stderr="\n".join(stderr_lines[-256:]),
            exit_code=-1,
            timeout=False,
        )


async def run_shell_command(
    context: RunContext,
    command: str,
    cwd: str = None,
    timeout: int = 60,
    background: bool = False,
) -> ShellCommandOutput:
    # Resolve CWD from the session ContextVar when not explicitly provided.
    # This supports concurrent WebSocket sessions where each session has its own CWD
    # without relying on the process-global os.chdir().
    # Returns None for CLI sessions (subprocess inherits process CWD as normal).
    if cwd is None:
        from code_puppy.api.session_cwd import get_session_working_directory

        cwd = get_session_working_directory()

    # Generate unique group_id for this command execution
    group_id = generate_group_id("shell_command", command)

    # Invoke safety check callbacks (only active in yolo_mode)
    # This allows plugins to intercept and assess commands before execution
    from code_puppy.callbacks import on_run_shell_command

    callback_results = await on_run_shell_command(context, command, cwd, timeout)

    # Check if any callback blocked the command
    # Callbacks can return None (allow) or a dict with blocked=True (reject)
    for result in callback_results:
        if result and isinstance(result, dict) and result.get("blocked"):
            return ShellCommandOutput(
                success=False,
                command=command,
                error=result.get("error_message", "Command blocked by safety check"),
                user_feedback=result.get("reasoning", ""),
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=None,
            )

    # Apply any command rewrites requested by callbacks.
    # A callback can return {"rewrite": "<new command>"} to transparently
    # transform the command before execution (e.g. inject a git trailer,
    # redact a secret, prepend a corporate proxy). Rewrites are applied in
    # callback registration order; each one sees whatever the previous ones
    # produced. A visible info line surfaces the change so users always know
    # what actually ran -- rewriting must never be sneaky.
    for result in callback_results:
        if result and isinstance(result, dict) and "rewrite" in result:
            new_command = result["rewrite"]
            if not isinstance(new_command, str) or not new_command.strip():
                continue  # ignore empty / non-string rewrites defensively
            if new_command != command:
                reason = result.get("rewrite_reason", "plugin")
                emit_info(f"[dim]\U0001f527 command rewritten by {reason}[/dim]")
                command = new_command

    # Handle background execution - runs command detached and returns immediately
    # This happens BEFORE user confirmation since we don't wait for the command
    if background:
        # Create temp log file for output
        log_file = tempfile.NamedTemporaryFile(
            mode="w",
            prefix="shell_bg_",
            suffix=".log",
            delete=False,  # Keep file so agent can read it later
        )
        log_file_path = log_file.name

        try:
            # Platform-specific process detachment. CREATE_NO_WINDOW:
            # own hidden console so the background tree can't stomp OUR
            # console input mode (see _run_command_sync docstring).
            if sys.platform.startswith("win"):
                creationflags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                )
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=cwd,
                    creationflags=creationflags,
                )
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=cwd,
                    start_new_session=True,  # Fully detach on POSIX
                )

            log_file.close()  # Close our handle, process keeps writing

            # Emit UI messages so user sees what happened
            bus = get_message_bus()
            bus.emit(
                ShellStartMessage(
                    command=command,
                    cwd=cwd,
                    timeout=0,  # No timeout for background processes
                    background=True,
                )
            )

            # Emit info about background execution
            emit_info(
                f"Background process started (PID: {process.pid}) - no timeout, runs until complete"
            )
            emit_info(f"Output logging to: {log_file.name}")

            # Return immediately - don't wait, don't block
            return ShellCommandOutput(
                success=True,
                command=command,
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=0.0,
                background=True,
                log_file=log_file.name,
                pid=process.pid,
            )
        except Exception as e:
            try:
                log_file.close()
            except Exception:
                pass
            # Clean up the temp file on error since no process will write to it
            try:
                os.unlink(log_file_path)
            except OSError:
                pass
            # Emit error message so user sees what happened
            emit_error(f"Failed to start background process: {e}")
            return ShellCommandOutput(
                success=False,
                command=command,
                error=f"Failed to start background process: {e}",
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=None,
                background=True,
            )

    # Rest of the existing function continues...
    if not command or not command.strip():
        emit_error("Command cannot be empty", message_group=group_id)
        return ShellCommandOutput(
            **{"success": False, "error": "Command cannot be empty"}
        )

    from code_puppy.config import get_yolo_mode

    yolo_mode = get_yolo_mode()

    # Check if we're running as a sub-agent (skip confirmation and run silently)
    running_as_subagent = is_subagent()

    # Check if WebSocket mode is active (permission handled via WebSocket callbacks)
    websocket_mode_active = False
    try:
        from code_puppy.api.permission_plugin import get_websocket_context

        websocket_mode_active = get_websocket_context() is not None
    except (ImportError, AttributeError):
        pass

    # Only ask for confirmation if we're in an interactive TTY, not in yolo mode,
    # NOT running as a sub-agent, and NOT in WebSocket mode (WebSocket has its own permission system)
    if (
        not yolo_mode
        and not running_as_subagent
        and not websocket_mode_active
        and sys.stdin.isatty()
    ):
        # Queue concurrent confirmations instead of rejecting parallel callers.
        while not _CONFIRMATION_LOCK.acquire(blocking=False):
            await asyncio.sleep(0.01)

        # Get puppy name for personalized messages
        from code_puppy.config import get_puppy_name

        puppy_name = get_puppy_name().title()

        # Build panel content
        panel_content = Text()
        panel_content.append("Requesting permission to run:\n", style="bold yellow")
        panel_content.append("$ ", style="bold green")
        panel_content.append(command, style="bold white")

        if cwd:
            panel_content.append("\n\n", style="")
            panel_content.append("Working directory: ", style="dim")
            panel_content.append(cwd, style="dim cyan")

        # Use the common approval function (async version)
        try:
            confirmed, user_feedback = await get_user_approval_async(
                title="Shell Command",
                content=panel_content,
                preview=None,
                border_style="dim white",
                puppy_name=puppy_name,
            )
        finally:
            _CONFIRMATION_LOCK.release()

        if not confirmed:
            if user_feedback:
                result = ShellCommandOutput(
                    success=False,
                    command=command,
                    error=f"USER REJECTED: {user_feedback}",
                    user_feedback=user_feedback,
                    stdout=None,
                    stderr=None,
                    exit_code=None,
                    execution_time=None,
                )
            else:
                result = ShellCommandOutput(
                    success=False,
                    command=command,
                    error="User rejected the command!",
                    stdout=None,
                    stderr=None,
                    exit_code=None,
                    execution_time=None,
                )
            return result
    else:
        time.time()

    # Execute the command - sub-agents run silently without keyboard context
    return await _execute_shell_command(
        command=command,
        cwd=cwd,
        timeout=timeout,
        group_id=group_id,
        silent=running_as_subagent,
    )


async def _execute_shell_command(
    command: str,
    cwd: str | None,
    timeout: int,
    group_id: str,
    silent: bool = False,
) -> ShellCommandOutput:
    """Internal helper to execute a shell command.

    Args:
        command: The shell command to execute
        cwd: Working directory for command execution
        timeout: Inactivity timeout in seconds
        group_id: Unique group ID for message grouping
        silent: If True, suppress streaming output (for sub-agents)

    Returns:
        ShellCommandOutput with execution results
    """
    # Always emit the ShellStartMessage banner (even for sub-agents)
    bus = get_message_bus()
    bus.emit(
        ShellStartMessage(
            command=command,
            cwd=cwd,
            timeout=timeout,
        )
    )

    # Shell output (including \r progress bars) streams inside the bottom
    # bar's scroll region — nothing to pause anymore.
    # Acquire shared keyboard context - Ctrl-X/Ctrl-C will kill ALL running commands
    # This is reference-counted: listener starts on first command, stops on last
    _acquire_keyboard_context()
    try:
        # When a command executor backend is installed (e.g. an editor host
        # running commands in its own terminal), delegate execution to it.
        # This runs on the event loop, so we can await the host directly.
        from code_puppy.tools.io_backends import get_command_executor

        executor = get_command_executor()
        if executor is not None:
            return await _execute_via_backend(
                executor, command, cwd, timeout, group_id, silent
            )
        return await _run_command_inner(command, cwd, timeout, group_id, silent=silent)
    finally:
        _release_keyboard_context()


async def _execute_via_backend(
    executor,
    command: str,
    cwd: str | None,
    timeout: int,
    group_id: str,
    silent: bool,
) -> ShellCommandOutput:
    """Run a command through an installed ``CommandExecutor`` backend.

    Streams the host's combined output to the UI as shell lines (so the run
    still looks live inside Code Puppy) and maps the result to the standard
    ``ShellCommandOutput``. Failures fall back to a structured error rather
    than raising, matching ``_run_command_inner``.
    """
    start = time.perf_counter()
    try:
        result = await executor.run(command, cwd, timeout)
    except Exception as e:
        if not silent:
            emit_error(traceback.format_exc(), message_group=group_id)
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error executing command {str(e)}",
            stdout=None,
            stderr=None,
            exit_code=-1,
            execution_time=time.perf_counter() - start,
            timeout=False,
        )

    output = result.output or ""
    if output and not silent:
        bus = get_message_bus()
        for line in output.splitlines():
            bus.emit_shell_line(line)
    truncated = "\n".join(_truncate_line(line) for line in output.split("\n")[-256:])
    return ShellCommandOutput(
        success=(result.exit_code == 0 and not result.timed_out),
        command=command,
        stdout=truncated or None,
        stderr=None,
        exit_code=result.exit_code,
        execution_time=time.perf_counter() - start,
        timeout=result.timed_out,
    )


def _run_command_sync(
    command: str,
    cwd: str | None,
    timeout: int,
    group_id: str,
    silent: bool = False,
) -> ShellCommandOutput:
    """Synchronous command execution - runs in thread pool.

    Console isolation (Windows): children get ``CREATE_NO_WINDOW`` — their
    own HIDDEN console — plus ``stdin=DEVNULL``. Sharing our console let
    the child tree stomp the shared input buffer: ``timeout /t`` and
    ``powershell`` call ``SetConsoleMode`` and re-enable
    ``ENABLE_PROCESSED_INPUT``, turning ^C back into console-wide
    CTRL_C_EVENTs mid-command (killing wrapper launchers like uvx.exe and
    waking the parent shell into fighting us for stdin), and children
    could literally eat the user's keystrokes ('press a key to
    continue'). With an isolated console their mode changes hit THEIR
    console, keyboard ^C can never be delivered to them as an event, and
    cancellation flows exclusively through the key listener →
    ``kill_all_running_shell_processes`` (taskkill /T) path by design.

    ``stdin=DEVNULL`` on every platform: agent shell commands are
    non-interactive by contract — a child reading stdin used to compete
    with the key listener for keystrokes (POSIX: also stomping termios);
    now it gets instant EOF instead of hanging until timeout.
    """
    creationflags = 0
    preexec_fn = None
    if sys.platform.startswith("win"):
        try:
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                | subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            )
        except Exception:
            creationflags = 0
    else:
        preexec_fn = os.setsid if hasattr(os, "setsid") else None

    import io

    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        bufsize=0,  # Unbuffered for real-time output
        preexec_fn=preexec_fn,
        creationflags=creationflags,
    )

    # Wrap pipes with TextIOWrapper that preserves \r (newline='' disables translation)
    process.stdout = io.TextIOWrapper(
        process.stdout, newline="", encoding="utf-8", errors="replace"
    )
    process.stderr = io.TextIOWrapper(
        process.stderr, newline="", encoding="utf-8", errors="replace"
    )
    _register_process(process)
    try:
        return run_shell_command_streaming(
            process, timeout=timeout, command=command, group_id=group_id, silent=silent
        )
    finally:
        # Ensure unregistration in case streaming returned early or raised
        _unregister_process(process)


async def _run_command_inner(
    command: str,
    cwd: str | None,
    timeout: int,
    group_id: str,
    silent: bool = False,
) -> ShellCommandOutput:
    """Inner command execution logic - runs blocking code in thread pool."""
    loop = asyncio.get_running_loop()
    try:
        # Run the blocking shell command in a thread pool to avoid blocking the event loop
        # This allows multiple sub-agents to run shell commands in parallel
        # Copy context so ContextVar-based session tracking propagates to the worker thread
        ctx = contextvars.copy_context()
        return await loop.run_in_executor(
            _SHELL_EXECUTOR,
            partial(
                ctx.run, _run_command_sync, command, cwd, timeout, group_id, silent
            ),
        )
    except Exception as e:
        if not silent:
            emit_error(traceback.format_exc(), message_group=group_id)
        if "stdout" not in locals():
            stdout = None
        if "stderr" not in locals():
            stderr = None

        # Apply line length limits to stdout/stderr if they exist
        truncated_stdout = None
        if stdout:
            stdout_lines = stdout.split("\n")
            truncated_stdout = "\n".join(
                [_truncate_line(line) for line in stdout_lines[-256:]]
            )

        truncated_stderr = None
        if stderr:
            stderr_lines = stderr.split("\n")
            truncated_stderr = "\n".join(
                [_truncate_line(line) for line in stderr_lines[-256:]]
            )

        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error executing command {str(e)}",
            stdout=truncated_stdout,
            stderr=truncated_stderr,
            exit_code=-1,
            timeout=False,
        )


class ReasoningOutput(BaseModel):
    success: bool = True


def share_your_reasoning(
    context: RunContext, reasoning: str, next_steps: str | List[str] | None = None
) -> ReasoningOutput:
    # Handle list of next steps by formatting them
    formatted_next_steps = next_steps
    if isinstance(next_steps, list):
        formatted_next_steps = "\n".join(
            [f"{i + 1}. {step}" for i, step in enumerate(next_steps)]
        )

    # Emit structured AgentReasoningMessage for the UI
    reasoning_msg = AgentReasoningMessage(
        reasoning=reasoning,
        next_steps=formatted_next_steps
        if formatted_next_steps and formatted_next_steps.strip()
        else None,
    )
    get_message_bus().emit(reasoning_msg)

    return ReasoningOutput(success=True)


def register_agent_run_shell_command(agent):
    """Register only the agent_run_shell_command tool."""

    @agent.tool
    async def agent_run_shell_command(
        context: RunContext,
        command: str = "",
        cwd: str = None,
        timeout: int = 60,
        background: bool = False,
    ) -> ShellCommandOutput:
        """Execute a shell command with comprehensive monitoring and safety features.

        Supports streaming output, timeout handling, and background execution.
        """
        result = await run_shell_command(context, command, cwd, timeout, background)
        await on_run_shell_command_output(result)
        return result


def register_agent_share_your_reasoning(agent):
    """Register only the agent_share_your_reasoning tool."""

    @agent.tool
    def agent_share_your_reasoning(
        context: RunContext,
        reasoning: str = "",
        next_steps: str | List[str] | None = None,
    ) -> ReasoningOutput:
        """Share the agent's current reasoning and planned next steps with the user.

        Displays reasoning and upcoming actions in a formatted panel for transparency.
        """
        return share_your_reasoning(context, reasoning, next_steps)
