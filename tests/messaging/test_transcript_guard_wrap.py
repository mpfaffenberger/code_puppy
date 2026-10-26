"""Regression: deferred autowrap must survive the scrollback dance.

Windows Terminal discards lines scrolled out of a DECSTBM region, so the
bottom bar performs a "dance" (margins off -> rewrite -> margins back) to
push real history. Step 4 of that dance repositions with CUP -- and CUP
CLEARS the terminal's deferred-autowrap flag (the xterm "last column
flag").

When streaming text parked the cursor in the last column, that pending
wrap was silently dropped: the next printable character overwrote the
glyph sitting in the last column instead of wrapping past it. The result
was one eaten character and a one-cell shift for the rest of the line --
``filters`` rendering as ``fite rs`` -- always at a wrapped-line boundary.

These tests render the bar's real escape output through a small VT screen
and compare against an unguarded terminal fed the identical bytes. The
guard's whole contract is to be visually indistinguishable from that
reference while also preserving scrollback, so the reference is the honest
oracle: it encodes no assumptions of our own about where wraps belong.

The emulator below is deliberately inline and stdlib-only. It implements
just the subset the bar emits (CUP, EL/ED, DECSTBM, LF/CR, SGR as a no-op)
plus the one behaviour under test -- deferred autowrap -- so these tests
add no new dependency to the suite.
"""

import io

import pytest
from rich.cells import get_character_cell_size

from code_puppy.messaging.bottom_bar import BottomBar

COLS, ROWS = 40, 12

# Long enough to wrap several times at COLS=40, and deliberately shaped so
# a dropped wrap corrupts a word rather than a space.
SENTENCE = (
    "The filters and columns are what make these reports right or wrong. "
    "So: get both reports producing correct rows first, export to Excel, "
    "and count there. COUNTA on deduped Reference #, a pivot for buckets."
)


class VTScreen:
    """Minimal VT screen with correct deferred-autowrap semantics.

    Only the escapes the bottom bar actually emits are implemented. The
    important contract -- and the one the fix is about -- is that printing
    into the last column parks the cursor there and sets ``wrap_pending``
    instead of wrapping immediately, and that any CUP clears that flag.
    """

    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.buf = [[" "] * cols for _ in range(rows)]
        self.row = self.col = 1  # 1-based, like the escapes
        self.wrap_pending = False
        self.top, self.bottom = 1, rows  # scroll margins
        self.saved = None  # DECSC / DECRC cursor stash

    # -- helpers ----------------------------------------------------------

    def _blank(self):
        return [" "] * self.cols

    def _scroll_up(self):
        """Scroll the margin region up one line (content above is history)."""
        del self.buf[self.top - 1]
        self.buf.insert(self.bottom - 1, self._blank())

    def _line_feed(self):
        if self.row >= self.bottom:
            self._scroll_up()
        else:
            self.row += 1

    def _put(self, ch, width):
        self.buf[self.row - 1][self.col - 1] = ch
        # A double-width glyph owns the next cell too; mark the continuation
        # so joining a row back into text does not invent a stray space.
        for pad in range(1, width):
            if self.col - 1 + pad < self.cols:
                self.buf[self.row - 1][self.col - 1 + pad] = ""

    # -- the parser -------------------------------------------------------

    def feed(self, text):  # noqa: C901 - a terminal is inherently branchy
        i, n = 0, len(text)
        while i < n:
            ch = text[i]

            if ch == "\x1b":
                if i + 1 >= n:
                    return  # incomplete escape; ignore the tail
                kind = text[i + 1]
                if kind == "[":  # CSI
                    j = i + 2
                    while j < n and not ("\x40" <= text[j] <= "\x7e"):
                        j += 1
                    if j >= n:
                        return
                    self._csi(text[j], text[i + 2 : j])
                    i = j + 1
                    continue
                if kind == "]":  # OSC -- skip to BEL or ST
                    j = i + 2
                    while j < n:
                        if text[j] == "\x07":
                            j += 1
                            break
                        if text[j] == "\x1b" and j + 1 < n and text[j + 1] == "\\":
                            j += 2
                            break
                        j += 1
                    i = j
                    continue
                if kind == "7":  # DECSC -- save cursor
                    self.saved = (self.row, self.col, self.wrap_pending)
                    i += 2
                    continue
                if kind == "8":  # DECRC -- restore cursor
                    if self.saved is not None:
                        self.row, self.col, self.wrap_pending = self.saved
                    i += 2
                    continue
                if kind in "()*+":  # charset designation: ESC ( B
                    i += 3
                    continue
                i += 2  # any other single-byte escape: inert
                continue

            if ch == "\n":
                self.col, self.wrap_pending = 1, False
                self._line_feed()
            elif ch == "\r":
                self.col, self.wrap_pending = 1, False
            elif ch < " " or ch == "\x7f":
                pass  # BEL and friends: zero width
            else:
                width = get_character_cell_size(ch)
                if width > 0:
                    if self.wrap_pending or self.col + width - 1 > self.cols:
                        self.col, self.wrap_pending = 1, False
                        self._line_feed()
                    self._put(ch, width)
                    self.col += width
                    if self.col > self.cols:
                        self.col, self.wrap_pending = self.cols, True
            i += 1

    def _csi(self, final, params):
        raw = params.lstrip("?>=")
        parts = raw.split(";")

        def arg(idx, default):
            try:
                return int(parts[idx]) if parts[idx] else default
            except (IndexError, ValueError):
                return default

        if final in "Hf":  # CUP -- and it CLEARS the deferred wrap
            self.row = max(1, min(self.rows, arg(0, 1)))
            self.col = max(1, min(self.cols, arg(1, 1)))
            self.wrap_pending = False
        elif final == "r":  # DECSTBM
            if raw:
                self.top, self.bottom = arg(0, 1), arg(1, self.rows)
            else:
                self.top, self.bottom = 1, self.rows
            self.row, self.col = 1, 1  # margins home the cursor
            self.wrap_pending = False
        elif final == "K":  # erase in line
            mode = arg(0, 0)
            row = self.buf[self.row - 1]
            span = (
                range(self.col - 1, self.cols)
                if mode == 0
                else range(0, self.col)
                if mode == 1
                else range(0, self.cols)
            )
            for c in span:
                row[c] = " "
        elif final == "J":  # erase in display (only "all" is used)
            if arg(0, 0) == 2:
                self.buf = [self._blank() for _ in range(self.rows)]
        # SGR ('m'), sync (?2026h/l), cursor show/hide: no geometry effect.

    # -- readout ----------------------------------------------------------

    @property
    def display(self):
        return ["".join(row) for row in self.buf]


