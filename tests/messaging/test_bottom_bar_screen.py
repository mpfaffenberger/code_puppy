"""End-to-end virtual-screen tests for the bottom bar's cursor contract.

The escape-string tests in ``test_bottom_bar.py`` pin the sequences we
*emit*; these render them through a real VT emulator (pyte) and assert
what a user actually *sees*. They exist because three generations of
"blank gap in the transcript" bugs (pause-flush ordering, popup slack,
cursor parking + blind grow-scrolls) all produced individually-plausible
escape streams that composed into visible whitespace.

The golden invariant: transcript output is ALWAYS adjacent to the
previous transcript line — no matter how short the transcript is, how
many completion popups opened, or how many TUI menus ran in between.
"""

import io

import pyte
import pytest

from code_puppy.messaging.bottom_bar import BottomBar

COLS, ROWS = 60, 24


class VTScreen(pyte.Screen):
    """pyte lacks SU/SD (CSI S / CSI T); emulate via DL/IL at margin top."""

    def scroll_up(self, count=None):
        count = count or 1
        top = self.margins.top if self.margins else 0
        x, y = self.cursor.x, self.cursor.y
        self.cursor.y = top
        self.delete_lines(count)
        self.cursor.x, self.cursor.y = x, y

    def scroll_down(self, count=None):
        count = count or 1
        top = self.margins.top if self.margins else 0
        x, y = self.cursor.x, self.cursor.y
        self.cursor.y = top
        self.insert_lines(count)
        self.cursor.x, self.cursor.y = x, y


class VTStream(pyte.Stream):
    csi = dict(pyte.Stream.csi, S="scroll_up", T="scroll_down")


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


class Term:
    """A BottomBar wired to a virtual terminal, plus a transcript writer."""

    def __init__(self):
        self.screen = VTScreen(COLS, ROWS)
        self.stream = VTStream(self.screen)
        self.bar = BottomBar(
            stream=Tap(self.stream.feed), get_size=lambda: (COLS, ROWS)
        )

    def transcript(self, text):
        """Print one transcript line the way the renderers do: at the
        current cursor, inside an output transaction."""
        with self.bar.output_transaction():
            self.stream.feed(text + "\r\n")

    def rows(self):
        return {i: line.rstrip() for i, line in enumerate(self.screen.display, 1)}

    def row_of(self, text):
        matches = [i for i, t in self.rows().items() if t == text]
        assert len(matches) == 1, f"{text!r} matched rows {matches}: {self.rows()}"
        return matches[0]


@pytest.fixture
def term():
    return Term()


def run_model_picker_flow(term):
    """Type /model with the slash popup open, run a menu, flush output."""
    term.bar.set_prompt_text("> ", "/model", 6)
    term.bar.set_popup_lines(["/model", "/motd", "/mcp", "/m"], selected=0)
    term.bar.set_popup_lines([])  # Enter: popup closes -> slack
    term.bar.set_prompt_text("> ", "", 0)  # submit clears the buffer
    term.transcript("> /model")  # submit echo
    with term.bar.suspended():
        pass  # picker ran in the alt screen; primary untouched
    term.transcript("Model selection cancelled")  # pause-buffer flush


def test_menu_output_adjacent_on_short_transcript(term):
    """Fresh session (screen mostly empty): the post-menu flush must land
    directly under the submit echo — not teleport to the region bottom."""
    term.bar.start()
    term.transcript("Welcome banner line 1")
    term.transcript("Welcome banner line 2")
    run_model_picker_flow(term)

    assert term.row_of("Welcome banner line 1") == 1
    assert term.row_of("Welcome banner line 2") == 2
    echo = term.row_of("> /model")
    assert echo == 3  # popup open/close moved nothing
    assert term.row_of("Model selection cancelled") == echo + 1


def test_menu_output_adjacent_on_full_transcript(term):
    """Scrolled steady state: same invariant once the screen is full."""
    term.bar.start()
    for i in range(ROWS + 5):
        term.transcript(f"line {i}")
    run_model_picker_flow(term)

    echo = term.row_of("> /model")
    assert term.row_of("Model selection cancelled") == echo + 1
    # And the line printed just before the echo is still right above it.
    assert term.row_of(f"line {ROWS + 4}") == echo - 1


def test_popup_open_does_not_scroll_short_transcript(term):
    """Opening the completion popup must not shove a short transcript
    toward the top of the screen — the reserved rows were already blank."""
    term.bar.start()
    term.transcript("only line")
    term.bar.set_prompt_text("> ", "/", 1)
    term.bar.set_popup_lines(["/a", "/b", "/c", "/d", "/e"], selected=0)

    assert term.row_of("only line") == 1
    term.bar.set_popup_lines([])
    assert term.row_of("only line") == 1


def test_repeated_menus_do_not_accumulate_gaps(term):
    """Menu cycles must not leak even a single blank row per run."""
    term.bar.start()
    term.transcript("start")
    for n in range(3):
        term.transcript(f"> /model {n}")
        with term.bar.suspended():
            pass
        term.transcript(f"result {n}")

    rows = term.rows()
    expected = ["start"]
    for n in range(3):
        expected += [f"> /model {n}", f"result {n}"]
    assert [rows[i] for i in range(1, len(expected) + 1)] == expected
