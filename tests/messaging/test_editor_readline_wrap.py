"""Phase B follow-up: readline keys, soft wrap, Alt/Option word jumps."""

import io

import pytest

from code_puppy.messaging.bar_rendering import count_prompt_rows, render_prompt_block
from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.line_editor import RunningLineEditor


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakeBar:
    def set_prompt_text(self, *a):
        pass


class FakeHistory:
    def __init__(self):
        self.ups = 0

    def up(self, _t):
        self.ups += 1
        return None

    def down(self, _t):
        return None

    def reset(self):
        pass

    def record_submit(self, _t):
        pass


class FakeRSearch:
    active = False

    def cancel(self):
        pass


@pytest.fixture
def editor():
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def feed_all(editor, text):
    for ch in text:
        editor.feed(ch)


# =========================================================================
# 1) Readline keys
# =========================================================================


def test_ctrl_a_moves_to_line_start(editor):
    feed_all(editor, "hello world")
    editor.feed("\x01")
    assert editor.cursor == 0


def test_ctrl_e_moves_to_line_end(editor):
    feed_all(editor, "hello")
    editor.feed("\x01")
    editor.feed("\x05")
    assert editor.cursor == 5


def test_ctrl_a_e_use_current_logical_line_in_multiline(editor):
    feed_all(editor, "\x1bm")  # multiline on
    feed_all(editor, "first line")
    editor.feed("\r")
    feed_all(editor, "second")
    # Cursor on line 2; Ctrl+A goes to ITS start, not buffer start.
    editor.feed("\x01")
    assert editor.cursor == len("first line") + 1
    editor.feed("\x05")
    assert editor.cursor == len("first line\nsecond")


def test_ctrl_k_kills_to_line_end(editor):
    feed_all(editor, "keep-this-gone")
    for _ in range(5):
        editor.feed("\x1b[D")  # Left x5
    editor.feed("\x0b")  # Ctrl+K
    assert editor.buffer == "keep-this"


def test_ctrl_k_only_kills_current_logical_line(editor):
    feed_all(editor, "\x1bm")
    feed_all(editor, "one")
    editor.feed("\r")
    feed_all(editor, "two")
    editor.feed("\x01")  # start of line 2
    editor.feed("\x0b")  # kill line 2's text only
    assert editor.buffer == "one\n"


def test_ctrl_w_deletes_word_backwards(editor):
    feed_all(editor, "delete this word")
    editor.feed("\x17")  # Ctrl+W
    assert editor.buffer == "delete this "
    editor.feed("\x17")
    assert editor.buffer == "delete "


def test_ctrl_w_at_start_is_noop(editor):
    editor.feed("\x17")
    assert editor.buffer == ""


# =========================================================================
# 3) Alt/Option word jumps (all encodings)
# =========================================================================


@pytest.mark.parametrize("seq", ["\x1b[1;5D", "\x1b[1;3D", "\x1b[1;9D"])
def test_word_left_variants(editor, seq):
    feed_all(editor, "two words")
    feed_all(editor, seq)
    assert editor.cursor == 4  # start of "words"


@pytest.mark.parametrize("seq", ["\x1b[1;5C", "\x1b[1;3C", "\x1b[1;9C"])
def test_word_right_variants(editor, seq):
    feed_all(editor, "two words")
    editor.feed("\x01")  # home
    feed_all(editor, seq)
    assert editor.cursor == 3  # end of "two"


def test_meta_b_and_f_via_esc_pending(editor):
    feed_all(editor, "alpha beta")
    feed_all(editor, "\x1bb")  # ESC b = Meta-b -> word left
    assert editor.cursor == 6
    feed_all(editor, "\x1bb")
    assert editor.cursor == 0
    feed_all(editor, "\x1bf")  # ESC f = Meta-f -> word right
    assert editor.cursor == 5


def test_meta_b_after_esc_timeout_is_bare_esc_plus_b(editor):
    """ESC then 'b' AFTER the disambiguation window: NOT a word jump —
    the bare ESC resolves, then 'b' is a plain printable insert."""
    fake_now = [100.0]
    editor._now = lambda: fake_now[0]
    feed_all(editor, "text")
    editor.feed("\x1b")
    fake_now[0] += 1.0  # window long expired
    editor.feed("b")
    assert editor.buffer == "textb"
    assert editor.cursor == 5


