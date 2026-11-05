"""Height resizes must keep the transcript cursor where output ended.

Rendered through pyte, patched to behave like real terminals (xterm,
Ghostty/libghostty-vt as used by herdr, kitty, alacritty, ...) where
stock pyte differs:

* ``CSI r`` (DECSTBM reset form) homes the cursor, like every DECSTBM.
* A height shrink drops rows off the TOP (into scrollback) and the
  cursor moves up with its content, so the bottom-anchored bar band
  ends up on the new bottom rows rather than at its old row numbers.
* A height grow either adds blank rows below, or (Ghostty, alacritty)
  pulls scrollback back down, shifting content and cursor down.
* Both reset the scroll region.

The regression: a resize re-establish reset the region (cursor -> home)
and then saved "the writer position" wherever the ghost-clear loop left
the cursor. After a shrink of at least the band height the loop was
empty, so the saved position was row 1 and the next transcript lines
overwrote the screen top-down -- stale rows showing through every blank
line and the tails of longer old lines glued onto shorter new ones.
"""

import pytest

from code_puppy.messaging.bottom_bar import BottomBar
from tests.messaging.test_bottom_bar_screen import Tap, VTScreen, VTStream

COLS = 80
IDENTITY = "Boodler [agent] [model] (~/project)"


class RealTerminalScreen(VTScreen):
    """pyte with real-terminal DECSTBM-reset, scrollback and resize semantics."""

    def __init__(self, columns, lines, pull_on_grow=False):
        super().__init__(columns, lines)
        self.history = []
        self.pull_on_grow = pull_on_grow

    def set_margins(self, top=None, bottom=None):
        super().set_margins(top, bottom)
        if (top is None or top == 0) and bottom is None:
            self.cursor_position()  # CSI r homes too (VT100, xterm, Ghostty)

    def index(self):
        top, bottom = self.margins or (0, self.lines - 1)
        if top == 0 and self.cursor.y == bottom:
            self.history.append(self.buffer[0])  # scrolled into scrollback
        super().index()

    def _shift(self, delta):
        """Move every row by ``delta`` (rebuilt by hand: pyte's line ops
        skip never-written rows, leaving stale ones behind)."""
        moved = {y + delta: row for y, row in self.buffer.items() if y + delta >= 0}
        self.buffer.clear()
        self.buffer.update(moved)

    def resize(self, lines=None, columns=None):
        lines = lines or self.lines
        x, y = self.cursor.x, self.cursor.y
        self.margins = None  # terminals reset the scroll region on resize
        drop = max(0, self.lines - lines)
        if drop:
            self.history += [self.buffer[i] for i in range(drop)]
            self._shift(-drop)  # the oldest rows go to scrollback
            y = max(0, y - drop)  # the cursor follows its content up
            self.lines = lines
        pull = min(max(0, lines - self.lines), len(self.history))
        if self.pull_on_grow and pull:
            self._shift(pull)
            for i, row in enumerate(self.history[-pull:]):
                self.buffer[i] = row
            del self.history[-pull:]
            y += pull  # ... and down with it
        super().resize(lines, columns)
        self.cursor.x, self.cursor.y = x, min(y, self.lines - 1)


class ResizableTerm:
    def __init__(self, rows, pull_on_grow=False):
        self.size = [COLS, rows]
        self.screen = RealTerminalScreen(COLS, rows, pull_on_grow)
        self.stream = VTStream(self.screen)
        self.bar = BottomBar(
            stream=Tap(self.stream.feed), get_size=lambda: tuple(self.size)
        )

    def start(self):
        self.bar.start()
        self.bar.set_prompt_text(f"{IDENTITY} >>> ", "", 0)
        self.bar.set_status("Idle")

    def transcript(self, text):
        with self.bar.output_transaction():
            self.stream.feed(text + "\r\n")

    def resize(self, rows):
        self.screen.resize(lines=rows)
        self.size[1] = rows
        self.bar.set_status("Idle")  # any repaint re-polls the geometry

    def rows(self):
        return [line.rstrip() for line in self.screen.display]

    def row_of(self, text):
        matches = [i for i, row in enumerate(self.rows(), 1) if row == text]
        assert len(matches) == 1, f"{text!r} at rows {matches}: {self.rows()}"
        return matches[0]


