"""Pure text/escape helpers for the bottom bar (no I/O, no state).

Split out of ``bottom_bar.py`` to respect the 600-line cap: everything
here is a deterministic function of its inputs — sanitization, cell-width
clipping, and the prompt-row renderer. The stateful scroll-region
machinery stays in :mod:`code_puppy.messaging.bottom_bar`.
"""

from __future__ import annotations

import shutil
import unicodedata
from typing import List, Optional, Tuple

from rich.cells import cell_len, chop_cells

# =============================================================================
# Escape constants
# =============================================================================

SAVE_CURSOR = "\x1b7"  # DECSC
RESTORE_CURSOR = "\x1b8"  # DECRC
RESET_REGION = "\x1b[r"  # DECSTBM with no args = full screen
CLEAR_LINE = "\x1b[2K"
REVERSE_ON = "\x1b[7m"
REVERSE_OFF = "\x1b[27m"
WRAP_OFF = "\x1b[?7l"  # DECAWM off: belt-and-braces against row bleed
WRAP_ON = "\x1b[?7h"
CURSOR_HIDE = "\x1b[?25l"  # DECTCEM: the prompt row paints its own
CURSOR_SHOW = "\x1b[?25h"  # pseudo-cursor; the hardware one must not blink
PASTE_ON = "\x1b[?2004h"  # bracketed paste while the bar owns input
PASTE_OFF = "\x1b[?2004l"
# xterm modifyOtherKeys level 1: encodes otherwise-ambiguous modified
# keys (Shift+Enter!) as CSI 27;m;13~ without touching normal typing,
# Ctrl+letters or arrows; unsupporting terminals ignore it. Level 2 /
# kitty CSI >1u are deliberately NOT used — they re-encode ESC itself
# and would fight the editor's ESC state machine.
MODKEYS_ON = "\x1b[>4;1m"
MODKEYS_OFF = "\x1b[>4;0m"


def default_get_size() -> Tuple[int, int]:
    """Best-effort ``(columns, rows)`` for the controlling terminal."""
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return max(1, size.columns), max(1, size.lines)
    except Exception:
        return 80, 24


def sanitize(text: str) -> str:
    """Strip control + format characters that could corrupt reserved rows.

    The status/prompt/panel rows are painted with raw positioning
    escapes, so any control character smuggled in via user- or
    MODEL-controlled text (agent names!) could corrupt the reserved rows
    — or break out of them entirely. Removed:

    * C0 controls + DEL (``\\x00``-``\\x1f``, ``\\x7f``) — incl. ESC.
    * C1 controls (``\\x80``-``\\x9f``) — incl. U+009B, the SINGLE-BYTE
      CSI that starts an escape sequence without an ESC prefix.
    * Unicode category ``Cf`` (format chars) — bidi overrides / ZWJ used
      for visual spoofing.
    """
    return "".join(
        ch
        for ch in text
        if ch >= " "
        and ch != "\x7f"
        and not ("\x80" <= ch <= "\x9f")
        and unicodedata.category(ch) != "Cf"
    )


def clip_cells(text: str, width: int) -> str:
    """Truncate ``text`` to at most ``width`` terminal CELLS (not chars).

    Emoji/CJK are 2 cells wide; slicing by code points lets them spill
    into the next reserved row.
    """
    if width <= 0:
        return ""
    if cell_len(text) <= width:
        return text
    chopped = chop_cells(text, width)
    return chopped[0] if chopped else ""


_STYLE_RESOLVER = None


def _style_resolver():
    """Lazy detached Console used ONLY to resolve Rich styles to segments.

    Writes to a throwaway StringIO -- it never touches the real terminal.
    ``force_terminal``/``truecolor`` so Style.render always produces SGRs
    regardless of the ambient TTY detection.
    """
    global _STYLE_RESOLVER
    if _STYLE_RESOLVER is None:
        import io

        from rich.console import Console

        _STYLE_RESOLVER = Console(
            file=io.StringIO(),
            force_terminal=True,
            color_system="truecolor",
            width=4096,
        )
    return _STYLE_RESOLVER


