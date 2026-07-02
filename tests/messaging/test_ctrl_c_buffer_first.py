"""Buffer-first Ctrl+C (Claude Code / Gemini CLI convention).

Mid-run: composing input absorbs the first Ctrl+C (clear + dim hint);
only an empty prompt cancels the agent. Gated ONLY on the SIGINT path.
"""

import inspect
import io

import pytest

import code_puppy.messaging.run_ui as run_ui_mod
from code_puppy.agents._run_signals import sigint_should_cancel
from code_puppy.messaging import bottom_bar as bottom_bar_mod
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
    def __init__(self):
        self.active = False
        self.cancelled = 0

    def start(self):
        self.active = True

    def cancel(self):
        self.active = False
        self.cancelled += 1

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


def make_editor():
    return RunningLineEditor(
        prompt_prefix="> ",
        bar=FakeBar(),
        history=FakeHistory(),
        reverse_search=FakeRSearch(),
    )


class TTY(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def persistent_ui(monkeypatch):
    """Persistent UI on a fake TTY; yields (editor, tty)."""
    monkeypatch.setattr(run_ui_mod, "_spawn_persistent_listener", lambda: None)
    bottom_bar_mod.reset_bottom_bar()
    tty = TTY()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=tty, get_size=lambda: (80, 24)
    )
    assert run_ui_mod.start_persistent_ui() is True
    editor = run_ui_mod.get_run_editor()
    yield editor, tty
    run_ui_mod.stop_persistent_ui()
    bottom_bar_mod.reset_bottom_bar()


# =========================================================================
# Editor.is_composing
# =========================================================================


def test_is_composing_empty_false():
    assert make_editor().is_composing() is False


def test_is_composing_with_text():
    editor = make_editor()
    editor.feed("x")
    assert editor.is_composing() is True


def test_is_composing_multiline_buffer_counts():
    editor = make_editor()
    for ch in "\x1bm":  # multiline on
        editor.feed(ch)
    editor.feed("a")
    editor.feed("\r")  # newline in multiline mode
    assert "\n" in editor.buffer
    assert editor.is_composing() is True


def test_is_composing_reverse_search_counts_even_empty():
    editor = make_editor()
    editor.feed("\x12")  # Ctrl+R, no query typed
    assert editor.buffer == ""
    assert editor.is_composing() is True


# =========================================================================
# absorb_ctrl_c_if_composing / sigint_should_cancel
# =========================================================================


def test_midrun_text_absorbs_clears_and_hints(persistent_ui):
    editor, tty = persistent_ui
    for ch in "half-typed steer":
        editor.feed(ch)
    tty.truncate(0)
    tty.seek(0)
    assert sigint_should_cancel() is False  # press absorbed, NO cancel
    assert editor.buffer == ""
    out = tty.getvalue()
    assert "input cleared" in out and "ctrl+c again" in out
    assert "\x1b[2minput cleared" in out  # hint rides the dim status row


def test_second_press_on_now_empty_buffer_cancels(persistent_ui):
    editor, _tty = persistent_ui
    for ch in "text":
        editor.feed(ch)
    assert sigint_should_cancel() is False  # first press: absorbed
    assert sigint_should_cancel() is True  # second press: cancel fires


def test_empty_buffer_cancels_immediately(persistent_ui):
    _editor, _tty = persistent_ui
    assert sigint_should_cancel() is True


def test_reverse_search_absorbs_and_cancels_search_only(persistent_ui):
    editor, _tty = persistent_ui
    editor.feed("\x12")  # Ctrl+R
    assert editor._rsearch.active is True
    assert sigint_should_cancel() is False  # absorbed: search cancel wins
    assert editor._rsearch.active is False
    assert sigint_should_cancel() is True  # nothing composing now


def test_no_editor_means_cancel_proceeds():
    # Classic mode / embeds: no persistent editor -> gate is transparent.
    assert run_ui_mod.get_run_editor() is None
    assert sigint_should_cancel() is True


def test_gate_fails_open(monkeypatch):
    monkeypatch.setattr(
        run_ui_mod,
        "absorb_ctrl_c_if_composing",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert sigint_should_cancel() is True  # cancellation never breaks


# =========================================================================
# Idle path unchanged
# =========================================================================


def test_idle_clear_buffer_still_works(persistent_ui):
    editor, _tty = persistent_ui
    for ch in "idle text":
        editor.feed(ch)
    run_ui_mod.clear_idle_buffer()
    assert editor.buffer == ""


def test_idle_empty_buffer_noop(persistent_ui):
    editor, _tty = persistent_ui
    run_ui_mod.clear_idle_buffer()  # must not raise / change anything
    assert editor.buffer == ""


# =========================================================================
# What must NOT be gated (source-level contracts)
# =========================================================================


def test_hotkey_cancel_path_is_unconditional():
    """A remapped cancel hotkey (ctrl+k/ctrl+q) never routes through the
    buffer-first gate — only Ctrl+C/SIGINT does."""
    from code_puppy.agents import _key_listeners

    src = inspect.getsource(_key_listeners)
    assert "absorb_ctrl_c" not in src
    assert "sigint_should_cancel" not in src


def test_shell_tool_sigint_handler_untouched():
    """The shell SIGINT handler interrupts the TOOL — never gated."""
    from code_puppy.tools import command_runner

    src = inspect.getsource(command_runner._shell_sigint_handler)
    assert "absorb_ctrl_c" not in src
    assert "sigint_should_cancel" not in src


def test_runtime_gates_only_the_sigint_cancel_decision():
    from code_puppy.agents import _runtime

    src = inspect.getsource(_runtime)
    # The gate sits in keyboard_interrupt_handler (SIGINT), and the
    # graceful (non-ctrl+c-cancel) handler doesn't cancel at all.
    handler_src = src.split("def keyboard_interrupt_handler", 1)[1].split("def ", 1)[0]
    assert "sigint_should_cancel" in handler_src
