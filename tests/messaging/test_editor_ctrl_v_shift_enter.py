"""Ctrl+V smart paste + Shift/Ctrl+Enter newline (owner follow-up)."""

import asyncio
import importlib
import io
import threading
import time

import pytest

from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.editor_paste import read_clipboard_smart
from code_puppy.messaging.line_editor import RunningLineEditor


class FakeBar:
    def set_prompt_text(self, *a):
        pass


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


@pytest.fixture
def editor():
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


def clip_mod():
    return importlib.import_module("code_puppy.command_line.clipboard")


# =========================================================================
# read_clipboard_smart classification
# =========================================================================


def test_read_clipboard_smart_image(monkeypatch):
    monkeypatch.setattr(
        clip_mod(), "capture_clipboard_image_to_pending", lambda: "[clipboard image 1]"
    )
    kind, text = read_clipboard_smart()
    assert kind == "image"
    assert text == "[clipboard image 1] "


def test_read_clipboard_smart_text(monkeypatch):
    monkeypatch.setattr(clip_mod(), "capture_clipboard_image_to_pending", lambda: None)
    monkeypatch.setattr(
        "code_puppy.messaging.editor_paste._read_clipboard_text",
        lambda: "line1\r\nline2\n",
    )
    kind, text = read_clipboard_smart()
    assert kind == "text"
    assert text == "line1\nline2"  # CRLF-normalized, trailing \n stripped


def test_read_clipboard_smart_empty(monkeypatch):
    monkeypatch.setattr(clip_mod(), "capture_clipboard_image_to_pending", lambda: None)
    monkeypatch.setattr(
        "code_puppy.messaging.editor_paste._read_clipboard_text", lambda: None
    )
    assert read_clipboard_smart() == ("none", "")


def test_read_clipboard_smart_image_check_failure_falls_to_text(monkeypatch):
    def boom():
        raise RuntimeError("no clipboard")

    monkeypatch.setattr(clip_mod(), "capture_clipboard_image_to_pending", boom)
    monkeypatch.setattr(
        "code_puppy.messaging.editor_paste._read_clipboard_text", lambda: "fallback"
    )
    assert read_clipboard_smart() == ("text", "fallback")


# =========================================================================
# \x16 in the editor
# =========================================================================


def test_ctrl_v_invokes_handler_and_insert_is_programmatic(editor):
    calls = []
    editor.set_clipboard_handler(lambda: calls.append(1))
    editor.feed("\x16")
    assert calls == [1]
    # Async apply path: completion must stay quiet (typed=False).
    notified = []

    class Engine:
        def is_open(self):
            return False

        def on_edit(self, *a):
            notified.append(a)

        def close(self):
            pass

        def set_suppressed(self, *_a):
            pass

    editor.attach_completion(Engine())
    editor.insert_paste_text("/pasted text")
    assert editor.buffer == "/pasted text"
    assert notified == []  # no completion query for programmatic insert


def test_ctrl_v_without_handler_is_noop(editor):
    editor.feed("\x16")
    assert editor.buffer == ""


def test_ctrl_v_insert_at_cursor(editor):
    for ch in "ab":
        editor.feed(ch)
    editor.feed("\x1b[D")  # Left
    editor.insert_paste_text("XY")
    assert editor.buffer == "aXYb"
    assert editor.cursor == 3


def test_ctrl_v_does_not_block_feed_on_slow_clipboard(editor):
    """The handler is fire-and-forget: a slow clipboard read must not
    stall the key-listener thread's feed() call."""
    release = threading.Event()

    def slow_handler():
        # Simulate run_ui's behavior: schedule elsewhere, return at once.
        threading.Thread(
            target=lambda: (release.wait(2), editor.insert_paste_text("late")),
            daemon=True,
        ).start()

    editor.set_clipboard_handler(slow_handler)
    t0 = time.monotonic()
    editor.feed("\x16")
    editor.feed("x")  # typing continues immediately
    assert time.monotonic() - t0 < 0.5
    assert editor.buffer == "x"
    release.set()


