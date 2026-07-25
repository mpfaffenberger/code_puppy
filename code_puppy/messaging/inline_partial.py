"""Partial-line tracking for the inline prompt surface.

:class:`PartialLineTracker` models what the transcript's current
(unfinished) line looks like on screen: its rendered cell width and the
stream's SGR styling state. ``InlineBottomBar`` uses this to repaint the
prompt block BELOW a mid-stream partial line and hop the cursor back
into it with relative moves — keeping the prompt visible while a
paragraph streams.

The tracker fails closed: anything whose width can't be modelled (tabs,
backspaces, cursor-moving escapes, escape sequences split across write
boundaries, absurdly long lines) poisons :attr:`ok` until the next line
break, and the surface falls back to its hidden+debounce behavior.
Wrong-but-confident width math would corrupt the transcript; "I don't
know" never does.
"""

from __future__ import annotations

import re
from typing import Optional

from rich.cells import cell_len

#: Escape sequences that occupy no cells -- ignored when deciding whether
#: the transcript cursor rests at column 1 (CSI, OSC, other ESC-prefixed).
ANSI_RE = re.compile(
    r"\x1b\[[0-9;?<=> ]*[@-~]"  # CSI (SGR, cursor moves, ...)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (hyperlinks, titles)
    r"|\x1b[@-Z\\-_]"  # other C1-style ESC sequences
)

#: SGR sequences (colors/attributes) -- tracked so a mid-line bar repaint
#: can replay the stream's styling state after hopping the cursor back.
_SGR_RE = re.compile(r"\x1b\[([0-9;:]*)m")

#: Tracking caps: beyond these the width/SGR bookkeeping is abandoned
#: for the current line (fail closed to hidden+debounce).
_PARTIAL_TRACK_MAX_CHARS = 2048
_SGR_TRACK_MAX_CHARS = 256


class PartialLineTracker:
    """Rendered width + SGR state of the transcript's current line."""

    def __init__(self) -> None:
        self.text = ""  # visible content of the current (last) line
        self.ok = True  # width tracking trustworthy?
        self.sgr = ""  # accumulated SGR state since the last reset

    def feed(self, chunk: str) -> None:
        """Account one foreign write's worth of transcript output."""
        self._feed_sgr(chunk)
        # Cell-width tracking for the LAST (current) partial line.
        line_break = max(chunk.rfind("\n"), chunk.rfind("\r"))
        if line_break >= 0:
            self.reset_line()
            raw_tail = chunk[line_break + 1 :]
        else:
            raw_tail = chunk
        for match in ANSI_RE.finditer(raw_tail):
            seq = match.group(0)
            if seq.startswith("\x1b["):
                if seq.endswith("m"):
                    continue  # SGR: zero cells, tracked above
                if seq[-1] in "hl" and "?" in seq:
                    continue  # private mode toggles: zero cells
                self.ok = False  # cursor motion / clears
            elif seq.startswith("\x1b]"):
                continue  # OSC: zero cells
            else:
                self.ok = False  # DECSC & friends
        tail = ANSI_RE.sub("", raw_tail)
        if any(ch < " " or ch == "\x7f" for ch in tail):
            # Tabs/backspaces/split escapes: width unknowable this line.
            self.ok = False
            tail = "".join(ch for ch in tail if ch >= " " and ch != "\x7f")
        self.text += tail
        if len(self.text) > _PARTIAL_TRACK_MAX_CHARS:
            self.ok = False

    def _feed_sgr(self, chunk: str) -> None:
        """SGR state is terminal-global; scan the whole chunk. A reset
        (bare ``m``, ``0m`` or ``0;...m``) restarts the accumulation."""
        for match in _SGR_RE.finditer(chunk):
            params = match.group(1)
            if params in ("", "0") or params.startswith(("0;", "0:")):
                self.sgr = match.group(0)
            else:
                self.sgr += match.group(0)
        if len(self.sgr) > _SGR_TRACK_MAX_CHARS:
            self.sgr = ""  # runaway styling: replay reset-only

    def reset_line(self) -> None:
        """The cursor reached a fresh row (line break or explicit commit)."""
        self.text = ""
        self.ok = True

    def extended(self, chunk: str, cols: int) -> Optional["PartialLineTracker"]:
        """A fed copy of this tracker IF ``chunk`` merely extends the
        current line in place: no line breaks, tracking still
        trustworthy, the cursor stays on the same terminal row AND out
        of the wrap-margin danger zone. ``None`` otherwise.

        This is the streaming fast path's admission test: an in-place
        extension means the painted bar below the line doesn't move, so
        the surface can pass the text straight through — zero escapes,
        zero repaints, zero flicker.
        """
        if not self.ok or cols < 8 or "\n" in chunk or "\r" in chunk:
            return None
        clone = PartialLineTracker()
        clone.text, clone.ok, clone.sgr = self.text, self.ok, self.sgr
        clone.feed(chunk)
        if not clone.ok:
            return None
        if cell_len(clone.text) // cols != cell_len(self.text) // cols:
            return None  # crosses a row boundary: the bar must move down
        if clone.restore_col(cols) is None:
            return None  # margin danger zone / untrustworthy hop
        return clone

    def restore_col(self, cols: int) -> Optional[int]:
        """Cell column (0-based) of the partial line's end, or ``None``
        when it can't be trusted.

        Bails near the wrap margin: an exact-margin column loses the
        terminal's pending-wrap flag on hop-back, and a wide glyph two
        cells out may have wrapped early — both would desync the hop.
        """
        if not self.ok or cols < 8:
            return None
        col = cell_len(self.text) % cols
        if self.text and (col == 0 or col >= cols - 2):
            return None
        return col

    @property
    def sgr_replay(self) -> str:
        """Escape string that restores the stream's styling after a hop."""
        return "\x1b[0m" + self.sgr


__all__ = ["ANSI_RE", "PartialLineTracker"]