def test_alt_backspace_deletes_word(editor):
    feed_all(editor, "remove word")
    feed_all(editor, "\x1b\x7f")  # Alt+Backspace
    assert editor.buffer == "remove "


def test_alt_up_behaves_like_plain_up(editor):
    feed_all(editor, "\x1b[1;3A")  # Alt+Up -> history path
    assert editor._history.ups == 1


# =========================================================================
# 2) Soft wrap
# =========================================================================


def test_count_prompt_rows_wraps_by_cells():
    assert count_prompt_rows("> ", "a" * 100, 100, 80) == 2
    assert count_prompt_rows("> ", "a" * 10, 10, 80) == 1
    # Wide glyphs: 60 CJK chars = 120 cells + 2 prefix -> 2 rows.
    assert count_prompt_rows("> ", "\u6c49" * 60, 60, 80) == 2


def test_render_prompt_block_wraps_and_marks_cursor():
    rows, cursor_row = render_prompt_block("> ", "a" * 100, 100, 80, 5)
    assert len(rows) == 2
    assert cursor_row == 1
    assert rows[0].startswith("> a")
    assert "\x1b[7m \x1b[27m" in rows[1]  # cursor cell after the tail


def test_render_prompt_block_wide_glyphs_never_split():
    from rich.cells import cell_len

    rows, _ = render_prompt_block("", "\u6c49" * 50, 50, 79, 5)  # odd width
    plain = [r.replace("\x1b[7m", "").replace("\x1b[27m", "") for r in rows]
    assert all(cell_len(r) <= 79 for r in plain)


def test_cursor_at_exact_row_boundary_wraps_to_next_row():
    # 78 chars + "> " prefix exactly fills an 80-col row; the cursor cell
    # must wrap onto a fresh (empty) second row.
    rows, cursor_row = render_prompt_block("> ", "a" * 78, 78, 80, 5)
    assert len(rows) == 2
    assert cursor_row == 1
    assert rows[1] == "\x1b[7m \x1b[27m"


def test_viewport_scrolls_beyond_cap_keeping_cursor_visible():
    rows, cursor_row = render_prompt_block("> ", "a" * 700, 700, 80, 5)
    assert len(rows) == 5  # capped
    assert cursor_row == 4  # cursor on the last visible row


def test_bar_grows_for_wrapped_input_and_shrinks_back():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    tty.truncate(0)
    tty.seek(0)
    bar.set_prompt_text("> ", "x" * 150, 150)  # 2 visual rows
    assert "\x1b[1;21r" in tty.getvalue()  # reserved 3 -> region 1..21
    tty.truncate(0)
    tty.seek(0)
    bar.set_prompt_text("> ", "short", 5)
    assert "\x1b[1;22r" in tty.getvalue()  # back to 2 reserved rows
    bar.stop()


def test_popup_sits_below_grown_prompt_block():
    """Popup opens UNDER the prompt; the (grown) prompt slides up."""
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "y" * 150, 150)  # 2 prompt rows
    tty.truncate(0)
    tty.seek(0)
    bar.set_popup_lines(["/candidate"], selected=0)
    out = tty.getvalue()
    # Popup at 24 (bottom -- status hidden), prompt 22-23, margin 21.
    assert "\x1b[24;1H\x1b[2K" in out
    assert "/candidate" in out
    assert "\x1b[22;1H\x1b[2K> y" in out  # prompt slid up above the popup
    bar.stop()


def test_history_recall_of_long_entry_grows_viewport():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()

    class LongHistory(FakeHistory):
        def up(self, _t):
            return "z" * 200

    editor = RunningLineEditor(
        prompt_prefix="> ",
        bar=bar,
        history=LongHistory(),
        reverse_search=FakeRSearch(),
    )
    tty.truncate(0)
    tty.seek(0)
    editor.feed("\x1b[A")  # recall the long entry
    out = tty.getvalue()
    assert "\x1b[1;20r" in out  # 3 wrapped rows -> reserved 4
    bar.stop()