def render_styled_line(line, width: int) -> str:
    """Render a ``rich.text.Text`` row to a one-row ANSI string.

    Trusted-styles-only contract: SGR bytes are regenerated HERE from the
    Text's ``Style`` objects (program-generated, never model-controlled);
    every segment's *text* goes through :func:`sanitize`, so in-band
    escapes smuggled inside the content (agent names!) can never reach
    the terminal. Cell-clipped BEFORE styling, so SGR bytes never count
    as cells.
    """
    if width <= 0:
        return ""
    text = line.copy()
    text.truncate(width, overflow="ellipsis")
    parts: List[str] = []
    for segment in text.render(_style_resolver(), end=""):
        chunk = sanitize(segment.text)
        if not chunk:
            continue
        style = segment.style
        parts.append(style.render(chunk) if style else chunk)
    return "".join(parts)


def stylize_slice(text: str, start: Optional[int], sgrs: Optional[List[str]]) -> str:
    """Re-apply per-char SGR codes to a chopped row slice.

    ``sgrs`` is index-aligned with the sanitized PREFIX chars (see
    ``prompt_prefix_style.flatten_prompt_fragments``); ``start`` is this
    slice's char offset within logical line 0 (``None`` for rows from
    other logical lines — they never carry prefix chars). Applied AFTER
    cell-chopping, so SGR bytes never count as cells.
    """
    if not text or not sgrs or start is None or start >= len(sgrs):
        return text
    out: List[str] = []
    current = ""
    for idx, ch in enumerate(text):
        pos = start + idx
        sgr = sgrs[pos] if pos < len(sgrs) else ""
        if sgr != current:
            # Reset between runs so e.g. bold never bleeds across colors.
            out.append("\x1b[0m")
            if sgr:
                out.append(f"\x1b[{sgr}m")
            current = sgr
        out.append(ch)
    if current:
        out.append("\x1b[0m")
    return "".join(out)


def _prompt_visual_rows(prefix: str, buffer: str, cursor_pos: int, width: int) -> tuple:
    """Soft-wrap prompt content into visual rows (cell-accurate).

    Every LOGICAL line (split on ``\\n``) wraps into one or more visual
    rows of at most ``width`` cells (wide glyphs never split — rich's
    ``chop_cells`` does the cell math).

    The prefix may itself contain hard newlines (the prompt_newline
    plugin appends one so typed input starts below the chrome): every
    prefix line but the last paints as its own chrome row(s) ABOVE the
    input, and only the final prefix line rides the buffer's logical
    line 0. Each prefix ``\\n`` occupies an SGR slot (see
    ``prompt_prefix_style.flatten_prompt_fragments``), so ``row_offsets``
    index into the full newline-bearing prefix and stay SGR-aligned.

    Returns ``(rows, cursor_row, cursor_offset, row_offsets)``: ALL
    visual rows (uncapped), the index of the row holding the cursor, the
    cursor's char offset within that row, and each row's char offset
    within the prefix + logical line 0 (``None`` for rows of other
    logical lines — only prefix rows and line 0 carry styleable prefix
    chars). When the cursor sits past a row that exactly fills the
    width, it wraps onto a following (possibly empty) row — same as a
    real terminal.
    """
    width = max(1, width)
    buffer = buffer or ""
    cursor = max(0, min(cursor_pos, len(buffer)))
    prefix_lines = [sanitize(part) for part in (prefix or "").split("\n")]
    prefix_tail = prefix_lines[-1]
    logical = buffer.split("\n")
    before = buffer[:cursor]
    cur_line = before.count("\n")
    cur_col = len(before) - (before.rfind("\n") + 1)

    rows: list = []
    row_offsets: list = []
    cursor_row = 0
    cursor_offset = 0
    # Chrome rows: every prefix line except the last, offset-tracked
    # against the full prefix (the '\n' itself consumes one SGR slot).
    poff = 0
    for head in prefix_lines[:-1]:
        segments = chop_cells(head, width) or [""]
        for seg in segments:
            rows.append(seg)
            row_offsets.append(poff)
            poff += len(seg)
        poff += 1  # the newline's SGR slot
    for i, line in enumerate(logical):
        content = (prefix_tail if i == 0 else "") + sanitize(line)
        segments = chop_cells(content, width) or [""]
        if i == cur_line:
            offset = (len(prefix_tail) if i == 0 else 0) + cur_col
            acc = 0
            seg_idx = len(segments) - 1
            inner = len(segments[-1])
            for j, seg in enumerate(segments):
                is_last = j == len(segments) - 1
                if offset < acc + len(seg) or (is_last and offset <= acc + len(seg)):
                    seg_idx = j
                    inner = offset - acc
                    break
                acc += len(seg)
            # Cursor cell doesn't fit after an exactly-full row: it
            # wraps to the next visual row (create one if needed).
            seg = segments[seg_idx]
            if inner == len(seg) and cell_len(seg) + 1 > width:
                if seg_idx == len(segments) - 1:
                    segments.append("")
                seg_idx += 1
                inner = 0
            cursor_row = len(rows) + seg_idx
            cursor_offset = inner
        if i == 0:
            acc_off = poff  # line 0's prefix chars start after the chrome
            for seg in segments:
                row_offsets.append(acc_off)
                acc_off += len(seg)
        else:
            row_offsets.extend([None] * len(segments))
        rows.extend(segments)
    return rows, cursor_row, cursor_offset, row_offsets


