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


def test_overlong_rows_are_cell_clipped_below_terminal_width():
    """No painted row may reach the terminal width: JediTerm wraps at the
    margin even with DECAWM off (double-width emoji especially), which
    desyncs the cursor-up bookkeeping and strands stale copies -- the
    spinner-spam bug."""
    from rich.cells import cell_len

    cols = 40
    bar = InlineBottomBar(stream=FakeTTY(), get_size=lambda: (cols, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.set_status_prefix("\U0001f436  ")  # double-width puppy spinner frame
    bar.set_status("tokens 123,456/200,000 " * 5)  # way past 40 cells
    bar.set_status_suffix(" | queued: 3")
    bar.set_panel_lines(["sub-agent panel line " * 5])

    for line in bar._inline_lines():
        assert cell_len(line) < cols


def test_inline_surface_retains_every_panel_row():
    bar = InlineBottomBar(stream=FakeTTY(), get_size=lambda: (80, 24))
    lines = [f"agent-{index}" for index in range(6)]

    bar.start()
    bar.set_panel_lines(lines)

    assert bar.get_panel_lines() == lines
    assert bar._inline_lines()[:6] == lines


def test_inline_panel_clamps_to_viewport_with_overflow():
    """On a short viewport the panel can't render one row per agent -- the
    block would exceed terminal height and desync the cursor-up repaint
    count. It clamps to what fits and collapses the rest into '+N more',
    keeping the raw panel state intact."""
    bar = InlineBottomBar(stream=FakeTTY(), get_size=lambda: (80, 8))
    lines = [f"agent-{index}" for index in range(10)]

    bar.start()
    bar.set_panel_lines(lines)
    rendered = bar._inline_lines()

    # The whole block never exceeds the viewport height.
    assert len(rendered) <= 8
    # The clamped overflow is summarized rather than dropped silently.
    assert any("more" in row for row in rendered)
    # Raw panel state still holds every tracked agent (clamp is render-only).
    assert bar.get_panel_lines() == lines


def test_spinner_tick_repaints_in_place_without_growing_block():
    """A status-prefix tick (the 5fps puppy) must erase and repaint the
    same number of rows -- never leaving extra lines behind."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "steer me", 8)
    bar.set_status("ctx 12k/200k")
    rows_before = bar._displayed_rows

    tty.seek(0)
    tty.truncate(0)
    for frame in ("\U0001f436   ", " \U0001f436  ", "  \U0001f436 "):
        bar.set_status_prefix(frame)

    assert bar._displayed_rows == rows_before
    output = tty.getvalue()
    # Each of the 3 ticks repaints the same block: exactly rows-1
    # newlines per repaint, and never a lone "\n" that would scroll
    # rows into scrollback.
    assert output.count("\r\n") == 3 * (rows_before - 1)
    assert output.count("\n") == output.count("\r\n")


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
