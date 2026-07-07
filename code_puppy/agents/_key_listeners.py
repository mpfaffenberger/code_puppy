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
from code_puppy.messaging import emit_info, emit_warning


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


def acquire_listener(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]] = None,
) -> tuple[Optional[KeyListenerHandle], bool]:
    """Atomically reuse the live active listener or spawn + register one.

    The historical bug: three call sites each did ``get_active_handle()``
    → ``spawn_key_listener()`` → ``set_active_handle()`` as separate steps,
    so two components racing through that window could both spawn — two
    cbreak readers on one stdin, keystrokes split between them.

    Returns:
        ``(handle, spawned)`` — ``spawned`` is False when an existing live
        listener was reused (the caller must NOT stop it). ``handle`` is
        ``None`` (with ``spawned=True``) when stdin isn't a TTY.
    """
    global _active_handle
    with _active_handle_lock:
        existing = _active_handle
        if (
            existing is not None
            and existing.thread.is_alive()
            and not existing.stop_event.is_set()
        ):
            return existing, False
        handle = spawn_key_listener(stop_event, on_escape, on_cancel_agent)
        if handle is not None:
            _active_handle = handle
        return handle, True


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


#: Raw Ctrl+C byte. On Windows the session strips ENABLE_PROCESSED_INPUT,
#: so ^C reaches the listener as this byte instead of becoming a SIGINT.
_RAW_CTRL_C = "\x03"


def _ctrl_c_should_cancel() -> bool:
    """Buffer-first gate for raw-^C cancel (same contract as SIGINT).

    Returns False when composing input absorbed the press (editor
    cleared + hint shown). Fails open — cancellation must never break
    because a UI check raised.
    """
    try:
        from code_puppy.agents._run_signals import sigint_should_cancel

        return sigint_should_cancel()
    except Exception:
        return True


