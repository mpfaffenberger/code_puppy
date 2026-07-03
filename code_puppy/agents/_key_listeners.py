"""Keyboard listener thread helpers, extracted from ``BaseAgent``.

These functions listen for Ctrl+X (shell cancel) and the configured
cancel-agent key (when it's not bound to a signal like SIGINT).

The listener exposes a ``KeyListenerHandle`` so consumers can
``suspend`` it (release stdin) while another UI component takes over the
terminal, then ``resume`` it — otherwise two readers fight over stdin
and the terminal ends up bricked.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from code_puppy.keymap import (
    cancel_agent_uses_signal,
    get_cancel_agent_char_code,
)
from code_puppy.messaging import emit_warning


# =============================================================================
# Public handle
# =============================================================================


@dataclass
class KeyListenerHandle:
    """Lifecycle handle for the key-listener daemon thread.

    The owner (``run_with_mcp``) holds this so they can ``stop()`` cleanly.
    Plugins can call ``suspend()`` before launching another stdin consumer
    (e.g. ``prompt_toolkit``) and ``resume()`` afterwards.
    """

    thread: threading.Thread
    stop_event: threading.Event
    suspend_event: threading.Event = field(default_factory=threading.Event)
    released_event: threading.Event = field(default_factory=threading.Event)

    def suspend(self, timeout: float = 1.0) -> bool:
        """Tell the listener to release stdin and wait for our resume.

        Blocks until the listener confirms it has released stdin, or until
        ``timeout`` elapses.

        Returns:
            True if the listener acknowledged within the timeout, False
            otherwise (in which case stdin may still be owned by the
            listener — caller should warn the user).
        """
        self.released_event.clear()
        self.suspend_event.set()
        return self.released_event.wait(timeout=timeout)

    def resume(self) -> None:
        """Tell the listener to re-acquire stdin and resume reading.

        Idempotent and cheap.
        """
        self.suspend_event.clear()

    def stop(self) -> None:
        """Signal the listener thread to exit at its next iteration."""
        self.stop_event.set()
        # Make sure we're not parked on suspend_event after stop.
        self.suspend_event.clear()


# =============================================================================
# Module-level singleton for plugins
# =============================================================================

_active_handle: Optional[KeyListenerHandle] = None
_active_handle_lock = threading.Lock()

# =============================================================================
# Dynamic escape (Ctrl+X) handler
# =============================================================================
#
# The shell-command runner needs Ctrl+X to kill running processes, but only
# while commands are in flight. Rather than spawning a *second* cbreak
# listener thread (two readers on one stdin -- the historical cause of
# stolen CPR replies and the "terminal doesn't support cursor position
# requests" warning), it registers a handler here and the single active
# listener dispatches to it.

_escape_handler: Optional[Callable[[], None]] = None
_escape_handler_lock = threading.Lock()


def set_escape_handler(handler: Optional[Callable[[], None]]) -> None:
    """Install (or clear, with ``None``) the dynamic Ctrl+X handler.

    While set, it takes precedence over the ``on_escape`` callback the
    listener was spawned with.
    """
    global _escape_handler
    with _escape_handler_lock:
        _escape_handler = handler


def _resolve_escape_handler(fallback: Callable[[], None]) -> Callable[[], None]:
    """Return the dynamic Ctrl+X handler if set, else ``fallback``."""
    with _escape_handler_lock:
        return _escape_handler or fallback


# =============================================================================
# Line-editor feed target (Phase 3 of the bottom-bar rewrite)
# =============================================================================
#
# The run UI installs a ``RunningLineEditor`` here; the single listener
# thread routes every NON-hotkey character into it (one stdin reader,
# dynamic dispatch — the ``set_escape_handler`` pattern). Ctrl+X and the
# cancel-agent key keep priority and are never fed to the editor.

_line_editor: Optional[Any] = None
_line_editor_lock = threading.Lock()


def set_line_editor(editor: Optional[Any]) -> None:
    """Install (or clear, with ``None``) the line-editor feed target."""
    global _line_editor
    with _line_editor_lock:
        _line_editor = editor


def get_line_editor() -> Optional[Any]:
    """Return the currently-installed line-editor feed target, or None."""
    with _line_editor_lock:
        return _line_editor


def _feed_line_editor(key: str) -> None:
    """Best-effort feed of a non-hotkey character into the editor."""
    editor = get_line_editor()
    if editor is None:
        return
    try:
        editor.feed(key)
    except Exception:
        # A broken editor must never kill the listener thread.
        pass


def _tick_line_editor() -> None:
    """Resolve the editor's pending-ESC timeout on idle poll ticks."""
    editor = get_line_editor()
    if editor is None:
        return
    try:
        editor.check_timeout()
    except Exception:
        pass


