"""Ctrl+L clears the screen: editor wiring + both prompt surfaces.

The raw editor used to swallow ``\\x0c`` as an "unknown control character",
so there was no way to wipe the viewport without restarting. These tests
pin the key wiring, the escape sequence, and (via a VT emulator) what the
user actually sees afterwards.
"""

import io

import pyte
import pytest

from code_puppy.messaging import chords
from code_puppy.messaging import inline_bar as inline_bar_mod
from code_puppy.messaging.bar_rendering import CLEAR_SCREEN
from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.inline_bar import InlineBottomBar
from code_puppy.messaging.line_editor import RunningLineEditor

CTRL_L = "\x0c"
CTRL_X = "\x18"
COLS, ROWS = 60, 24


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakePipe(io.StringIO):
    def isatty(self):
        return False


# =========================================================================
# Editor wiring
# =========================================================================


class RecordingBar:
    def __init__(self, error=None):
        self.clears = 0
        self._error = error

    def set_prompt_text(self, *args):
        pass

    def clear_screen(self):
        self.clears += 1
        if self._error:
            raise self._error


class FakeHistory:
    def up(self, _text):
        return None

    def down(self, _text):
        return None

    def reset(self):
        pass

    def record_submit(self, _text):
        pass


class FakeRSearch:
    def __init__(self):
        self.active = False

    def start(self):
        self.active = True

    def cancel(self):
        self.active = False

    def feed_char(self, ch):
        pass

    def backspace(self):
        pass

    def next_older(self):
        pass

    def current_match(self):
        return None

    def prompt_text(self):
        return "(reverse-i-search)`': "


def make_editor(bar):
    # Frozen clock: the ESC timeout (Alt+M etc.) can never expire mid-test.
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=bar,
        now=lambda: 0.0,
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def feed_all(editor, text):
    for ch in text:
        editor.feed(ch)


def test_ctrl_l_clears_screen_and_keeps_buffer():
    bar = RecordingBar()
    editor = make_editor(bar)
    feed_all(editor, "hello")

    editor.feed(CTRL_L)

    assert bar.clears == 1
    assert editor.buffer == "hello"
    assert editor.cursor == 5


def test_ctrl_l_on_empty_buffer_clears_screen():
    bar = RecordingBar()
    make_editor(bar).feed(CTRL_L)
    assert bar.clears == 1


def test_ctrl_l_works_in_multiline_mode():
    bar = RecordingBar()
    editor = make_editor(bar)
    feed_all(editor, "\x1bm")
    feed_all(editor, "a\rb")

    editor.feed(CTRL_L)

    assert bar.clears == 1
    assert editor.buffer == "a\nb"


def test_ctrl_l_does_not_cancel_reverse_search():
    bar = RecordingBar()
    editor = make_editor(bar)
    editor.feed("\x12")  # Ctrl+R
    assert editor._rsearch.active

    editor.feed(CTRL_L)

    assert bar.clears == 1
    assert editor._rsearch.active


def test_form_feed_inside_bracketed_paste_is_paste_data():
    bar = RecordingBar()
    editor = make_editor(bar)

    feed_all(editor, "\x1b[200~" + "a" + CTRL_L + "b" + "\x1b[201~")

    assert bar.clears == 0
    assert "a" in editor.buffer
    assert "b" in editor.buffer


def test_clear_failure_never_breaks_the_key_path():
    bar = RecordingBar(error=RuntimeError("terminal exploded"))
    editor = make_editor(bar)

    editor.feed(CTRL_L)
    editor.feed("x")

    assert bar.clears == 1
    assert editor.buffer == "x"


@pytest.fixture
def ctrl_l_chord():
    hits = []
    chords.register_chord(CTRL_L, lambda: hits.append(True), "Ctrl+L test")
    yield hits
    chords.unregister_chord(CTRL_L)


def test_bound_ctrl_x_ctrl_l_chord_wins_over_clear(ctrl_l_chord):
    bar = RecordingBar()
    editor = make_editor(bar)

    editor.feed(CTRL_X)
    editor.feed(CTRL_L)

    assert ctrl_l_chord == [True]
    assert bar.clears == 0


