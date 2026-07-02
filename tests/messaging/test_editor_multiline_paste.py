"""Phase B features 3+4: multiline mode + bracketed paste."""

import io

import pytest

from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.editor_paste import PasteBuffer, classify_paste
from code_puppy.messaging.line_editor import RunningLineEditor


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakeBar:
    def __init__(self):
        self.paints = []

    def set_prompt_text(self, prefix, buffer, cursor, prefix_sgrs=None):
        self.paints.append((prefix, buffer, cursor))


class FakeHistory:
    def up(self, _t):
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


class FakeController:
    def __init__(self):
        self.steers = []

    def request_steer(self, text, mode="now"):
        self.steers.append((text, mode))


@pytest.fixture
def bar():
    return FakeBar()


@pytest.fixture
def controller():
    return FakeController()


@pytest.fixture
def editor(bar, controller):
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=bar,
        pause_controller=controller,
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def feed_all(editor, text):
    for ch in text:
        editor.feed(ch)


# =========================================================================
# Multiline mode
# =========================================================================


def test_f2_ss3_toggles_multiline(editor):
    assert editor.multiline is False
    feed_all(editor, "\x1bOQ")  # F2 (SS3)
    assert editor.multiline is True
    feed_all(editor, "\x1bOQ")
    assert editor.multiline is False


def test_f2_csi_variant_toggles_multiline(editor):
    feed_all(editor, "\x1b[12~")  # F2 (CSI)
    assert editor.multiline is True


def test_alt_m_toggles_multiline(editor):
    feed_all(editor, "\x1bm")  # Alt+M
    assert editor.multiline is True


def test_multiline_indicator_in_prompt_prefix(editor, bar):
    feed_all(editor, "\x1bm")
    assert bar.paints[-1][0] == "> [multiline] "


def test_multiline_enter_inserts_newline(editor, controller):
    feed_all(editor, "\x1bm")  # multiline on
    feed_all(editor, "line one")
    editor.feed("\r")  # Enter = newline in multiline mode
    feed_all(editor, "line two")
    assert editor.buffer == "line one\nline two"
    assert controller.steers == []


def test_multiline_alt_enter_submits(editor, controller):
    feed_all(editor, "\x1bm")
    feed_all(editor, "a")
    editor.feed("\r")
    feed_all(editor, "b")
    editor.feed("\x1b")
    editor.feed("\r")  # Alt+Enter submits (queue semantics, as single-line)
    assert controller.steers == [("a\nb", "queue")]
    assert editor.buffer == ""


def test_ctrl_j_always_inserts_newline(editor, controller):
    feed_all(editor, "x")
    editor.feed("\n")  # Ctrl+J, multiline OFF
    feed_all(editor, "y")
    assert editor.buffer == "x\ny"
    assert controller.steers == []


def test_up_down_move_between_lines_in_multiline(editor):
    feed_all(editor, "\x1bm")
    feed_all(editor, "abc")
    editor.feed("\r")
    feed_all(editor, "de")
    assert editor.cursor == 6  # end of "abc\nde"
    feed_all(editor, "\x1b[A")  # Up: to line 1, same column (2)
    assert editor.cursor == 2
    feed_all(editor, "\x1b[B")  # Down: back to line 2
    assert editor.cursor == 6


def test_up_on_first_line_goes_to_history(editor):
    class OneShotHistory(FakeHistory):
        def up(self, _t):
            return "from history"

    editor._history = OneShotHistory()
    feed_all(editor, "\x1bm")
    feed_all(editor, "abc")
    editor.feed("\x1b[A")  # first line -> history, not line-move
    assert editor.buffer == "from history"


# =========================================================================
# Prompt viewport growth (bar-level)
# =========================================================================


