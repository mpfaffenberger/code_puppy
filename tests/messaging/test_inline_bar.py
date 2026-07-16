"""JediTerm-safe inline prompt surface tests."""

import io

from code_puppy.messaging import bottom_bar as bottom_bar_mod
from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.inline_bar import InlineBottomBar


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def test_jediterm_selects_inline_surface(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert isinstance(bottom_bar_mod.get_bottom_bar(), InlineBottomBar)
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_android_studio_bundle_needs_no_special_case(monkeypatch):
    """Android Studio is covered by its shared JediTerm emulator marker."""
    monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
    monkeypatch.setenv("__CFBundleIdentifier", "com.google.android.studio")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert isinstance(bottom_bar_mod.get_bottom_bar(), InlineBottomBar)
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_non_jediterm_keeps_scroll_region_surface(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "iTerm2")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    bottom_bar_mod.reset_bottom_bar()
    try:
        bar = bottom_bar_mod.get_bottom_bar()
        assert type(bar) is BottomBar
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_prompt_mode_override_wins(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
    monkeypatch.setenv("CODE_PUPPY_PROMPT_MODE", "pinned")
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert type(bottom_bar_mod.get_bottom_bar()) is BottomBar
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_inline_surface_never_emits_scroll_margins():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))

    bar.start()
    bar.set_prompt_text("> ", "hello", 5)
    bar.set_status("working")
    with bar.output_transaction():
        tty.write("agent output\n")
    bar.stop()

    output = tty.getvalue()
    assert "\x1b[1;" not in output
    assert "\x1b[r" not in output
    assert "agent output\n" in output
    assert "hello" in output
    assert "working" in output


def test_output_transaction_erases_then_redraws_prompt():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    with bar.output_transaction():
        tty.write("new output\n")

    output = tty.getvalue()
    assert output.index("\x1b[2K") < output.index("new output")
    assert output.rindex("draft") > output.index("new output")
