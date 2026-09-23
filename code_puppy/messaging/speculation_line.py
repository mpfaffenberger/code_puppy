"""Optional pinned speculation row above the identity and context rows."""

from __future__ import annotations

from rich.text import Text

from .bar_rendering import (
    CLEAR_LINE,
    RESTORE_CURSOR,
    SAVE_CURSOR,
    WRAP_OFF,
    WRAP_ON,
    clip_cells,
    dim,
    render_styled_line,
    sanitize,
)


class SpeculationLineMixin:
    """Paint localized stats without changing the existing status slots."""

    def set_speculation_status(self, text: Text | str | None) -> None:
        """Enable a stats row, or collapse it when text is None or empty.

        A ``Text`` keeps its program-generated styles (rendered through the
        trusted-style path); a plain string is sanitized and painted dim.
        """
        status: Text | str
        if isinstance(text, Text):
            status = text if text.plain.strip() else ""
        else:
            status = sanitize(text) if text is not None else ""
        with self._lock:
            if status == self._speculation_status:
                return
            self._speculation_status = status
            self._sync_reserved(self._speculation_seq)

    def _speculation_visible(self) -> bool:
        return bool(self._speculation_status)

    def _render_speculation_line(self, width: int) -> str:
        status = self._speculation_status
        if isinstance(status, Text):
            return render_styled_line(status, width)
        return dim(clip_cells(status, width))

    def _speculation_seq(self) -> str:
        """Paint directly above the bottom identity and context rows."""
        if not self._speculation_visible():
            return ""
        row = self._rows - int(self._status_visible()) - self._identity_row_count()
        text = self._render_speculation_line(self._cols)
        return (
            f"{SAVE_CURSOR}{WRAP_OFF}"
            f"\x1b[{row};1H{CLEAR_LINE}{text}"
            f"{WRAP_ON}{RESTORE_CURSOR}"
        )
