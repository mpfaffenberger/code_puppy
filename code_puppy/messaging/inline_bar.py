"""Inline prompt surface for terminals that mishandle DECSTBM.

Unlike :class:`bottom_bar.BottomBar`, this surface never establishes scroll
margins or paints at absolute screen rows.  It keeps the live UI at the normal
terminal cursor, erases it before transcript output, then redraws it below the
new output.  The public API intentionally matches ``BottomBar`` so the editor
and status/panel plugins do not need terminal-specific branches.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .bar_rendering import (
    CLEAR_LINE,
    CURSOR_HIDE,
    CURSOR_SHOW,
    WRAP_OFF,
    WRAP_ON,
    render_prompt_block,
    sanitize,
)
from .bottom_bar import PANEL_MAX_ROWS, POPUP_MAX_ROWS, BottomBar


class InlineBottomBar(BottomBar):
    """A DECSTBM-free prompt surface for embedded terminal emulators."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._displayed_rows = 0
        self._output_depth = 0

    def start(self) -> None:
        if not self._is_tty():
            return
        with self._lock:
            if self._active:
                return
            self._active = True
            self._cols, self._rows = self._safe_size()
            self._write(CURSOR_HIDE)
            self._paint_inline()
        self._install_sigwinch()
        self._register_atexit()

    def stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._erase_inline()
            self._write(CURSOR_SHOW)
            self._active = False
            self._displayed_rows = 0

    def _sync_reserved(self, _painter) -> None:
        """Repaint cached state without creating a terminal scroll region."""
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return
        self._ensure_inline_geometry()
        self._erase_inline()
        self._paint_inline()

    def notify_transcript_output(self) -> None:
        """Retain popup-slack semantics; erasing is owned by the transaction."""
        with self._lock:
            if self._popup_slack:
                self._popup_slack -= 1

    @contextmanager
    def output_transaction(self) -> Iterator[None]:
        """Atomically remove the live UI, allow output, then redraw it."""
        with self._lock:
            outermost = self._output_depth == 0
            self._output_depth += 1
            if outermost and self._active and self._suspend_depth == 0:
                self.notify_transcript_output()
                self._erase_inline()
            try:
                yield
            finally:
                self._output_depth -= 1
                if outermost and self._active and self._suspend_depth == 0:
                    self._ensure_inline_geometry()
                    self._paint_inline()

    @contextmanager
    def suspended(self) -> Iterator[None]:
        if not self._is_tty():
            yield
            return
        with self._lock:
            self._suspend_depth += 1
            if self._suspend_depth == 1 and self._active:
                self._erase_inline()
        try:
            yield
        finally:
            with self._lock:
                self._suspend_depth -= 1
                if self._suspend_depth == 0 and self._active:
                    self._paint_inline()

    def set_panel_lines(self, lines) -> None:
        from rich.text import Text

        cleaned = [
            line.copy() if isinstance(line, Text) else sanitize(str(line))
            for line in (lines or [])
        ][:PANEL_MAX_ROWS]
        with self._lock:
            self._panel_lines = cleaned
            self._sync_reserved(None)

    def set_popup_lines(self, lines, selected: int = -1) -> None:
        cleaned = [sanitize(str(line)) for line in (lines or [])][:POPUP_MAX_ROWS]
        with self._lock:
            self._popup_lines = cleaned
            self._popup_selected = selected
            self._popup_slack = 0
            self._sync_reserved(None)

    def _ensure_inline_geometry(self) -> None:
        cols, rows = self._safe_size()
        self._cols, self._rows = cols, rows

    def _inline_lines(self) -> list[str]:
        lines: list[str] = []
        panel = [] if self._popup_lines else self._panel_lines
        for line in panel:
            lines.append(sanitize(line.plain if hasattr(line, "plain") else str(line)))

        prompt_rows, _ = render_prompt_block(
            self._prompt_prefix,
            self._prompt_buffer,
            self._prompt_cursor,
            self._cols,
            5,
            prefix_sgrs=self._prompt_prefix_sgrs,
        )
        lines.extend(prompt_rows)

        for index, line in enumerate(self._popup_lines):
            marker = "› " if index == self._popup_selected else "  "
            lines.append(f"{marker}{line}")

        status = f"{self._status_prefix}{self._status}{self._status_suffix}"
        if status:
            lines.append(sanitize(status))
        return lines or [""]

    def _paint_inline(self) -> None:
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return
        lines = self._inline_lines()
        parts = [WRAP_OFF]
        for index, line in enumerate(lines):
            if index:
                parts.append("\r\n")
            parts.append(f"{CLEAR_LINE}{line}")
        if len(lines) > 1:
            parts.append(f"\x1b[{len(lines) - 1}A")
        parts.extend(["\r", WRAP_ON])
        self._write("".join(parts))
        self._displayed_rows = len(lines)

    def _erase_inline(self) -> None:
        if not self._displayed_rows:
            return
        parts = [WRAP_OFF, "\r"]
        for index in range(self._displayed_rows):
            if index:
                parts.append("\x1b[1B\r")
            parts.append(CLEAR_LINE)
        if self._displayed_rows > 1:
            parts.append(f"\x1b[{self._displayed_rows - 1}A")
        parts.extend(["\r", WRAP_ON])
        self._write("".join(parts))
        self._displayed_rows = 0

    def _emergency_restore(self) -> None:
        try:
            with self._lock:
                if self._active:
                    self._erase_inline()
                self._write(CURSOR_SHOW)
                self._active = False
        except Exception:
            pass
