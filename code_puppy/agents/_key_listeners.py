"""Keyboard listener thread helpers, extracted from ``BaseAgent``.

These functions listen for Ctrl+X (shell cancel) and optionally the configured
cancel-agent key (when it's not bound to a signal like SIGINT). Previously
they lived as methods on ``BaseAgent`` but they never touched ``self``, so
they're free functions now.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from code_puppy.keymap import cancel_agent_uses_signal, get_cancel_agent_char_code
from code_puppy.messaging import emit_warning


def spawn_key_listener(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
) -> Optional[threading.Thread]:
    """Start a daemon thread that listens for Ctrl+X / cancel-agent keys.

    Args:
        stop_event: Signal the listener to stop.
        on_escape: Callback for Ctrl+X (shell command cancel).
        on_cancel_agent: Optional callback for the configured cancel-agent
            key, only used when ``cancel_agent_uses_signal()`` is False.

    Returns:
        The started Thread, or None if stdin isn't a TTY (or otherwise
        unusable, e.g. during tests).
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

    def listener() -> None:
        try:
            if sys.platform.startswith("win"):
                _listen_windows(stop_event, on_escape, on_cancel_agent)
            else:
                _listen_posix(stop_event, on_escape, on_cancel_agent)
        except Exception:
            emit_warning("Key listener stopped unexpectedly; press Ctrl+C to cancel.")

    thread = threading.Thread(
        target=listener, name="code-puppy-key-listener", daemon=True
    )
    thread.start()
    return thread


def _listen_windows(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
) -> None:
    import msvcrt
    import time

    cancel_agent_char: Optional[str] = None
    if on_cancel_agent is not None and not cancel_agent_uses_signal():
        cancel_agent_char = get_cancel_agent_char_code()

    while not stop_event.is_set():
        try:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key == "\x18":  # Ctrl+X
                    try:
                        on_escape()
                    except Exception:
                        emit_warning(
                            "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                        )
                elif cancel_agent_char and on_cancel_agent and key == cancel_agent_char:
                    try:
                        on_cancel_agent()
                    except Exception:
                        emit_warning("Cancel agent handler raised unexpectedly.")
        except Exception:
            emit_warning(
                "Windows key listener error; Ctrl+C is still available for cancel."
            )
            return
        time.sleep(0.05)


def _listen_posix(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
) -> None:
    import select
    import sys
    import termios
    import tty

    cancel_agent_char: Optional[str] = None
    if on_cancel_agent is not None and not cancel_agent_uses_signal():
        cancel_agent_char = get_cancel_agent_char_code()

    stdin = sys.stdin
    try:
        fd = stdin.fileno()
    except (AttributeError, ValueError, OSError):
        return
    try:
        original_attrs = termios.tcgetattr(fd)
    except Exception:
        return

    try:
        tty.setcbreak(fd)
        while not stop_event.is_set():
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
                    on_escape()
                except Exception:
                    emit_warning(
                        "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                    )
            elif cancel_agent_char and on_cancel_agent and data == cancel_agent_char:
                try:
                    on_cancel_agent()
                except Exception:
                    emit_warning("Cancel agent handler raised unexpectedly.")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)