def count_prompt_rows(prefix: str, buffer: str, cursor_pos: int, width: int) -> int:
    """Total soft-wrapped visual rows for the prompt content (uncapped)."""
    rows, _cr, _co, _ro = _prompt_visual_rows(prefix, buffer, cursor_pos, width)
    return len(rows)


def render_prompt_block(
    prefix: str,
    buffer: str,
    cursor_pos: int,
    width: int,
    max_rows: int,
    prefix_sgrs: Optional[List[str]] = None,
) -> tuple:
    """Render the soft-wrapped prompt viewport.

    Returns ``(painted_rows, cursor_row_offset)``: at most ``max_rows``
    visual rows (window chosen so the cursor's row stays visible; content
    beyond the cap scrolls within the viewport), with the cursor's row
    carrying the reverse-video pseudo-cursor. ``prefix_sgrs`` (per-char
    SGR codes for the prefix) recolors the prefix chars out-of-band —
    see :func:`stylize_slice`.
    """
    rows, cursor_row, cursor_offset, row_offsets = _prompt_visual_rows(
        prefix, buffer, cursor_pos, width
    )
    total = len(rows)
    visible = max(1, min(max_rows, total))
    start = 0
    if cursor_row >= visible:
        start = cursor_row - visible + 1
    start = min(start, max(0, total - visible))

    out = []
    for i in range(start, start + visible):
        row = rows[i]
        off = row_offsets[i]
        if i == cursor_row:
            at = row[cursor_offset] if cursor_offset < len(row) else " "
            before = stylize_slice(row[:cursor_offset], off, prefix_sgrs)
            after = stylize_slice(
                row[cursor_offset + 1 :],
                None if off is None else off + cursor_offset + 1,
                prefix_sgrs,
            )
            out.append(f"{before}{REVERSE_ON}{at}{REVERSE_OFF}{after}")
        else:
            out.append(stylize_slice(row, off, prefix_sgrs))
    return out, cursor_row - start


__all__ = [
    "CLEAR_LINE",
    "CURSOR_HIDE",
    "CURSOR_SHOW",
    "MODKEYS_OFF",
    "MODKEYS_ON",
    "PASTE_OFF",
    "PASTE_ON",
    "RESET_REGION",
    "RESTORE_CURSOR",
    "REVERSE_OFF",
    "REVERSE_ON",
    "SAVE_CURSOR",
    "WRAP_OFF",
    "WRAP_ON",
    "clip_cells",
    "count_prompt_rows",
    "default_get_size",
    "render_prompt_block",
    "render_styled_line",
    "sanitize",
    "stylize_slice",
]