class Tap(io.StringIO):
    """TTY-shaped stream that feeds every write into the emulator."""

    def __init__(self, feed):
        super().__init__()
        self._feed = feed

    def isatty(self):
        return True

    def write(self, s):
        self._feed(s)
        return len(s)


def visible(screen):
    """Non-blank rows, trailing pad removed."""
    return [line.rstrip() for line in screen.display if line.strip()]


def guarded_rows(chunks, cols=COLS, rows=ROWS):
    """Stream ``chunks`` through a started BottomBar onto a virtual screen."""
    screen = VTScreen(cols, rows)
    bar = BottomBar(stream=Tap(screen.feed), get_size=lambda: (cols, rows))
    bar.start()
    # Force the dance path: park the transcript on the region's last row so
    # every subsequent write has to scroll.
    top = rows - bar._reserved
    screen.feed(f"\x1b[{top};1H")
    bar._sim_row, bar._sim_col = top, 1
    bar._sim_pending, bar._sim_real_flag = False, True
    for chunk in chunks:
        bar.guarded_write(chunk)
    return visible(screen)


def reference_rows(text, cols=COLS, rows=ROWS, reserved=2):
    """Oracle: the same text on a plain terminal, no bar and no guard."""
    screen = VTScreen(cols, rows)
    screen.feed(f"\x1b[{rows - reserved};1H")
    screen.feed(text)
    return visible(screen)


def chunk_text(text, size):
    return [text[i : i + size] for i in range(0, len(text), size)]


class TestWrapAcrossDance:
    @pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 13, 40])
    def test_streamed_text_matches_unguarded_terminal(self, size):
        """No character is eaten regardless of how the stream is split.

        Chunk size decides where a dance lands relative to the last
        column, so sweeping it is what exposes the dropped wrap.
        """
        assert guarded_rows(chunk_text(SENTENCE, size)) == reference_rows(SENTENCE)

    @pytest.mark.parametrize("cols", [24, 31, 40, 57, 80])
    def test_matches_unguarded_terminal_at_any_width(self, cols):
        """Terminal width shifts the wrap points; all must stay intact."""
        got = guarded_rows(chunk_text(SENTENCE, 3), cols=cols)
        assert got == reference_rows(SENTENCE, cols=cols)

    def test_glyph_in_last_column_survives(self):
        """Pin the exact failure: a wrap pending when the dance fires.

        Byte-for-byte, the pre-fix output dropped the final column's glyph
        and shifted the remainder left by one cell.
        """
        filler = "x" * (COLS - 1)
        # Land 'A' exactly in the last column, then force a dance.
        rows_ = guarded_rows([filler, "A", "B" * (COLS * 3)])
        joined = "".join(rows_)
        assert "A" in joined, "last-column glyph was eaten by the dance"
        assert joined.count("B") == COLS * 3

    def test_wide_glyphs_are_not_split(self):
        """Double-width CJK must wrap whole; the commit must not desync."""
        text = "\u5e83\u3044\u6587\u5b57" * 12
        assert guarded_rows(chunk_text(text, 3)) == reference_rows(text)

    def test_sgr_split_across_chunks(self):
        """Colour codes straddling chunk boundaries stay intact.

        The guard withholds incomplete escapes in ``_carry``; the wrap
        commit must not be injected into the middle of one.
        """
        text = "\x1b[36m" + SENTENCE[:90] + "\x1b[0m" + SENTENCE[90:]
        assert guarded_rows(chunk_text(text, 3)) == reference_rows(text)

    def test_explicit_newlines_still_break_lines(self):
        """The commit must not swallow or duplicate real line breaks.

        CRLF is used deliberately. The guard models a bare ``\\n`` as CR+LF
        because Python's text-mode streams perform that translation on
        Windows before the console ever sees it; this test feeds the
        emulator directly, so writing CRLF is what keeps the guard and the
        reference describing the same bytes.
        """
        text = SENTENCE[:60] + "\r\n" + SENTENCE[60:120] + "\r\n" + SENTENCE[120:]
        assert guarded_rows(chunk_text(text, 3)) == reference_rows(text)
