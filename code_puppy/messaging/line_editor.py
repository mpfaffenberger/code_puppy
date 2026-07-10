"""Raw-mode line editor for the persistent bottom-bar prompt.

The key-listener daemon thread (``code_puppy.agents._key_listeners``)
feeds raw characters into :meth:`RunningLineEditor.feed`; the editor
maintains the buffer, repaints the bottom-bar prompt viewport on every
edit, and routes submissions (idle → new REPL turn, running → steer /
slash drain — see ``run_ui``'s router).

Key map (Phase B parity set): printables, backspace/Delete, Ctrl+U/K/W
kills, Ctrl+A/E + Left/Right/Home/End + word jumps (Ctrl/Alt+arrows,
Meta-b/f), Up/Down (menu > multiline line-move > history), Enter
(accept-completion / newline-in-multiline / submit; ``\\r`` only — the
POSIX listener clears ICRNL so Ctrl+J = ``\\n`` = newline), Shift/Ctrl+
Enter (CSI-u + modifyOtherKeys → newline), Alt+Enter (queue-submit),
Ctrl+D (EOF on empty), Ctrl+R (reverse search; Enter accepts WITHOUT
submitting), Ctrl+V (async smart paste — image or text), Ctrl+X chords
(registry-driven: Ctrl+E $EDITOR, shell kill/background — see chords),
Tab/Shift-Tab
(completion), F2 / Alt+M (multiline), bracketed paste (atomic insert).

Unknown CSI/SS3 sequences are swallowed whole. ESC disambiguation uses
a pending timestamp; bare ESC resolves on the next feed()/check_timeout.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, List, Optional

from . import editor_keys as ek
from .bottom_bar import get_bottom_bar
from .chords import clear_chord_hint
from .editor_actions import apply_action, handle_chord
from .editor_display import to_display
from .editor_history import (
    HistoryNavigator,
    ReverseSearch,
    feed_reverse_search,
    safe_navigator,
    safe_reverse_search,
)
from .editor_paste import PasteBuffer, classify_paste
from .pause_controller import get_pause_controller

logger = logging.getLogger(__name__)

#: Alt+Enter arrives as ESC then Enter within a few ms; slower = bare
#: ESC + separate key. TODO(deferred): >50ms SSH latency can split an
#: Alt+Enter — consider a config knob/adaptive timeout if reports come.
DEFAULT_ESC_TIMEOUT = 0.05

# Raw control chars live in editor_keys (see the Ctrl+K / Ctrl+V notes there).
_ENTER, _CTRL_J, _TAB, _ESC = ek.ENTER, ek.CTRL_J, ek.TAB, ek.ESC
_BACKSPACE_KEYS = ek.BACKSPACE_KEYS
_CTRL_A, _CTRL_C, _CTRL_D = ek.CTRL_A, ek.CTRL_C, ek.CTRL_D
_CTRL_E, _CTRL_K = ek.CTRL_E, ek.CTRL_K
_CTRL_R, _CTRL_U, _CTRL_V, _CTRL_W = ek.CTRL_R, ek.CTRL_U, ek.CTRL_V, ek.CTRL_W

#: Callback signature: ``(text, mode)`` where mode is "now" or "queue".
SubmitListener = Callable[[str, str], None]

#: Router signature: ``(text, mode) -> feedback | None``. When installed,
#: it REPLACES the built-in routing (steer queues / slash-command queue);
#: the run_ui layer uses this to centralize idle-vs-running dispatch.
SubmitRouter = Callable[[str, str], Optional[str]]


class RunningLineEditor:
    """Line editor fed by the key-listener thread.

    Thread-safe: :meth:`feed`, :meth:`check_timeout`, and the accessors
    may be called from any thread. Construction args exist for testing
    (inject ``bar`` / ``pause_controller`` / ``now`` / history objects);
    production code uses the defaults which resolve lazily.
    """

    DEFAULT_PROMPT_PREFIX = "› "

    def __init__(
        self,
        prompt_prefix: str = DEFAULT_PROMPT_PREFIX,
        esc_timeout: float = DEFAULT_ESC_TIMEOUT,
        bar=None,
        pause_controller=None,
        now: Callable[[], float] = time.monotonic,
        history: Optional[HistoryNavigator] = None,
        reverse_search: Optional[ReverseSearch] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._prompt_prefix = prompt_prefix
        self._prompt_prefix_sgrs: List[str] = []  # per-char prefix colors
        self._esc_timeout = esc_timeout
        self._bar = bar
        self._pause_controller = pause_controller
        self._now = now
        self._buffer = ""
        self._cursor = 0
        # ESC state machine: pending timestamp + CSI accumulator + SS3 flag.
        self._esc_pending_at: Optional[float] = None
        self._csi_buf: Optional[str] = None
        self._ss3_pending = False
        # Slash commands ("/foo") park here instead of the steer queues.
        self._command_queue: "queue.Queue[str]" = queue.Queue()
        self._submit_listeners: List[SubmitListener] = []
        # Optional overrides installed by run_ui.
        self._router: Optional[SubmitRouter] = None
        self._eof_handler: Optional[Callable[[], None]] = None
        self._clipboard_handler: Optional[Callable[[], None]] = None
        self._ctrl_x_pending = False  # Ctrl+X chord prefix armed (see chords)
        # Phase B feature state.
        self._history = history if history is not None else safe_navigator()
        self._rsearch = (
            reverse_search if reverse_search is not None else safe_reverse_search()
        )
        self._paste = PasteBuffer()
        self._completion = None  # CompletionEngine, attached by run_ui
        self._multiline = False

    # =========================================================================
    # Accessors / configuration
    # =========================================================================

    @property
    def buffer(self) -> str:
        with self._lock:
            return self._buffer

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._cursor

    @property
    def multiline(self) -> bool:
        with self._lock:
            return self._multiline

    def get_pending_command(self) -> Optional[str]:
        """Pop the next pending ``/slash`` command, or ``None``."""
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def set_submit_router(self, router: Optional[SubmitRouter]) -> None:
        """Install (or clear) a router that replaces the built-in routing."""
        with self._lock:
            self._router = router

    def set_eof_handler(self, handler: Optional[Callable[[], None]]) -> None:
        with self._lock:  # Ctrl+D-on-empty-buffer handler (run_ui)
            self._eof_handler = handler

    def set_clipboard_handler(self, handler: Optional[Callable[[], None]]) -> None:
        with self._lock:  # async Ctrl+V clipboard handler (run_ui)
            self._clipboard_handler = handler

    @property
    def paste_active(self) -> bool:
        """True while a bracketed paste is streaming into the buffer.

        The Windows key listener checks this so a paste split across
        poll ticks isn't re-coalesced (and re-wrapped) mid-stream.
        """
        return self._paste.active

    def insert_paste_text(self, text: str) -> None:
        """Insert clipboard content (programmatic — no completion)."""
        if not text:
            return
        with self._lock:
            self._insert_text(text, typed=False)

    def replace_buffer_text(self, text: str) -> None:
        """Replace the whole buffer (external $EDITOR round-trip)."""
        with self._lock:
            self._buffer = text
            self._cursor = len(text)
            self._history.reset()
            self._close_completion()
            self._repaint()

    def attach_completion(self, engine) -> None:
        """Attach a CompletionEngine (or None to detach)."""
        with self._lock:
            self._completion = engine

    def set_prompt_prefix(
        self, prefix: str, prefix_sgrs: Optional[List[str]] = None
    ) -> None:
        """Change the prompt prefix (+ repaint). ``prefix_sgrs``: one SGR
        string per prefix char (out-of-band color — ``prompt_prefix_style``)."""
        with self._lock:
            self._prompt_prefix = prefix or ""
            self._prompt_prefix_sgrs = list(prefix_sgrs or [])
            self._repaint()

    def is_composing(self) -> bool:
        """Text buffered or reverse-i-search active (any mode)."""
        with self._lock:
            return bool(self._buffer) or self._rsearch.active

    def clear_buffer(self) -> None:
        """Discard typed text + transient UI state (Ctrl+C-at-idle)."""
        with self._lock:
            self._esc_pending_at = None
            if self._ctrl_x_pending:
                self._ctrl_x_pending = False
                clear_chord_hint()
            if self._rsearch.active:
                self._rsearch.cancel()
                self._set_completion_suppressed(False)
            if self._buffer or self._cursor:
                self._buffer = ""
                self._cursor = 0
                self._history.reset()
            self._close_completion()
            self._repaint()

    def add_submit_listener(self, callback: SubmitListener) -> None:
        with self._lock:
            if callback not in self._submit_listeners:
                self._submit_listeners.append(callback)

    def remove_submit_listener(self, callback: SubmitListener) -> None:
        with self._lock:
            try:
                self._submit_listeners.remove(callback)
            except ValueError:
                pass

    def apply_completion(self, start: int, end: int, replacement: str) -> None:
        """Apply a completion: replace buffer[start:end) with ``replacement``.

        Absolute indices (clamped) — the CompletionEngine anchors them to
        the cursor AT QUERY TIME, so the splice stays correct even when
        the user moved the cursor while the menu was open.
        """
        with self._lock:
            start = max(0, min(start, len(self._buffer)))
            end = max(start, min(end, len(self._buffer)))
            self._buffer = self._buffer[:start] + replacement + self._buffer[end:]
            self._cursor = start + len(replacement)
            self._history.reset()
            self._repaint()

    # =========================================================================
    # Key input
    # =========================================================================

    def feed(self, key: str) -> None:
        """Process raw character(s) from the key-listener thread."""
        if not key:
            return
        feedback: List[str] = []
        with self._lock:
            for ch in key:
                note = self._feed_one(ch)
                if note:
                    feedback.append(note)
        # Emit OUTSIDE the lock — emit_info can fan out to renderers that
        # grab their own locks, and we never want lock-ordering surprises.
        for note in feedback:
            self._emit_feedback(note)

    def check_timeout(self) -> None:
        """Resolve a pending bare ESC whose timeout has elapsed."""
        with self._lock:
            self._resolve_esc_timeout()

    def repaint(self) -> None:
        """Repaint the prompt viewport from the current state."""
        with self._lock:
            self._repaint()

    # =========================================================================
    # Internals — key state machine
    # =========================================================================

    def _feed_one(self, ch: str) -> Optional[str]:
        """Process one character; returns a feedback line to emit, if any."""
        # Bracketed paste swallows EVERYTHING until the closer — no ESC
        # handling, no completion queries mid-paste.
        if self._paste.active:
            payload = self._paste.feed(ch)
            if payload is not None:
                self._insert_paste(payload)
            return None

        self._resolve_esc_timeout()

        # Mid-CSI: accumulate parameter/intermediate bytes until the final
        # byte (0x40-0x7E), then dispatch (unknown sequences swallowed).
        if self._csi_buf is not None:
            if "\x40" <= ch <= "\x7e":
                seq = self._csi_buf + ch
                self._csi_buf = None
                self._apply_action(ek.classify_csi(seq))
            else:
                self._csi_buf += ch
            return None

        # Mid-SS3 (ESC O <final>): exactly one byte.
        if self._ss3_pending:
            self._ss3_pending = False
            self._apply_action(ek.classify_ss3(ch))
            return None

        if self._esc_pending_at is not None:
            self._esc_pending_at = None
            if ch in (_ENTER, _CTRL_J):
                return self._submit(mode="queue")  # Alt+Enter
            elif ch == "[":
                self._csi_buf = ""
            elif ch == "O":
                self._ss3_pending = True
            elif ch in ("m", "M"):
                self._toggle_multiline()  # Alt+M
            elif ch == "b":
                self._apply_action("word_left")  # Meta-b (macOS Option+Left)
            elif ch == "f":
                self._apply_action("word_right")  # Meta-f (macOS Option+Right)
            elif ch in _BACKSPACE_KEYS:
                self._delete_word_back()  # Alt+Backspace
            elif ch == _ESC:
                # ESC ESC: first one was bare; keep the second pending.
                self._esc_pending_at = self._now()
            # Any other Alt+<key> combo: swallow both, no buffer damage.
            return None

        if ch == _ESC:
            if self._ctrl_x_pending:  # Esc cancels an armed chord
                self._ctrl_x_pending = False
                clear_chord_hint()
            if self._rsearch.active:
                # Cancel search immediately; keep ESC pending so a
                # trailing sequence is still consumed safely.
                self._rsearch.cancel()
                self._set_completion_suppressed(False)
                self._repaint()
            self._esc_pending_at = self._now()
            return None

        if ch == _CTRL_C:
            # Raw ^C only reaches the editor when the console can't turn
            # it into SIGINT (Windows clamps ENABLE_PROCESSED_INPUT for
            # the whole session — see cli_runner startup).
            # Mirror the SIGINT path: discard composed input / cancel
            # reverse search, never submit or kill anything — cancel
            # semantics stay with the hotkey/signal layers.
            self.clear_buffer()
            return None

        if self._rsearch.active:
            return self._feed_rsearch(ch)

        if handle_chord(self, ch):  # Ctrl+X chord prefix (chords registry)
            return None

        if ch == _ENTER:
            if self._completion_open():
                self._completion.accept()  # accept, do NOT submit (classic)
                return None
            if self._multiline:
                self._insert_text("\n")
                return None
            # Mid-run default is QUEUE (run as the next turn) — mid-turn
            # injection is opt-in via /steer. Idle routing ignores mode.
            return self._submit(mode="queue")
        if ch == _CTRL_J:
            self._insert_text("\n")  # Ctrl+J: always a newline
            return None
        if ch == _TAB:
            if self._completion is not None:
                self._completion.on_tab(self._buffer, self._cursor)
            return None
        if ch == _CTRL_R:
            self._rsearch.start()
            self._set_completion_suppressed(True)
            self._repaint()
            return None
        if ch == _CTRL_V:
            # Raw-\x16 / image-only clipboard fallback; handler is async.
            self._call_handler(self._clipboard_handler, "clipboard")
            return None
        if ch in _BACKSPACE_KEYS:
            if self._cursor > 0:
                self._buffer = (
                    self._buffer[: self._cursor - 1] + self._buffer[self._cursor :]
                )
                self._cursor -= 1
                self._after_edit()
            return None
        if ch == _CTRL_U:
            if self._buffer:
                self._buffer = ""
                self._cursor = 0
                self._after_edit()
            return None
        if ch == _CTRL_A:
            self._apply_action("home")
            return None
        if ch == _CTRL_E:
            self._apply_action("end")
            return None
        if ch == _CTRL_K:
            self._kill_to_line_end()
            return None
        if ch == _CTRL_W:
            self._delete_word_back()
            return None
        if ch == _CTRL_D:
            # EOF only on an EMPTY buffer (classic readline semantics).
            if not self._buffer:
                self._call_handler(self._eof_handler, "EOF")
            return None
        if ch.isprintable():
            self._insert_text(ch)
            return None
        return None  # any other control character: ignore safely

    def _apply_action(self, action: Optional[str]) -> None:
        """Dispatch a classified CSI/SS3 action (see editor_actions)."""
        apply_action(self, action)

    @staticmethod
    def _call_handler(handler: Optional[Callable[[], None]], name: str) -> None:
        """Best-effort invoke of an installed async handler (run_ui)."""
        if handler is None:
            return
        try:
            handler()
        except Exception:
            logger.debug("%s handler failed", name, exc_info=True)

    # =========================================================================
    # Internals — history / reverse search / completion / paste glue
    # =========================================================================

    def _history_recall(self, text: Optional[str]) -> None:
        if text is None:
            return
        self._buffer = text
        self._cursor = len(text)
        # Programmatic mutation: no menu; close() kills stale queries.
        self._close_completion()
        self._repaint()

    def _feed_rsearch(self, ch: str) -> Optional[str]:
        feed_reverse_search(self, ch)
        return None

    def _delete_word_back(self) -> None:
        """Ctrl+W / Alt+Backspace: delete to the previous word boundary."""
        start = ek.word_left(self._buffer, self._cursor)
        if start < self._cursor:
            self._buffer = self._buffer[:start] + self._buffer[self._cursor :]
            self._cursor = start
            self._after_edit()

    def _kill_to_line_end(self) -> None:
        """Ctrl+K: kill from the cursor to the end of the logical line."""
        _start, end = ek.line_bounds(self._buffer, self._cursor)
        if end > self._cursor:
            self._buffer = self._buffer[: self._cursor] + self._buffer[end:]
            self._after_edit()

    def _insert_text(self, text: str, typed: bool = True) -> None:
        self._buffer = (
            self._buffer[: self._cursor] + text + self._buffer[self._cursor :]
        )
        self._cursor += len(text)
        self._after_edit(typed=typed)

    def _insert_paste(self, payload: str) -> None:
        """Insert a completed bracketed paste (classic classification)."""
        try:
            _kind, text = classify_paste(payload)
        except Exception:
            logger.debug("paste classification failed", exc_info=True)
            text = payload
        if text:
            # Paste is programmatic: no completion query — not during
            # assembly, and not for the completed buffer state either.
            self._insert_text(text, typed=False)
        else:
            self._repaint()

    def _after_edit(self, typed: bool = True) -> None:
        """Common post-edit bookkeeping.

        ``typed`` edits (keystrokes: insert/backspace/delete/kills)
        re-query completion; programmatic mutations (paste) close the
        menu instead — which also invalidates in-flight queries. Tab
        force-open works either way (it doesn't come through here).
        """
        self._history.reset()
        if typed:
            self._notify_completion()
        else:
            self._close_completion()
        self._repaint()

    def _notify_completion(self) -> None:
        if self._completion is not None:
            try:
                self._completion.on_edit(self._buffer, self._cursor)
            except Exception:
                logger.debug("completion on_edit failed", exc_info=True)

    def _completion_open(self) -> bool:
        return self._completion is not None and self._completion.is_open()

    def _close_completion(self) -> None:
        if self._completion is not None:
            try:
                self._completion.close()
            except Exception:
                logger.debug("completion close failed", exc_info=True)

    def _set_completion_suppressed(self, suppressed: bool) -> None:
        if self._completion is not None:
            try:
                self._completion.set_suppressed(suppressed)
            except Exception:
                logger.debug("completion suppress failed", exc_info=True)

    def _toggle_multiline(self) -> None:
        self._multiline = not self._multiline
        self._repaint()

    def _resolve_esc_timeout(self) -> None:
        """Bare-ESC resolution: close menu / cancel search, clear pending."""
        if self._esc_pending_at is None:
            return
        if self._now() - self._esc_pending_at > self._esc_timeout:
            self._esc_pending_at = None
            if self._rsearch.active:
                self._rsearch.cancel()
                self._set_completion_suppressed(False)
                self._repaint()
            elif self._completion_open():
                self._close_completion()

    # =========================================================================
    # Internals — submission + repaint
    # =========================================================================

    def _submit(self, mode: str) -> Optional[str]:
        """Route the buffer; returns a transcript feedback line, if any."""
        text = self._buffer
        self._buffer = ""
        self._cursor = 0
        self._close_completion()
        self._repaint()

        stripped = text.strip()
        if not stripped:
            return None

        try:
            self._history.record_submit(text)
        except Exception:
            logger.debug("history record failed", exc_info=True)

        router = self._router
        if router is not None:
            try:
                feedback = router(text, mode)
            except Exception:
                logger.debug("submit router failed", exc_info=True)
                feedback = None
        else:
            feedback = self.route_default(text, mode)

        for listener in list(self._submit_listeners):
            try:
                listener(stripped, mode)
            except Exception:
                logger.debug("submit listener failed", exc_info=True)
        return feedback

    def route_default(self, text: str, mode: str) -> Optional[str]:
        """Built-in mid-run routing: slash → command queue, else steer."""
        stripped = text.strip()
        if not stripped:
            return None
        if stripped.startswith("/"):
            # Fast path: /steer hands its text straight to the now-queue.
            # Routing it through the command drain would PAUSE the agent
            # just to request a steer (plus pause/resume transcript noise)
            # — the exact opposite of "interrupt ASAP".
            steer_text = _parse_steer_command(stripped)
            if steer_text is not None:
                if not steer_text:
                    return "Usage: /steer <message>"
                try:
                    self._resolve_controller().request_steer(steer_text, mode="now")
                except Exception:
                    logger.debug("steer fast path failed", exc_info=True)
                # No ack: the steer history processor announces the
                # injection when the text actually reaches the model.
                return None
            # Other slash commands are runtime concerns (drained by
            # run_ui) — they must NOT reach the PauseController queues.
            self._command_queue.put(stripped)
            return None
        try:
            self._resolve_controller().request_steer(text, mode=mode)
        except Exception:
            # Never let a broken controller kill the listener thread.
            logger.debug("request_steer failed", exc_info=True)
            return None
        if mode == "queue":
            # Queued steers get no later confirmation, so ack at submit time.
            return f"⏭ queued for next turn: {stripped[:60]}"
        # "now" steers: stay quiet here. The steer history processor emits
        # "Injecting steer mid-turn — model will see: ..." when the text
        # actually reaches the model; acking at submit time too was a lie
        # (nothing has been injected yet) and doubled up the transcript.
        return None

    @staticmethod
    def _emit_feedback(note: str) -> None:
        """Best-effort transcript line for a successful steer submission."""
        try:
            from code_puppy.messaging.message_queue import emit_info

            emit_info(note)
        except Exception:
            logger.debug("feedback emit failed", exc_info=True)

    def _repaint(self) -> None:
        try:
            bar = self._resolve_bar()
            if self._rsearch.active:
                text = self._rsearch.prompt_text()
                bar.set_prompt_text("", text, len(text))
                return
            # "[multiline] " suffix has no SGR entries: extra chars paint plain.
            prefix = self._prompt_prefix + ("[multiline] " if self._multiline else "")
            # Attachment paths render as friendly tags ([png image]) —
            # display only; the buffer keeps the real path for submit.
            display_text, display_cursor = to_display(self._buffer, self._cursor)
            bar.set_prompt_text(
                prefix, display_text, display_cursor, self._prompt_prefix_sgrs
            )
        except Exception:
            # Painting is best-effort; the buffer state is the truth.
            pass

    def _resolve_bar(self):
        return self._bar if self._bar is not None else get_bottom_bar()

    def _resolve_controller(self):
        if self._pause_controller is not None:
            return self._pause_controller
        return get_pause_controller()


def _parse_steer_command(stripped: str) -> Optional[str]:
    """'/steer fix it' -> 'fix it'; bare '/steer' -> ''; not steer -> None."""
    if stripped == "/steer":
        return ""
    if stripped.startswith("/steer "):
        return stripped[len("/steer ") :].strip()
    return None


__all__ = [
    "DEFAULT_ESC_TIMEOUT",
    "RunningLineEditor",
    "SubmitListener",
    "SubmitRouter",
]