def test_prompt_viewport_grows_and_shrinks():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    tty.truncate(0)
    tty.seek(0)
    buffer = "one\ntwo\nthree"
    bar.set_prompt_text("> ", buffer, len(buffer))  # cursor at end
    out = tty.getvalue()
    # 3 prompt rows: reserved = margin+3 (status hidden) -> region 1..20.
    assert "\x1b[1;20r" in out
    assert "> one" in out and "two" in out and "three" in out
    tty.truncate(0)
    tty.seek(0)
    bar.set_prompt_text("> ", "flat", 4)
    assert "\x1b[1;22r" in tty.getvalue()  # back to a single prompt row
    bar.stop()


def test_prompt_viewport_caps_at_five_rows_with_cursor_visible():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    tty.truncate(0)
    tty.seek(0)
    buffer = "\n".join(f"line{i}" for i in range(8))
    bar.set_prompt_text("> ", buffer, len(buffer))  # cursor on line7
    out = tty.getvalue()
    assert "\x1b[1;18r" in out  # 5 prompt rows: reserved 6 -> region 1..18
    assert "line7" in out  # cursor line visible
    assert "line0" not in out  # scrolled out of the viewport
    bar.stop()


# =========================================================================
# Bracketed paste
# =========================================================================


def test_paste_buffer_assembles_split_chunks():
    pb = PasteBuffer()
    pb.start()
    result = None
    for ch in "hello world\x1b[201~":
        out = pb.feed(ch)
        if out is not None:
            result = out
    assert result == "hello world"
    assert pb.active is False


def test_editor_paste_inserts_atomically(editor):
    feed_all(editor, "\x1b[200~")  # opener (via CSI classification)
    for ch in "pasted /text @with triggers\x1b[201~":
        editor.feed(ch)
    assert editor.buffer == "pasted /text @with triggers"


def test_editor_paste_normalizes_crlf(editor):
    feed_all(editor, "\x1b[200~")
    for ch in "a\r\nb\rc\x1b[201~":
        editor.feed(ch)
    assert editor.buffer == "a\nb\nc"  # inner newlines preserved


def test_paste_split_across_feeds(editor):
    feed_all(editor, "\x1b[200~")
    for chunk in ("first ", "second", "\x1b[20", "1~"):
        editor.feed(chunk)
    assert editor.buffer == "first second"


def test_classify_paste_empty_checks_clipboard_image(monkeypatch):
    # Patch the sys.modules object directly (pollution-proof: string
    # targets resolve via package-attr traversal, which stale re-import
    # tests elsewhere can leave pointing at a different module object).
    import importlib

    clip_mod = importlib.import_module("code_puppy.command_line.clipboard")
    monkeypatch.setattr(clip_mod, "has_image_in_clipboard", lambda: True)
    monkeypatch.setattr(
        clip_mod, "capture_clipboard_image_to_pending", lambda: "[clipboard image 1]"
    )
    kind, text = classify_paste("")
    assert kind == "image"
    assert text == "[clipboard image 1] "


def test_classify_paste_text_wins_over_image(monkeypatch):
    import importlib

    clip_mod = importlib.import_module("code_puppy.command_line.clipboard")
    monkeypatch.setattr(clip_mod, "has_image_in_clipboard", lambda: True)
    kind, text = classify_paste("real text")
    assert kind == "text"
    assert text == "real text"


# =========================================================================
# ESC[?2004h lifecycle (bar)
# =========================================================================


def test_bar_arms_bracketed_paste_on_start_and_disarms_on_stop():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    assert "\x1b[?2004h" in tty.getvalue()
    tty.truncate(0)
    tty.seek(0)
    bar.stop()
    assert "\x1b[?2004l" in tty.getvalue()


def test_bar_disarms_paste_during_suspend():
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    tty.truncate(0)
    tty.seek(0)
    with bar.suspended():
        assert "\x1b[?2004l" in tty.getvalue()
        tty.truncate(0)
        tty.seek(0)
    assert "\x1b[?2004h" in tty.getvalue()  # re-armed on resume
    bar.stop()