def _dispatch_key(
    data: str,
    on_escape: Callable[[], None],
    cancel_agent_char: Optional[str],
    on_cancel_agent: Optional[Callable[[], None]],
) -> None:
    """Route one keystroke: hotkeys first, everything else to the editor.

    Ctrl+X and the cancel-agent key keep PRIORITY and are never fed to
    the line editor. Shared by the POSIX and Windows listener loops.

    Raw ^C as the cancel char (the Windows default) keeps its universal
    shell semantics, mirroring the POSIX SIGINT handler's contract:
    composing input absorbs the press (clear + hint); only an empty
    prompt cancels the run; idle ^C clears the typed line.
    """
    if data == "\x18":  # Ctrl+X
        try:
            _resolve_escape_handler(on_escape)()
        except Exception:
            emit_warning("Ctrl+X handler raised unexpectedly; Ctrl+C still works.")
        return
    if cancel_agent_char and data == cancel_agent_char:
        handler = _resolve_cancel_handler(on_cancel_agent)
        if handler is None:
            # No handler (idle): a remapped cancel key is inert —
            # swallowed, never fed to the editor as a stray control
            # character. Raw ^C keeps its clear-the-line meaning via
            # the editor's own \x03 handling.
            if data == _RAW_CTRL_C:
                _feed_line_editor(data)
            return
        if data == _RAW_CTRL_C and not _ctrl_c_should_cancel():
            return  # buffer-first: composing input absorbed the press
        try:
            handler()
        except Exception:
            emit_warning("Cancel agent handler raised unexpectedly.")
        return
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

    The ack is LEVEL-triggered — re-asserted every lap — not edge-
    triggered at park entry only. Rationale: back-to-back suspensions
    (e.g. ``/resume``: one scope around ``handle_command``, another
    around the picker) can resume+re-suspend within one 50ms poll lap.
    The re-suspend clears ``released_event`` while we're STILL parked in
    this loop (``suspend_event`` never read as clear), so an entry-only
    ack would never be re-set and the new suspend would falsely time
    out ("Key listener did not release stdin in time") even though
    stdin was released the whole time.

    NOTE: we deliberately wait on ``stop_event`` (which is unset) rather
    than ``suspend_event`` (which IS set while we're parked here — waiting
    on it returns immediately and busy-spins, hogging the GIL and making
    raw-mode input prompts feel laggy while the listener is suspended).
    """
    while suspend_event.is_set() and not stop_event.is_set():
        if released_event is not None:
            released_event.set()
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


#: Max chars drained from the console input queue in one poll tick.
_WIN_BURST_CAP = 4096

#: CSI-u Shift+Enter — editor_keys maps body "13;2u" → newline.
_SHIFT_ENTER_SEQ = "\x1b[13;2u"

_VK_SHIFT = 0x10


def _win_shift_is_down() -> bool:
    """Physical Shift state via ``GetAsyncKeyState`` (best-effort).

    Classic console input (``getwch``) encodes Shift+Enter as a plain
    ``\\r`` — byte-identical to bare Enter — and neither Windows
    Terminal nor conhost honors the xterm modifyOtherKeys arming that
    disambiguates it on POSIX terminals (Ctrl+Enter only works because
    the console happens to encode it as ``\\n``). Asking the OS for the
    live modifier state is the only way to tell the two apart. Fails
    False (= plain Enter, submit) on headless/remote sessions where no
    local keyboard exists.
    """
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(_VK_SHIFT) & 0x8000)
    except Exception:
        return False


def _windows_char_to_seq(
    value: str, shift_is_down: Callable[[], bool] = _win_shift_is_down
) -> Optional[str]:
    """Translate chars whose classic-console encoding is ambiguous.

    Returns an xterm/CSI-u sequence to feed the editor directly, or
    ``None`` for a regular keystroke. Called AFTER paste coalescing so
    Shift+Insert pastes stay atomic bracketed pastes.
    """
    if value == "\r" and shift_is_down():
        return _SHIFT_ENTER_SEQ
    return None


#: Minimum all-text burst length treated as a paste. Two chars can be a
#: fast typing roll landing inside one 50ms poll tick (e.g. 'i' + Enter);
#: three-plus plain chars in under 50ms is effectively only ever a paste.
_WIN_PASTE_MIN_CHARS = 3


def _drain_windows_burst(msvcrt) -> list:
    """Read every pending console char as ``(kind, value)`` items.

    ``kind`` is ``"char"`` (regular key) or ``"seq"`` (extended key
    already translated to its xterm sequence).

    CONTRACT: the caller has already seen ``kbhit()`` return True, so
    the FIRST read is unconditional — do-while, not while. ``kbhit()``
    only peeks the console input queue and CANNOT see the CRT's
    internal pushback buffer, so re-polling it before the first read
    drops keys whose data already left the queue (an extended-key pair
    read half-way is exactly that — the original 'kbhit lie' bug).
    """
    items: list = []
    while len(items) < _WIN_BURST_CAP:
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            # Extended key pair — see the pushback-buffer note below.
            seq = _WIN_EXTENDED_KEYS.get(msvcrt.getwch())
            if seq:
                items.append(("seq", seq))
        else:
            items.append(("char", key))
        if not msvcrt.kbhit():
            break
    return items


#: Bracketed-paste markers a modern terminal (Windows Terminal ≥1.18
#: honors the ?2004h arming the bottom bar emits) may ALREADY have put
#: around a paste before ConPTY flattens it into a char flood.
_PASTE_OPEN = "\x1b[200~"
_PASTE_CLOSE = "\x1b[201~"


def _coalesce_paste_burst(items: list) -> Optional[str]:
    """Return the paste payload for a large all-text burst, else ``None``.

    The Windows console input queue has no bracketed paste: a paste
    arrives as a flood of individual chars, which the old one-char-per-
    tick loop rendered like slow typing — and every ``\\r`` in the flood
    submitted as its own prompt. Mirroring the classic prompt_toolkit
    win32 heuristic: many chars in a single read only ever means paste.
    Bursts containing extended keys (arrows etc.) are real typing.
    """
    if len(items) < _WIN_PASTE_MIN_CHARS:
        return None
    if any(kind != "char" for kind, _ in items):
        return None
    return "".join(value for _, value in items)


def _editor_paste_active() -> bool:
    """True when the installed line editor is mid-bracketed-paste."""
    editor = get_line_editor()
    if editor is None:
        return False
    try:
        return bool(getattr(editor, "paste_active", False))
    except Exception:
        return False


def _route_windows_burst(
    items: list,
    on_escape: Callable[[], None],
    cancel_agent_char: Optional[str],
    on_cancel_agent: Optional[Callable[[], None]],
) -> None:
    """Route one drained console burst to the editor / hotkey dispatch.

    Four lanes, in priority order:

    1. Editor mid-paste — continuation of a terminal-bracketed paste
       split across poll ticks: stream verbatim until the editor's
       PasteBuffer sees the closer. Wrapping (or dispatching) here
       would corrupt the payload.
    2. Terminal-bracketed paste — Windows Terminal honors the ?2004h
       arming and ConPTY delivers the ESC[200~/201~ markers as plain
       chars. Feed verbatim: wrapping AGAIN nests the markers, the
       inner opener classifies as "text", and an image-only paste
       (empty payload: ESC[200~ESC[201~) never reaches the
       clipboard-image capture — the Windows Ctrl+V image regression.
    3. Raw char flood (legacy conhost / older WT) — synthesize a
       bracketed paste so the editor inserts atomically and newlines
       stay IN the buffer instead of submitting one prompt per line.
    4. Real typing — per-key dispatch (hotkeys keep priority; ambiguous
       classic-console encodings like Shift+Enter get translated).
    """
    payload = _coalesce_paste_burst(items)
    if _editor_paste_active():
        for _, value in items:
            _feed_line_editor(value)
    elif payload is not None and (_PASTE_OPEN in payload or _PASTE_CLOSE in payload):
        _feed_line_editor(payload)
    elif payload is not None:
        _feed_line_editor(_PASTE_OPEN + payload + _PASTE_CLOSE)
    else:
        for kind, value in items:
            if kind == "char":
                translated = _windows_char_to_seq(value)
                if translated is not None:
                    kind, value = "seq", translated
            if kind == "seq":
                _feed_line_editor(value)
            else:
                _dispatch_key(value, on_escape, cancel_agent_char, on_cancel_agent)


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

    backoff = _RECOVERY_INITIAL_BACKOFF_S
    in_outage = False

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
                # Drain the WHOLE pending burst this tick (one char per
                # 50ms tick made a 200-char paste take ten seconds).
                # Extended-key note: the second half of a \x00/\xe0 pair
                # sits in the CRT's internal pushback buffer, which
                # kbhit() CANNOT see (it only peeks the console input
                # queue) — so per the _getwch docs the drain reads again
                # unconditionally. Gating on kbhit() here leaked the
                # prefix into the editor as a literal 'à' (\xe0) on
                # every arrow press. Unknown pairs are swallowed.
                # Known wart: a literal typed 'à' (U+00E0, non-US
                # layouts) is indistinguishable from the prefix and
                # briefly blocks the read until the next keypress.
                items = _drain_windows_burst(msvcrt)
                _route_windows_burst(
                    items, on_escape, cancel_agent_char, on_cancel_agent
                )
            else:
                # Idle tick: let a pending bare ESC expire.
                _tick_line_editor()
        except Exception as exc:
            # Recover instead of dying: warn once per outage, back off,
            # and keep retrying — a dead listener means a dead prompt.
            if not in_outage:
                in_outage = True
                emit_warning(
                    f"Windows key listener error ({exc!r}); recovering "
                    "automatically — Ctrl+C is still available for cancel."
                )
            if stop_event.wait(backoff):
                return
            backoff = min(backoff * 2.0, _RECOVERY_MAX_BACKOFF_S)
            continue
        if in_outage:
            in_outage = False
            backoff = _RECOVERY_INITIAL_BACKOFF_S
            emit_info("Windows key listener recovered.")
        time.sleep(0.05)


# =============================================================================
# POSIX listener
# =============================================================================


#: Consecutive transient read failures tolerated within one read session
#: (× the ~50ms retry pace ≈ 10 seconds of continuous EIO) before the
#: session yields back to the supervisor's slower backoff loop.
_MAX_TRANSIENT_READS = 200

#: Supervisor backoff bounds between read-session recovery attempts.
_RECOVERY_INITIAL_BACKOFF_S = 1.0
_RECOVERY_MAX_BACKOFF_S = 10.0


def _read_chunk(fd: int, decoder) -> Optional[str]:
    """Read every available byte from ``fd`` and decode incrementally.

    CRITICAL: must be ``os.read`` on the RAW fd — never a buffered
    ``TextIOWrapper.read(1)``. The wrapper slurps ALL available bytes
    into its Python-level buffer and returns one char, stranding the
    rest of an escape sequence where ``select()`` (fd-level) can't see
    it — the pending ESC then expires on the idle tick and the ``[A``
    tail leaks in as literal text (the live 'arrows don't work' bug).
    The incremental decoder keeps split UTF-8 chars intact across
    reads.

    Returns:
        * a (possibly empty) string of decoded chars on success — empty
          means a split multibyte char is buffered in the decoder;
        * ``""`` also for TRANSIENT errors (EINTR / EIO / EAGAIN): e.g.
          reads from the controlling tty return EIO while our process
          group is temporarily not the foreground group (backgrounded
          shell commands / tcsetpgrp shuffles). The listener must RETRY
          those, not die — a silent death here restores cooked termios
          and every subsequent keystroke echoes raw while the prompt
          goes unresponsive (the 2026-07-05 stdin wedge);
        * ``None`` on EOF or a fatal error (stdin genuinely gone).
    """
    import errno
    import os

    try:
        data = os.read(fd, 1024)
    except OSError as exc:
        if exc.errno in (errno.EINTR, errno.EIO, errno.EAGAIN, errno.EWOULDBLOCK):
            return ""
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
    """Self-healing supervisor around the actual read session.

    A read session can die for RECOVERABLE reasons — EIO storms while
    another process group briefly owns the tty, a failed cbreak
    re-acquire after suspend, select hiccups. Dying used to restore
    cooked termios and leave the prompt permanently dead with raw
    keystroke echo (the 2026-07-05 stdin wedge). Instead: warn ONCE per
    outage, back off (1s doubling to 10s), and keep retrying until the
    tty works again or the app stops — then announce recovery on the
    first successful read so the user knows input is back.
    """
    import sys
    import termios

    stdin = sys.stdin
    try:
        fd = stdin.fileno()
    except (AttributeError, ValueError, OSError):
        return
    try:
        original_attrs = termios.tcgetattr(fd)
    except Exception:
        return

    backoff = _RECOVERY_INITIAL_BACKOFF_S
    in_outage = [False]  # list-wrapped for the closure

    def _on_input_ok() -> None:
        nonlocal backoff
        if in_outage[0]:
            in_outage[0] = False
            emit_info("Key listener recovered — keyboard input restored.")
        backoff = _RECOVERY_INITIAL_BACKOFF_S

    while not stop_event.is_set():
        try:
            reason = _posix_read_session(
                stop_event,
                on_escape,
                on_cancel_agent,
                suspend_event,
                released_event,
                stdin,
                fd,
                original_attrs,
                _on_input_ok,
            )
        except Exception as exc:  # a bug must not kill input forever
            reason = f"unexpected error: {exc!r}"
        if reason == "stop" or stop_event.is_set():
            # Clean shutdown — including a stop that landed mid-session:
            # never cry "outage" over the app simply exiting.
            return
        if not in_outage[0]:
            in_outage[0] = True
            emit_warning(
                f"Key listener: keyboard input interrupted ({reason}); "
                "recovering automatically — the prompt may be briefly "
                "unresponsive."
            )
        if stop_event.wait(backoff):
            return
        backoff = min(backoff * 2.0, _RECOVERY_MAX_BACKOFF_S)


def _posix_read_session(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
    on_cancel_agent: Optional[Callable[[], None]],
    suspend_event: Optional[threading.Event],
    released_event: Optional[threading.Event],
    stdin,
    fd: int,
    original_attrs,
    on_input_ok: Callable[[], None],
) -> str:
    """One cbreak read session; returns WHY it ended.

    ``"stop"`` means clean shutdown; anything else is a human-readable
    recoverable reason the supervisor folds into its outage warning.
    ALWAYS restores the original termios attrs on the way out.
    """
    import codecs
    import select
    import termios
    import time
    import tty

    cancel_agent_char = _resolve_cancel_char(on_cancel_agent)
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

    transient_reads = 0
    reported_ok = False
    try:
        try:
            _enter_cbreak()
        except Exception as exc:
            return f"could not enter cbreak mode: {exc!r}"
        while not stop_event.is_set():
            # Suspend handling: release stdin (restore termios) and park
            # until the plugin signals resume. Re-arm cbreak afterwards.
            if suspend_event is not None and suspend_event.is_set():
                _exit_cbreak()
                _wait_while_suspended(stop_event, suspend_event, released_event)
                if stop_event.is_set():
                    return "stop"
                # Plugin finished — re-acquire raw mode.
                try:
                    _enter_cbreak()
                except Exception as exc:
                    return f"could not re-acquire terminal after suspend: {exc!r}"
                continue

            try:
                read_ready, _, _ = select.select([stdin], [], [], 0.05)
            except Exception as exc:
                return f"stdin select failed: {exc!r}"
            if not read_ready:
                # Idle tick: let a pending bare ESC expire.
                _tick_line_editor()
                continue
            chunk = _read_chunk(fd, decoder)
            if chunk is None:
                return "stdin EOF or fatal read error"
            if not chunk:
                # Transient failure (EIO while another process group
                # briefly owns the tty) or a split multibyte char still
                # buffering in the decoder. Retry — paced, and bounded
                # per session; the supervisor keeps retrying beyond that
                # with its slower backoff.
                transient_reads += 1
                if transient_reads >= _MAX_TRANSIENT_READS:
                    return "stdin unreadable (persistent EIO)"
                time.sleep(0.05)
                continue
            transient_reads = 0
            if not reported_ok:
                reported_ok = True
                on_input_ok()
            # Per-char dispatch: hotkeys keep priority even mid-burst;
            # everything else streams into the editor, whose ESC state
            # machine assembles sequences byte-at-a-time.
            for ch in chunk:
                _dispatch_key(ch, on_escape, cancel_agent_char, on_cancel_agent)
        return "stop"
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
        # A silently-failed suspend means the caller launches its own stdin
        # reader (prompt_toolkit, input()) while the listener is STILL in
        # cbreak mode — two readers, keystrokes split between them. Give
        # the listener one extended grace period, then warn loudly so the
        # flakiness is at least diagnosable instead of "sometimes my keys
        # vanish".
        if not handle.suspend(timeout=timeout):
            if not handle.released_event.wait(timeout=2.0):
                emit_warning(
                    "Key listener did not release stdin in time; "
                    "input may be flaky until this prompt closes."
                )
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
    "acquire_listener",
    "get_active_handle",
    "get_line_editor",
    "set_active_handle",
    "set_cancel_handler",
    "set_escape_handler",
    "set_line_editor",
    "spawn_key_listener",
    "suspended_key_listener",
]
