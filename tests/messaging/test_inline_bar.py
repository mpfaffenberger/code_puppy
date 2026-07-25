"""JediTerm-safe inline prompt surface tests."""

import io
import sys

from code_puppy.messaging import bottom_bar as bottom_bar_mod
from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.bar_rendering import (
    CURSOR_HIDE,
    CURSOR_SHOW,
    SYNC_OFF,
    SYNC_ON,
)
from code_puppy.messaging.inline_bar import InlineBottomBar
from code_puppy.messaging.transcript_guard import StreamGuard


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def _pin_config_mode(monkeypatch, mode: str = "auto") -> None:
    """Isolate selection tests from the developer's real puppy.cfg."""
    monkeypatch.setattr(bottom_bar_mod, "_configured_prompt_mode", lambda: mode)


def test_jediterm_selects_inline_surface(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    _pin_config_mode(monkeypatch)
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
    _pin_config_mode(monkeypatch)
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert isinstance(bottom_bar_mod.get_bottom_bar(), InlineBottomBar)
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_non_jediterm_keeps_scroll_region_surface(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "iTerm2")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    _pin_config_mode(monkeypatch)
    bottom_bar_mod.reset_bottom_bar()
    try:
        bar = bottom_bar_mod.get_bottom_bar()
        assert type(bar) is BottomBar
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_prompt_mode_override_wins(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "JetBrains-JediTerm")
    monkeypatch.setenv("CODE_PUPPY_PROMPT_MODE", "pinned")
    _pin_config_mode(monkeypatch)
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert type(bottom_bar_mod.get_bottom_bar()) is BottomBar
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_config_prompt_mode_selects_inline_surface(monkeypatch):
    """`/set prompt_mode inline` flows the prompt with output everywhere."""
    monkeypatch.setenv("TERMINAL_EMULATOR", "iTerm2")
    monkeypatch.delenv("CODE_PUPPY_PROMPT_MODE", raising=False)
    _pin_config_mode(monkeypatch, "inline")
    bottom_bar_mod.reset_bottom_bar()
    try:
        assert isinstance(bottom_bar_mod.get_bottom_bar(), InlineBottomBar)
    finally:
        bottom_bar_mod.reset_bottom_bar()


def test_env_var_beats_config_prompt_mode(monkeypatch):
    monkeypatch.setenv("TERMINAL_EMULATOR", "iTerm2")
    monkeypatch.setenv("CODE_PUPPY_PROMPT_MODE", "pinned")
    _pin_config_mode(monkeypatch, "inline")
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


def test_complete_foreign_line_erases_then_repaints_bar():
    """A newline-complete streaming write can safely repaint immediately,
    keeping the prompt visible without overwriting transcript content."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("reporting for duty!\n")
    with bar._lock:  # determinism: the 0.2s timer must not race the asserts
        bar._cancel_repaint_timer()

    output = tty.getvalue()
    assert output.index("\x1b[2K") < output.index("reporting for duty!")
    assert output.rindex("draft") > output.index("reporting for duty!")
    assert CURSOR_HIDE in output
    assert bar._displayed_rows > 0
    bar.stop()


def test_status_tick_while_hidden_is_cache_only():
    """When width tracking bails (here: a tab poisons it), the bar hides
    mid-line and the 5fps spinner / token-context ticks must not paint
    anything -- the old behavior repainted at the transcript cursor and
    shredded output."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    bar.guarded_write("AGENT RESPONSE\npartial\toutput")
    with bar._lock:  # determinism: the 0.2s timer must not race the asserts
        bar._cancel_repaint_timer()
    tty.seek(0)
    tty.truncate(0)

    bar.set_status("3.6k/1M tokens (0%)")  # mid-stream tick
    bar.set_status_prefix("\U0001f436  ")
    bar.set_panel_lines(["sub-agent working"])

    assert tty.getvalue() == ""  # cache only; nothing hit the terminal

    # Once output quiesces, the timer repaints with the latest cache.
    with bar._lock:
        bar._cancel_repaint_timer()
    bar._last_foreign_write = 0.0
    bar._repaint_after_quiet()
    output = tty.getvalue()
    assert "3.6k/1M tokens (0%)" in output
    assert "draft" in output
    assert bar._displayed_rows > 0
    bar.stop()


def test_quiescent_repaint_commits_partial_line_first():
    """If the last foreign write left the cursor mid-line AND the bar
    hidden (width tracking bailed), the repaint must move below it --
    painting starts with CLEAR_LINE and would otherwise destroy the
    half-written transcript line."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    bar.guarded_write("partial line\twithout newline")
    with bar._lock:  # determinism: the 0.2s timer must not race the asserts
        bar._cancel_repaint_timer()
    tty.seek(0)
    tty.truncate(0)

    bar._last_foreign_write = 0.0
    bar._repaint_after_quiet()

    output = tty.getvalue()
    # Committed below the partial line (ignoring the DEC 2026 bracket).
    assert output.replace(SYNC_ON, "", 1).startswith("\r\n")
    assert "draft" in output
    bar.stop()


def test_suspended_surface_shows_then_rehides_hardware_cursor():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    tty.seek(0)
    tty.truncate(0)

    with bar.suspended():
        assert CURSOR_SHOW in tty.getvalue()
    assert tty.getvalue().rindex(CURSOR_HIDE) > tty.getvalue().index(CURSOR_SHOW)
    bar.stop()


def test_streaming_write_is_one_synchronized_frame():
    """The erase→text→repaint cycle of a streamed line must sit inside
    one DEC 2026 bracket so the terminal never renders the bar-missing
    intermediate state -- the flicker bug."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("one full line\n")
    with bar._lock:
        bar._cancel_repaint_timer()

    output = tty.getvalue()
    assert output.count(SYNC_ON) == 1
    assert output.count(SYNC_OFF) == 1
    # Bracket encloses the whole cycle: erase, text, and repaint.
    assert output.index(SYNC_ON) < output.index("\x1b[2K")
    assert output.rindex("draft") < output.rindex(SYNC_OFF)
    assert bar._sync_depth == 0
    bar.stop()


def test_spinner_tick_is_one_synchronized_frame():
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.set_status("ctx 12k/200k")
    tty.seek(0)
    tty.truncate(0)

    bar.set_status_prefix("\U0001f436  ")  # one tick

    output = tty.getvalue()
    assert output.count(SYNC_ON) == 1
    assert output.count(SYNC_OFF) == 1
    assert output.index(SYNC_ON) < output.rindex(SYNC_OFF)
    assert bar._sync_depth == 0
    bar.stop()


def test_output_transaction_brackets_erase_and_repaint():
    """Nested guarded writes inside a transaction must not close the
    outer bracket early (refcounted BSU/ESU)."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    with bar.output_transaction():
        bar.guarded_write("nested stream write\n")

    output = tty.getvalue()
    assert output.count(SYNC_ON) == 1  # outermost bracket only
    assert output.count(SYNC_OFF) == 1
    assert output.rindex("draft") < output.rindex(SYNC_OFF)
    assert bar._sync_depth == 0
    bar.stop()


def test_midline_stream_keeps_prompt_visible():
    """THE streaming fix: a clean mid-line chunk repaints the bar below
    the partial line and hops the cursor back -- the prompt no longer
    vanishes while a paragraph streams."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("streaming tokens")

    output = tty.getvalue()
    assert bar._displayed_rows > 0  # visible!
    assert bar._bar_below_partial is True
    # Hop-back: up one row, CR, right by the partial line's cell width.
    assert "\x1b[1A\r" in output
    assert f"\x1b[{len('streaming tokens')}C" in output
    # The bar painted AFTER the chunk text (below it).
    assert output.rindex("draft") > output.index("streaming tokens")
    bar.stop()


def test_midline_extension_streams_text_only():
    """THE anti-flicker fast path: once the bar sits below the partial
    line, a same-row chunk passes straight through -- zero escapes,
    zero bar repaints, nothing to flicker."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    bar.guarded_write("first chunk")
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write(", second chunk")

    assert tty.getvalue() == ", second chunk"  # bytes in, bytes out
    assert bar._bar_below_partial is True  # bar untouched, still below
    assert bar._displayed_rows > 0
    assert bar._partial.text == "first chunk, second chunk"
    bar.stop()


def test_midline_extension_that_wraps_moves_the_bar():
    """A chunk that crosses the row boundary can't extend in place: the
    bar erases (DECSC/DECRC hop), the text wraps, and the bar repaints
    below the new row with the correct hop column."""
    cols = 20
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (cols, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.guarded_write("x" * 10)  # bar painted below, col 10
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("y" * 15)  # 25 cells total -> wraps to row 2, col 5

    output = tty.getvalue()
    assert "\x1b7" in output  # DECSC before hopping down to erase
    assert "\x1b8" in output  # DECRC back into the partial line
    assert output.index("\x1b8") < output.index("y" * 15)
    assert bar._bar_below_partial is True
    assert "\x1b[5C" in output[output.rindex("\x1b[1A\r") :]
    bar.stop()


def test_midline_extension_into_margin_hides_bar():
    """Growing into the wrap-margin danger zone bails out of BOTH the
    fast path and the below-repaint -- fail closed to hidden+debounce."""
    cols = 20
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (cols, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.guarded_write("x" * 10)

    bar.guarded_write("y" * 8)  # col 18 == cols - 2: danger zone
    with bar._lock:
        bar._cancel_repaint_timer()

    assert bar._displayed_rows == 0
    assert bar._bar_below_partial is False
    bar.stop()


def test_midline_sgr_state_is_replayed_after_hop():
    """A styled run must keep its color across a below-partial repaint."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("\x1b[31mred text")

    output = tty.getvalue()
    # After the hop-back (CUU+CR), the stream's SGR state is replayed.
    hop = output.rindex("\x1b[1A\r")
    assert "\x1b[0m\x1b[31m" in output[hop:]
    assert bar._bar_below_partial is True
    bar.stop()


def test_midline_bails_to_hidden_on_unmodelable_width():
    """Tabs (and other unmodelable content) must fall back to the old
    hidden+debounce behavior -- never risk a bad hop."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)

    bar.guarded_write("col1\tcol2")
    with bar._lock:
        bar._cancel_repaint_timer()

    assert bar._displayed_rows == 0  # hidden, awaiting quiescence
    assert bar._bar_below_partial is False
    assert bar._partial.ok is False
    bar.stop()


def test_midline_bails_near_wrap_margin():
    """At/near the wrap margin the pending-wrap flag makes the hop
    ambiguous -- fail closed to hidden."""
    cols = 20
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (cols, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)

    bar.guarded_write("x" * (cols - 1))  # lands in the danger zone
    with bar._lock:
        bar._cancel_repaint_timer()

    assert bar._displayed_rows == 0
    assert bar._bar_below_partial is False
    bar.stop()


def test_midline_wrapped_line_hops_to_modulo_column():
    """A wrapped partial line restores to width % cols on its LAST row."""
    cols = 20
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (cols, 24))
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    tty.seek(0)
    tty.truncate(0)

    bar.guarded_write("x" * (cols + 5))  # wraps once, 5 cells into row 2

    output = tty.getvalue()
    assert bar._bar_below_partial is True
    assert "\x1b[5C" in output[output.rindex("\x1b[1A\r") :]
    bar.stop()


def test_spinner_tick_below_partial_repaints_below_again():
    """Bar-state ticks while below a partial line must erase (DECSC/DECRC)
    and re-paint below -- never CLEAR_LINE through the partial line."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    bar.guarded_write("streaming tokens")
    tty.seek(0)
    tty.truncate(0)

    bar.set_status("ctx 12k/200k")  # tick while below-partial

    output = tty.getvalue()
    assert bar._bar_below_partial is True
    assert "\x1b8" in output  # erase hopped back via DECRC
    assert "ctx 12k/200k" in output
    assert output.count(SYNC_ON) == 1 and output.count(SYNC_OFF) == 1
    bar.stop()


def test_completing_the_line_repaints_at_line_start():
    """When the streamed line finally completes, the below-partial state
    clears and the bar repaints at the fresh row (classic path)."""
    tty = FakeTTY()
    bar = InlineBottomBar(stream=tty, get_size=lambda: (80, 24))
    bar.start()
    bar.set_prompt_text("> ", "draft", 5)
    bar.guarded_write("streaming tokens")

    bar.guarded_write(" and done.\n")

    assert bar._bar_below_partial is False
    assert bar._displayed_rows > 0
    assert bar._partial.text == ""
    assert bar._at_line_start is True
    bar.stop()


def test_trailing_sgr_does_not_count_as_line_content():
    """Rich/termflow often end writes with a reset AFTER the newline; the
    zero-width escape must not fool the column-1 tracker."""
    bar = InlineBottomBar(stream=FakeTTY(), get_size=lambda: (80, 24))
    bar._track_line_state("styled text\n\x1b[0m")
    assert bar._at_line_start is True
    bar._track_line_state("  Calling tool... 5 token(s)   \r")
    assert bar._at_line_start is True
    bar._track_line_state("mid-line")
    assert bar._at_line_start is False


def test_foreign_guard_installs_and_restores_std_streams(monkeypatch):
    """The inline surface must intercept sys.stdout/sys.stderr while up
    (streaming bypasses output_transaction) and restore them on stop."""
    fake_out, fake_err = FakeTTY(), FakeTTY()
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    bar = InlineBottomBar(get_size=lambda: (80, 24))

    bar._install_foreign_write_guard()
    assert isinstance(sys.stdout, StreamGuard)
    assert isinstance(sys.stderr, StreamGuard)
    sys.stdout.write("hello")
    assert fake_out.getvalue() == "hello"

    bar._uninstall_foreign_write_guard()
    assert sys.stdout is fake_out
    assert sys.stderr is fake_err


def test_injected_stream_never_installs_guard():
    """Constructor-injected streams (tests, embeds) must leave the real
    std streams alone -- mirrors the Windows transcript guard rules."""
    bar = InlineBottomBar(stream=FakeTTY(), get_size=lambda: (80, 24))
    before_out, before_err = sys.stdout, sys.stderr
    bar.start()
    try:
        assert sys.stdout is before_out
        assert sys.stderr is before_err
    finally:
        bar.stop()