def test_run_ui_clipboard_wiring_hops_to_loop(monkeypatch):
    """End-to-end: \\x16 -> handler -> executor read -> insert."""
    from code_puppy.messaging.run_ui_wiring import make_clipboard_handler

    monkeypatch.setattr(
        "code_puppy.messaging.editor_paste.read_clipboard_smart",
        lambda: ("text", "from-clipboard"),
    )
    editor = RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )

    async def scenario():
        loop = asyncio.get_running_loop()
        editor.set_clipboard_handler(make_clipboard_handler(editor, lambda: loop))
        await asyncio.get_running_loop().run_in_executor(
            None, editor.feed, "\x16"
        )  # from "listener thread"
        await asyncio.sleep(0.2)

    asyncio.run(scenario())
    assert editor.buffer == "from-clipboard"


# =========================================================================
# Shift+Enter / Ctrl+Enter -> newline
# =========================================================================


@pytest.mark.parametrize(
    "seq",
    [
        "\x1b[13;2u",  # Shift+Enter, CSI-u
        "\x1b[13;5u",  # Ctrl+Enter, CSI-u
        "\x1b[27;2;13~",  # Shift+Enter, modifyOtherKeys
        "\x1b[27;5;13~",  # Ctrl+Enter, modifyOtherKeys
    ],
)
def test_modified_enter_inserts_newline_byte_split(editor, seq):
    for ch in "ab":
        editor.feed(ch)
    for ch in seq:  # byte-at-a-time, like the real listener
        editor.feed(ch)
    assert editor.buffer == "ab\n"
    assert editor.multiline is False  # works in single-line mode too


def test_modified_enter_never_submits(editor):
    submitted = []
    editor.set_submit_router(lambda t, m: submitted.append((t, m)))
    for ch in "text\x1b[13;2u":
        editor.feed(ch)
    assert submitted == []
    assert editor.buffer == "text\n"


def test_unknown_enter_modifier_swallowed(editor):
    for ch in "ab\x1b[13;3u":  # Alt+Enter via CSI-u: unmapped
        editor.feed(ch)
    assert editor.buffer == "ab"  # swallowed, nothing inserted


# =========================================================================
# modifyOtherKeys lifecycle on the bar
# =========================================================================


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def bar_tty():
    tty = FakeTTY()
    return BottomBar(stream=tty, get_size=lambda: (80, 24)), tty


def drain(tty):
    tty.truncate(0)
    tty.seek(0)


def test_modkeys_on_start_off_stop(bar_tty):
    bar, tty = bar_tty
    bar.start()
    assert "\x1b[>4;1m" in tty.getvalue()
    drain(tty)
    bar.stop()
    assert "\x1b[>4;0m" in tty.getvalue()


def test_modkeys_cycle_through_suspend_resume(bar_tty):
    bar, tty = bar_tty
    bar.start()
    drain(tty)
    with bar.suspended():
        assert "\x1b[>4;0m" in tty.getvalue()
        drain(tty)
    assert "\x1b[>4;1m" in tty.getvalue()  # re-armed on resume
    bar.stop()


def test_modkeys_off_when_dormant_and_on_when_woken():
    """Dormant = terminal too small for the reserved rows: the bar backs
    off completely, including modifyOtherKeys; re-arms when it grows."""
    tty = FakeTTY()
    size = {"rows": 24}
    bar = BottomBar(stream=tty, get_size=lambda: (80, size["rows"]))
    bar.start()
    drain(tty)
    size["rows"] = 2  # too small -> dormant on next geometry check
    bar.set_status("shrink")
    assert "\x1b[>4;0m" in tty.getvalue()
    drain(tty)
    size["rows"] = 24
    bar.set_status("grow")
    assert "\x1b[>4;1m" in tty.getvalue()
    bar.stop()


def test_modkeys_off_on_emergency_restore(bar_tty):
    bar, tty = bar_tty
    bar.start()
    drain(tty)
    bar._emergency_restore()
    assert "\x1b[>4;0m" in tty.getvalue()