@pytest.fixture
def term():
    made = []

    def make(rows, pull_on_grow=False):
        made.append(ResizableTerm(rows, pull_on_grow))
        return made[-1]

    yield make
    for t in made:
        t.bar.stop()


@pytest.mark.parametrize("new_rows", [24, 30, 37])
def test_shrink_keeps_output_adjacent_to_transcript_tail(term, new_rows):
    """Big shrinks (past the band height) used to home the writer to row 1."""
    t = term(40)
    t.start()
    for i in range(60):
        t.transcript(f"line {i:02d}")

    t.resize(new_rows)
    t.transcript("after resize")

    tail = t.row_of("line 59")
    assert t.row_of("after resize") == tail + 1
    # Nothing above the tail was overwritten.
    assert t.rows()[tail - 2] == "line 58"
    assert t.rows()[0] == f"line {60 - tail:02d}"


def test_shrink_on_short_transcript_keeps_output_adjacent(term):
    """A transcript that never filled the screen shifts up with the shrink."""
    t = term(40)
    t.start()
    for i in range(25):
        t.transcript(f"line {i:02d}")

    t.resize(24)
    t.transcript("after resize")

    assert t.row_of("after resize") == t.row_of("line 24") + 1


@pytest.mark.parametrize("new_rows", [37, 39])
def test_small_shrink_leaves_no_ghost_band_in_transcript(term, new_rows):
    """The band slid up with the content; its stale copy must be erased
    rather than scrolled into the transcript."""
    t = term(40)
    t.start()
    for i in range(60):
        t.transcript(f"line {i:02d}")

    t.resize(new_rows)
    for i in range(10):
        t.transcript(f"more {i}")

    rows = t.rows()
    assert sum(IDENTITY in row for row in rows) == 1
    assert sum(row == "Idle" for row in rows) == 1
    assert IDENTITY in rows[-2]
    assert rows[-1] == "Idle"
    assert t.row_of("more 0") == t.row_of("line 59") + 1


def test_grow_keeps_output_adjacent_without_band_sized_gap(term):
    """Growing used to resume output at the old bottom row, leaving the
    erased old band as a blank gap in the transcript."""
    t = term(24)
    t.start()
    for i in range(10):
        t.transcript(f"line {i:02d}")

    t.resize(40)
    t.transcript("after resize")

    assert t.row_of("after resize") == t.row_of("line 09") + 1
    rows = t.rows()
    assert sum(IDENTITY in row for row in rows) == 1
    assert IDENTITY in rows[-2]


def _assert_contiguous(t, prefix, first, last):
    """Lines ``first..last`` sit on consecutive rows, none lost or doubled."""
    start = t.row_of(f"{prefix} {first:02d}")
    for offset, i in enumerate(range(first, last + 1)):
        assert t.rows()[start - 1 + offset] == f"{prefix} {i:02d}", t.rows()


def test_grow_that_pulls_scrollback_down_keeps_transcript(term):
    """Ghostty (herdr) and alacritty pull scrollback into the new rows,
    shifting the transcript AND the band down; the old band row numbers
    then hold transcript lines that must not be erased."""
    t = term(24, pull_on_grow=True)
    t.start()
    for i in range(60):
        t.transcript(f"line {i:02d}")

    t.resize(40)
    t.transcript("after resize")

    tail = t.row_of("line 59")
    assert t.row_of("after resize") == tail + 1
    _assert_contiguous(t, "line", 60 - (tail - 1) + 1, 59)
    rows = t.rows()
    assert sum(IDENTITY in row for row in rows) == 1
    assert IDENTITY in rows[-2]
    assert rows[-1] == "Idle"


@pytest.mark.parametrize("pull_on_grow", [False, True])
def test_shrink_then_grow_round_trip_keeps_transcript_contiguous(term, pull_on_grow):
    t = term(40, pull_on_grow)
    t.start()
    for i in range(45):
        t.transcript(f"line {i:02d}")
    t.resize(20)
    t.transcript("small")
    t.resize(40)
    t.transcript("big")

    small = t.row_of("small")
    assert t.rows()[small - 2] == "line 44"
    assert t.row_of("big") == small + 1
    assert sum(IDENTITY in row for row in t.rows()) == 1