def test_unbound_ctrl_x_ctrl_l_disarms_chord_and_clears():
    bar = RecordingBar()
    editor = make_editor(bar)

    editor.feed(CTRL_X)
    editor.feed(CTRL_L)

    assert bar.clears == 1
    assert editor._ctrl_x_pending is False


# =========================================================================
# BottomBar (DECSTBM surface)
# =========================================================================


def test_clear_screen_emits_viewport_clear_without_scrollback_wipe():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (COLS, ROWS))
    bar.start()
    tty.truncate(0)
    tty.seek(0)

    bar.clear_screen()

    out = tty.getvalue()
    assert CLEAR_SCREEN in out
    assert "\x1b[3J" not in out


def test_clear_screen_is_noop_when_inactive():
    tty = FakeTTY()
    BottomBar(stream=tty, get_size=lambda: (COLS, ROWS)).clear_screen()
    assert tty.getvalue() == ""


def test_clear_screen_is_noop_off_tty():
    pipe = FakePipe()
    bar = BottomBar(stream=pipe, get_size=lambda: (COLS, ROWS))
    bar.start()
    bar.clear_screen()
    assert pipe.getvalue() == ""


def test_clear_screen_is_noop_while_suspended():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (COLS, ROWS))
    bar.start()
    with bar.suspended():
        tty.truncate(0)
        tty.seek(0)
        bar.clear_screen()
        assert tty.getvalue() == ""


def test_clear_screen_resets_popup_slack():
    bar = BottomBar(stream=FakeTTY(), get_size=lambda: (COLS, ROWS))
    bar.start()
    bar.set_popup_lines(["/a", "/b"], selected=0)
    bar.set_popup_lines([])
    assert bar._popup_slack > 0

    bar.clear_screen()

    assert bar._popup_slack == 0


class Tap(FakeTTY):
    def __init__(self, feed):
        super().__init__()
        self._feed = feed

    def write(self, s):
        self._feed(s)
        return len(s)


class Term:
    """A bar wired to a pyte virtual terminal."""

    def __init__(self, bar_cls=BottomBar, guard_scroll_fix=False):
        self.screen = pyte.Screen(COLS, ROWS)
        self.stream = pyte.Stream(self.screen)
        self.bar = bar_cls(stream=Tap(self.stream.feed), get_size=lambda: (COLS, ROWS))
        self.bar._guard_scroll_fix = guard_scroll_fix

    def transcript(self, text):
        with self.bar.output_transaction():
            self.stream.feed(text + "\r\n")

    def rows(self):
        return [line.rstrip() for line in self.screen.display]

    def text(self):
        return "\n".join(self.rows())


@pytest.fixture(params=[False, True], ids=["posix-region", "windows-guard"])
def term(request):
    return Term(guard_scroll_fix=request.param)


def test_clear_wipes_transcript_and_keeps_prompt_and_status(term):
    term.bar.start()
    for i in range(5):
        term.transcript(f"clutter {i}")
    term.bar.set_status("ctx 42%")
    term.bar.set_prompt_text("> ", "half typed", 10)
    assert "clutter 0" in term.text()

    term.bar.clear_screen()

    text = term.text()
    assert "clutter" not in text
    assert "half typed" in text
    assert "ctx 42%" in text


def test_output_after_clear_is_not_overwritten_or_lost(term):
    term.bar.start()
    for i in range(30):
        term.transcript(f"old {i}")
    term.bar.set_prompt_text("> ", "draft", 5)

    term.bar.clear_screen()
    term.transcript("fresh line")

    text = term.text()
    assert "fresh line" in text
    assert "draft" in text
    assert "old" not in text


def test_posix_clear_starts_transcript_at_the_top():
    term = Term()
    term.bar.start()
    for i in range(ROWS + 5):
        term.transcript(f"old {i}")

    term.bar.clear_screen()
    term.transcript("first after clear")
    term.transcript("second after clear")

    rows = term.rows()
    assert rows[0] == "first after clear"
    assert rows[1] == "second after clear"


