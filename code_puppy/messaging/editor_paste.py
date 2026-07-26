"""Bracketed paste for the persistent raw editor (Phase B, feature 4).

The bottom bar enables ``ESC[?2004h`` while it owns input (disabled on
suspend/stop alongside DECTCEM). Terminals then wrap pastes in
``ESC[200~ ... ESC[201~``; the editor detects the opener as a CSI
sequence and streams every following byte into :class:`PasteBuffer`
until the closer — atomically, even when the payload is split across
multiple ``read()`` chunks.

Classification mirrors the classic path's ``handle_bracketed_paste`` in
``command_line.prompt_toolkit_completion`` (source of truth — logic
replicated because it's an inline closure there; helpers are imported):

* meaningful text → normalize CRLF/CR to LF, insert at the cursor;
* empty/whitespace-only → check the clipboard for an image; if present,
  capture it to the pending-images manager and insert its placeholder;
* whitespace-only fallback → paste the whitespace.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

#: Terminator sequence inside the paste stream.
PASTE_END = "\x1b[201~"


class PasteBuffer:
    """Assembles one bracketed-paste payload from per-char feeds."""

    def __init__(self) -> None:
        self.active = False
        self._buf: str = ""

    def start(self) -> None:
        self.active = True
        self._buf = ""

    def feed(self, ch: str) -> Optional[str]:
        """Feed one char; returns the completed payload at the closer."""
        if not self.active:
            return None
        self._buf += ch
        if self._buf.endswith(PASTE_END):
            payload = self._buf[: -len(PASTE_END)]
            self.active = False
            self._buf = ""
            return payload
        return None

    def abort(self) -> str:
        """Bail out (e.g. editor teardown); returns whatever accumulated."""
        payload = self._buf
        self.active = False
        self._buf = ""
        return payload


def classify_paste(payload: str) -> Tuple[str, str]:
    """Map a paste payload to an insertion, classic-path semantics.

    Returns ``(kind, text_to_insert)`` where kind is ``"text"`` or
    ``"image"`` (text_to_insert is then the clipboard placeholder).
    Never raises.
    """
    if payload and payload.strip():
        return ("text", _normalize(payload))

    # No meaningful text — try capturing a clipboard image directly
    # (Windows image paste sends an empty bracketed paste). ONE clipboard
    # read: a separate "has image?" probe would double the (slow,
    # osascript-backed on macOS) round-trip.
    try:
        from code_puppy.command_line.clipboard import (
            capture_clipboard_image_to_pending,
        )

        placeholder = capture_clipboard_image_to_pending()
        if placeholder:
            return ("image", placeholder + " ")
    except Exception:
        logger.debug("clipboard image check failed", exc_info=True)

    # Fallback: whitespace-only data still gets pasted.
    return ("text", _normalize(payload or ""))


def _normalize(text: str) -> str:
    """Windows line endings → Unix (same as the classic handler)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_clipboard_smart() -> Tuple[str, str]:
    """Ctrl+V fallback: auto-detect image vs text in the clipboard.

    Returns ``(kind, text_to_insert)``: ``("image", placeholder)`` via
    the pending-images flow, ``("text", normalized)``, or
    ``("none", "")`` for an empty/unreadable clipboard. Never raises.
    Image detection + capture REUSE ``command_line.clipboard`` helpers;
    the text read REPLICATES the classic ``handle_smart_paste`` closure
    in ``prompt_toolkit_completion`` (source of truth — it's inline
    there and can't be imported without refactoring command_line/).

    NOTE: clipboard reads shell out (pbpaste/xclip/powershell) — callers
    must run this OFF the key-listener thread (run_ui hops to the loop's
    executor, like completion queries).
    """
    try:
        from code_puppy.command_line.clipboard import (
            capture_clipboard_image_to_pending,
        )

        placeholder = capture_clipboard_image_to_pending()
        if placeholder:
            return ("image", placeholder + " ")
    except Exception:
        logger.debug("clipboard image check failed", exc_info=True)

    text = _read_clipboard_text()
    if text:
        return ("text", _normalize(text).rstrip("\n"))
    return ("none", "")


def _read_clipboard_text():
    """Platform text-clipboard read (classic handle_smart_paste logic)."""
    import platform
    import subprocess

    try:
        system = platform.system()
        if system == "Darwin":
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout
        elif system == "Windows":
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout
        else:
            for cmd in (
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
            ):
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0:
                        return result.stdout
                except FileNotFoundError:
                    continue
    except Exception:
        logger.debug("clipboard text read failed", exc_info=True)
    return None


__all__ = ["PASTE_END", "PasteBuffer", "classify_paste", "read_clipboard_smart"]