# =============================================================================
# Dynamic cancel-agent handler (persistent listener, Phase A)
# =============================================================================
#
# The cancel-agent hotkey callback is per-RUN (closes over the agent
# task + loop): the runtime arms it here while a run is active and
# clears it afterwards — mirroring ``set_escape_handler``. With no
# handler armed the cancel key is inert (never fed to the editor).

_cancel_handler: Optional[Callable[[], None]] = None
_cancel_handler_lock = threading.Lock()


def set_cancel_handler(handler: Optional[Callable[[], None]]) -> None:
    """Install (or clear, with ``None``) the per-run cancel-agent handler."""
    global _cancel_handler
    with _cancel_handler_lock:
        _cancel_handler = handler


def _resolve_cancel_handler(
    fallback: Optional[Callable[[], None]],
) -> Optional[Callable[[], None]]:
    """Return the dynamic cancel handler if set, else ``fallback``."""
    with _cancel_handler_lock:
        return _cancel_handler or fallback


def set_active_handle(handle: Optional[KeyListenerHandle]) -> None:
    """Publish the currently-running listener handle for plugins."""
    global _active_handle
    with _active_handle_lock:
        _active_handle = handle


def get_active_handle() -> Optional[KeyListenerHandle]:
    """Get the currently-running listener handle, or ``None``."""
    with _active_handle_lock:
        return _active_handle


# =============================================================================
# Spawn
# =============================================================================


def spawn_key_listener(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
) -> Optional[KeyListenerHandle]:
    """Start a daemon thread that listens for Ctrl+X / cancel keys.

    ``on_escape`` handles Ctrl+X (shell cancel); ``on_cancel_agent`` is
    only used when ``cancel_agent_uses_signal()`` is False. Returns a
    ``KeyListenerHandle``, or ``None`` if stdin isn't a TTY.
    """
    try:
        import sys
    except ImportError:
        return None

    stdin = getattr(sys, "stdin", None)
    if stdin is None or not hasattr(stdin, "isatty"):
        return None
    try:
        if not stdin.isatty():
            return None
    except Exception:
        return None

    suspend_event = threading.Event()
    released_event = threading.Event()

    def listener() -> None:
        try:
            if sys.platform.startswith("win"):
                _listen_windows(
                    stop_event,
                    on_escape,
                    on_cancel_agent,
                    suspend_event,
                    released_event,
                )
            else:
                _listen_posix(
                    stop_event,
                    on_escape,
                    on_cancel_agent,
                    suspend_event,
                    released_event,
                )
        except Exception:
            emit_warning("Key listener stopped unexpectedly; press Ctrl+C to cancel.")

    thread = threading.Thread(
        target=listener, name="code-puppy-key-listener", daemon=True
    )
    thread.start()
    return KeyListenerHandle(
        thread=thread,
        stop_event=stop_event,
        suspend_event=suspend_event,
        released_event=released_event,
    )


# =============================================================================
# Shared helpers
# =============================================================================


def _resolve_cancel_char(
    on_cancel_agent: Optional[Callable[[], None]],
) -> Optional[str]:
    """Resolve the cancel character code once per listener start.

    Returns ``None`` when SIGINT owns cancel. The char is resolved even
    without a spawn-time callback: the persistent listener (Phase A)
    receives its per-run handler later via ``set_cancel_handler``, and
    dispatch re-checks handler presence per keystroke.
    """
    if cancel_agent_uses_signal():
        return None
    try:
        return get_cancel_agent_char_code()
    except Exception:
        return None


def _dispatch_key(
    data: str,
    on_escape: Callable[[], None],
    cancel_agent_char: Optional[str],
    on_cancel_agent: Optional[Callable[[], None]],
) -> None:
    """Route one keystroke: hotkeys first, everything else to the editor.

    Ctrl+X and the cancel-agent key keep PRIORITY and are never fed to
    the line editor. Shared by the POSIX and Windows listener loops.
    """
    if data == "\x18":  # Ctrl+X
        try:
            _resolve_escape_handler(on_escape)()
        except Exception:
            emit_warning("Ctrl+X handler raised unexpectedly; Ctrl+C still works.")
    elif cancel_agent_char and data == cancel_agent_char:
        handler = _resolve_cancel_handler(on_cancel_agent)
        if handler is not None:
            try:
                handler()
            except Exception:
                emit_warning("Cancel agent handler raised unexpectedly.")
        # No handler (idle): the cancel key is inert — swallowed, never
        # fed to the editor as a stray control character.
    else:
        # Not a hotkey — route to the running line editor (if installed).
        _feed_line_editor(data)