def test_windows_guard_flushes_carry_before_clear_and_resyncs_simulator():
    term = Term(guard_scroll_fix=True)
    writes = []
    real_write = term.bar._write
    term.bar._write = lambda seq: (writes.append(seq), real_write(seq))[1]
    term.bar.start()
    term.bar._carry = "\x1b[38;2;1;2"
    writes.clear()

    term.bar.clear_screen()

    joined = "".join(writes)
    assert joined.index("\x1b[38;2;1;2") < joined.index(CLEAR_SCREEN)
    assert term.bar._carry == ""
    assert term.bar._sim_row == ROWS - term.bar._reserved


def test_windows_guard_keeps_routing_transcript_after_clear():
    term = Term(guard_scroll_fix=True)
    term.bar.start()
    term.bar.set_prompt_text("> ", "draft", 5)
    term.bar.clear_screen()

    for i in range(ROWS + 3):
        term.bar.guarded_write(f"line {i}\r\n", term.bar._stream)

    text = term.text()
    assert f"line {ROWS + 2}" in text
    assert "draft" in text
    assert 1 <= term.bar._sim_row <= ROWS - term.bar._reserved


def test_clear_while_popup_open_repaints_popup_rows(term):
    term.bar.start()
    term.bar.set_prompt_text("> ", "/mo", 3)
    term.bar.set_popup_lines(["/model", "/motd"], selected=0)

    term.bar.clear_screen()

    text = term.text()
    assert "/model" in text
    assert "/motd" in text


def test_clear_on_too_small_terminal_does_not_crash():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (COLS, 2))
    bar.start()

    bar.clear_screen()

    assert CLEAR_SCREEN in tty.getvalue()


def test_repeated_clears_do_not_accumulate_gaps():
    term = Term()
    term.bar.start()
    for n in range(3):
        term.transcript(f"before {n}")
        term.bar.clear_screen()
    term.transcript("after")

    assert term.rows()[0] == "after"


# =========================================================================
# InlineBottomBar (no scroll region)
# =========================================================================


def make_inline():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (COLS, ROWS))
    bar.start()
    return bar, tty


def drain(tty):
    value = tty.getvalue()
    tty.truncate(0)
    tty.seek(0)
    return value


def test_inline_clear_wipes_viewport_and_repaints_cached_prompt():
    bar, tty = make_inline()
    try:
        bar.set_prompt_text("> ", "draft", 5)
        drain(tty)

        bar.clear_screen()

        out = drain(tty)
        assert CLEAR_SCREEN in out
        assert "\x1b[3J" not in out
        assert out.index(CLEAR_SCREEN) < out.index("draft")
        assert bar._displayed_rows >= 1
    finally:
        bar.stop()


def test_inline_clear_resets_partial_line_and_cancels_repaint_timer(monkeypatch):
    monkeypatch.setattr(inline_bar_mod, "_REPAINT_QUIET_S", 60.0)
    bar, tty = make_inline()
    try:
        bar.guarded_write("streaming without newline", tty)
        assert bar._at_line_start is False
        assert bar._repaint_timer is not None

        bar.clear_screen()

        assert bar._at_line_start is True
        assert bar._repaint_timer is None
    finally:
        bar.stop()


def test_inline_writes_after_clear_still_erase_and_repaint():
    bar, tty = make_inline()
    try:
        bar.clear_screen()
        drain(tty)

        bar.guarded_write("hello\n", tty)

        out = drain(tty)
        assert "hello\n" in out
        assert bar._displayed_rows >= 1
    finally:
        bar.stop()


def test_inline_clear_is_noop_when_inactive_or_suspended():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (COLS, ROWS))
    bar.clear_screen()
    assert tty.getvalue() == ""

    bar.start()
    try:
        with bar.suspended():
            drain(tty)
            bar.clear_screen()
            assert tty.getvalue() == ""
    finally:
        bar.stop()
