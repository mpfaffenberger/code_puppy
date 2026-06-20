"""Keyboard listener thread helpers, extracted from ``BaseAgent``.

These functions listen for Ctrl+X (shell cancel), the configured
cancel-agent key (when it's not bound to a signal like SIGINT), and the
configured pause-agent key (Phase 3 of the pause/steer feature).

The listener exposes a ``KeyListenerHandle`` so consumers can ``suspend``
it (release stdin) while another UI component (e.g. the steering-message
editor's ``prompt_toolkit.Application``) takes over the terminal, then
``resume`` it. Without this contract, two threads fight over stdin and
the terminal ends up bricked — see the Phase 3 fix-up pass.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from code_puppy.keymap import (
    cancel_agent_uses_signal,
    get_cancel_agent_char_code,
    get_pause_agent_char_code,
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
    on_pause_agent: Optional[Callable[[], None]] = None,
) -> Optional[KeyListenerHandle]:
    """Start a daemon thread that listens for Ctrl+X / cancel / pause keys.

    Args:
        stop_event: Signal the listener to stop.
        on_escape: Callback for Ctrl+X (shell command cancel).
        on_cancel_agent: Optional callback for the configured cancel-agent
            key. Only used when ``cancel_agent_uses_signal()`` is False.
        on_pause_agent: Optional callback for the configured pause-agent
            key. Always honoured when provided.

    Returns:
        A ``KeyListenerHandle`` for lifecycle management, or ``None`` if
        stdin isn't a TTY / unavailable.
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
                    on_pause_agent,
                    suspend_event,
                    released_event,
                )
            else:
                _listen_posix(
                    stop_event,
                    on_escape,
                    on_cancel_agent,
                    on_pause_agent,
                    suspend_event,
                    released_event,
                )
        except Exception:
            emit_warning("Key listener stopped unexpectedly; press Ctrl+C to cancel.")

    thread = threading.Thread(target=listener, name="mist-key-listener", daemon=True)
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


def _resolve_special_chars(
    on_cancel_agent: Optional[Callable[[], None]],
    on_pause_agent: Optional[Callable[[], None]],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve the cancel + pause character codes once per listener start.

    Returns ``(cancel_char, pause_char)``; either may be ``None`` if the
    corresponding callback wasn't provided or if SIGINT owns cancel.
    """
    cancel_char: Optional[str] = None
    if on_cancel_agent is not None and not cancel_agent_uses_signal():
        cancel_char = get_cancel_agent_char_code()

    pause_char: Optional[str] = None
    if on_pause_agent is not None:
        try:
            pause_char = get_pause_agent_char_code()
        except Exception:
            pause_char = None
    return cancel_char, pause_char


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


def _listen_windows(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
    on_pause_agent: Optional[Callable[[], None]] = None,
    suspend_event: Optional[threading.Event] = None,
    released_event: Optional[threading.Event] = None,
) -> None:
    import msvcrt
    import time

    cancel_agent_char, pause_agent_char = _resolve_special_chars(
        on_cancel_agent, on_pause_agent
    )

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
                if key == "\x18":  # Ctrl+X
                    try:
                        _resolve_escape_handler(on_escape)()
                    except Exception:
                        emit_warning(
                            "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                        )
                elif cancel_agent_char and on_cancel_agent and key == cancel_agent_char:
                    try:
                        on_cancel_agent()
                    except Exception:
                        emit_warning("Cancel agent handler raised unexpectedly.")
                elif pause_agent_char and on_pause_agent and key == pause_agent_char:
                    try:
                        on_pause_agent()
                    except Exception:
                        emit_warning("Pause agent handler raised unexpectedly.")
        except Exception:
            emit_warning(
                "Windows key listener error; Ctrl+C is still available for cancel."
            )
            return
        time.sleep(0.05)


# =============================================================================
# POSIX listener
# =============================================================================


def _listen_posix(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
    on_pause_agent: Optional[Callable[[], None]] = None,
    suspend_event: Optional[threading.Event] = None,
    released_event: Optional[threading.Event] = None,
) -> None:
    import select
    import sys
    import termios
    import tty

    cancel_agent_char, pause_agent_char = _resolve_special_chars(
        on_cancel_agent, on_pause_agent
    )

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

    def _enter_cbreak() -> None:
        nonlocal cbreak_active
        if not cbreak_active:
            tty.setcbreak(fd)
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
                        "Failed to re-acquire terminal after pause; "
                        "key listener exiting."
                    )
                    return
                continue

            try:
                read_ready, _, _ = select.select([stdin], [], [], 0.05)
            except Exception:
                break
            if not read_ready:
                continue
            data = stdin.read(1)
            if not data:
                break
            if data == "\x18":  # Ctrl+X
                try:
                    _resolve_escape_handler(on_escape)()
                except Exception:
                    emit_warning(
                        "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                    )
            elif cancel_agent_char and on_cancel_agent and data == cancel_agent_char:
                try:
                    on_cancel_agent()
                except Exception:
                    emit_warning("Cancel agent handler raised unexpectedly.")
            elif pause_agent_char and on_pause_agent and data == pause_agent_char:
                try:
                    on_pause_agent()
                except Exception:
                    emit_warning("Pause agent handler raised unexpectedly.")
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
    "set_active_handle",
    "set_escape_handler",
    "spawn_key_listener",
    "suspended_key_listener",
]