def _wait_while_suspended(
    stop_event: threading.Event,
    suspend_event: threading.Event,
    released_event: Optional[threading.Event] = None,
) -> None:
    """Block until suspend is cleared or stop is set.

    Sets ``released_event`` (when given) to confirm we've parked. Polls
    every 50ms so we still respond to stop in a reasonable time.

    NOTE: we deliberately wait on ``stop_event`` (which is unset) rather
    than ``suspend_event`` (which IS set while we're parked here — waiting
    on it returns immediately and busy-spins, hogging the GIL and making
    raw-mode input prompts feel laggy while the listener is suspended).
    """
    if released_event is not None:
        released_event.set()
    while suspend_event.is_set() and not stop_event.is_set():
        stop_event.wait(timeout=0.05)


# =============================================================================
# Windows listener
# =============================================================================


#: Windows extended keys (second getwch after \x00/\xe0) → xterm seqs.
_WIN_EXTENDED_KEYS = {
    "H": "\x1b[A",  # Up
    "P": "\x1b[B",  # Down
    "K": "\x1b[D",  # Left
    "M": "\x1b[C",  # Right
    "G": "\x1b[H",  # Home
    "O": "\x1b[F",  # End
    "S": "\x1b[3~",  # Delete
    "s": "\x1b[1;5D",  # Ctrl+Left / Ctrl+Right / F2 below
    "t": "\x1b[1;5C",
    "<": "\x1b[12~",
}


def _listen_windows(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
    suspend_event: Optional[threading.Event] = None,
    released_event: Optional[threading.Event] = None,
) -> None:
    import msvcrt
    import time

    cancel_agent_char = _resolve_cancel_char(on_cancel_agent)

    while not stop_event.is_set():
        # Honor suspend: msvcrt doesn't reconfigure the terminal, so the
        # contract here is purely "don't read keystrokes while suspended."
        if suspend_event is not None and suspend_event.is_set():
            _wait_while_suspended(stop_event, suspend_event, released_event)
            if stop_event.is_set():
                return
            continue

        try:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    # Extended key: the second half of the pair sits in
                    # the CRT's internal pushback buffer, which kbhit()
                    # CANNOT see (it only peeks the console input queue)
                    # — so per the _getwch docs we read again
                    # unconditionally. Gating on kbhit() here leaked the
                    # prefix into the editor as a literal 'à' (\xe0) on
                    # every arrow press. Unknown pairs are swallowed.
                    # Known wart: a literal typed 'à' (U+00E0, non-US
                    # layouts) is indistinguishable from the prefix and
                    # briefly blocks this read until the next keypress.
                    seq = _WIN_EXTENDED_KEYS.get(msvcrt.getwch())
                    if seq:
                        _feed_line_editor(seq)
                else:
                    _dispatch_key(key, on_escape, cancel_agent_char, on_cancel_agent)
            else:
                # Idle tick: let a pending bare ESC expire.
                _tick_line_editor()
        except Exception:
            emit_warning(
                "Windows key listener error; Ctrl+C is still available for cancel."
            )
            return
        time.sleep(0.05)


# =============================================================================
# POSIX listener
# =============================================================================


def _read_chunk(fd: int, decoder) -> Optional[str]:
    """Read every available byte from ``fd`` and decode incrementally.

    CRITICAL: must be ``os.read`` on the RAW fd — never a buffered
    ``TextIOWrapper.read(1)``. The wrapper slurps ALL available bytes
    into its Python-level buffer and returns one char, stranding the
    rest of an escape sequence where ``select()`` (fd-level) can't see
    it — the pending ESC then expires on the idle tick and the ``[A``
    tail leaks in as literal text (the live 'arrows don't work' bug).
    The incremental decoder keeps split UTF-8 chars intact across
    reads. Returns None on EOF/error.
    """
    import os

    try:
        data = os.read(fd, 1024)
    except OSError:
        return None
    if not data:
        return None
    try:
        return decoder.decode(data)
    except Exception:
        return data.decode("utf-8", errors="replace")


def _listen_posix(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
    suspend_event: Optional[threading.Event] = None,
    released_event: Optional[threading.Event] = None,
) -> None:
    import codecs
    import select
    import sys
    import termios
    import tty

    cancel_agent_char = _resolve_cancel_char(on_cancel_agent)

    stdin = sys.stdin
    try:
        fd = stdin.fileno()
    except (AttributeError, ValueError, OSError):
        return
    try:
        original_attrs = termios.tcgetattr(fd)
    except Exception:
        return

    cbreak_active = False
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def _enter_cbreak() -> None:
        nonlocal cbreak_active
        if not cbreak_active:
            tty.setcbreak(fd)
            # Phase B: distinguish Enter (\r) from Ctrl+J (\n) for the
            # persistent editor — setcbreak leaves ICRNL on, which maps
            # CR->LF and makes them identical. Best-effort; the editor
            # treats a stray \n as newline-insert either way.
            #
            # setcbreak also leaves IEXTEN on, and on BSD/macOS the tty
            # driver honors VLNEXT (Ctrl+V = "literal next") even in
            # non-canonical mode when IEXTEN is set: the kernel EATS the
            # first ^V as a quote-prefix and only the SECOND one reaches
            # us (the live 'press Ctrl+V twice to paste an image' bug).
            # VDISCARD (Ctrl+O) is likewise IEXTEN-gated. Clear IEXTEN so
            # every control char is delivered verbatim, exactly like the
            # raw mode (tty.setraw) the classic prompt_toolkit path used.
            try:
                attrs = termios.tcgetattr(fd)
                attrs[0] &= ~termios.ICRNL  # iflag
                attrs[3] &= ~termios.IEXTEN  # lflag
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
            except Exception:
                pass
            cbreak_active = True

    def _exit_cbreak() -> None:
        nonlocal cbreak_active
        if cbreak_active:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
            except Exception:
                pass
            cbreak_active = False

    try:
        _enter_cbreak()
        while not stop_event.is_set():
            # Suspend handling: release stdin (restore termios) and park
            # until the plugin signals resume. Re-arm cbreak afterwards.
            if suspend_event is not None and suspend_event.is_set():
                _exit_cbreak()
                _wait_while_suspended(stop_event, suspend_event, released_event)
                if stop_event.is_set():
                    return
                # Plugin finished — re-acquire raw mode.
                try:
                    _enter_cbreak()
                except Exception:
                    emit_warning(
                        "Failed to re-acquire terminal after suspend; "
                        "key listener exiting."
                    )
                    return
                continue

            try:
                read_ready, _, _ = select.select([stdin], [], [], 0.05)
            except Exception:
                break
            if not read_ready:
                # Idle tick: let a pending bare ESC expire.
                _tick_line_editor()
                continue
            chunk = _read_chunk(fd, decoder)
            if chunk is None:
                break
            # Per-char dispatch: hotkeys keep priority even mid-burst;
            # everything else streams into the editor, whose ESC state
            # machine assembles sequences byte-at-a-time.
            for ch in chunk:
                _dispatch_key(ch, on_escape, cancel_agent_char, on_cancel_agent)
    finally:
        # GUARANTEE termios restoration — even if something exploded inside
        # the suspend block.
        _exit_cbreak()
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
        except Exception:
            pass


# =============================================================================
# Reentrant suspend context manager
# =============================================================================
#
# Any code that wants exclusive ownership of stdin (prompt_toolkit
# Applications, Rich Prompt.ask, raw input(), etc.) MUST wrap the call
# in ``suspended_key_listener()``. Without this, two readers fight over
# stdin -- prompt_toolkit will emit the dreaded "your terminal doesn't
# support cursor position requests (CPR)" warning and arrow keys will
# behave erratically because the key-listener thread eats half of them.
#
# The context manager is reentrant via a refcount, so nested usage
# (e.g. ``get_user_approval_async`` -> ``arrow_select_async``) only
# actually suspends the listener once and only resumes after the
# outermost scope exits.

_suspend_lock = threading.Lock()
_suspend_depth = 0


@contextmanager
def suspended_key_listener(timeout: float = 1.0) -> Iterator[None]:
    """Suspend the active key listener for the duration of the block.

    Safe to use:
      * When no listener is active (no-op).
      * Nested -- only the outermost scope suspends/resumes.
      * From sync OR async code (it's a plain ``contextmanager``).

    Args:
        timeout: Seconds to wait for the listener to release stdin.
    """
    global _suspend_depth
    handle = get_active_handle()
    is_outermost = False
    with _suspend_lock:
        _suspend_depth += 1
        if _suspend_depth == 1 and handle is not None:
            is_outermost = True
    if is_outermost:
        # Best-effort suspend; if it doesn't release in time we just
        # carry on quietly rather than spamming the user with a warning.
        handle.suspend(timeout=timeout)
    try:
        yield
    finally:
        with _suspend_lock:
            _suspend_depth -= 1
            should_resume = _suspend_depth == 0 and handle is not None
        if should_resume:
            handle.resume()


__all__ = [
    "KeyListenerHandle",
    "get_active_handle",
    "get_line_editor",
    "set_active_handle",
    "set_cancel_handler",
    "set_escape_handler",
    "set_line_editor",
    "spawn_key_listener",
    "suspended_key_listener",
]
