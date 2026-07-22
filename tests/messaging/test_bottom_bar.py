"""Tests for code_puppy.messaging.bottom_bar - the scroll-region manager."""

import io
from unittest.mock import patch

import pytest

from code_puppy.messaging.bottom_bar import (
    RESERVED_ROWS,
    BottomBar,
    get_bottom_bar,
    reset_bottom_bar,
)

# =========================================================================
# Fakes
# =========================================================================


class FakeTTY(io.StringIO):
    """StringIO masquerading as a TTY, capturing all escape writes."""

    def isatty(self):
        return True


class FakePipe(io.StringIO):
    """StringIO that reports NOT a TTY (pipes / CI / headless)."""

    def isatty(self):
        return False


@pytest.fixture
def tty():
    return FakeTTY()


@pytest.fixture
def bar(tty):
    """A BottomBar on an 80x24 fake TTY."""
    return BottomBar(stream=tty, get_size=lambda: (80, 24))


def written(stream):
    return stream.getvalue()


def drain(stream):
    """Return captured output and reset the capture buffer."""
    value = stream.getvalue()
    stream.truncate(0)
    stream.seek(0)
    return value


def test_prompt_buffer_uses_theme_foreground(bar, tty):
    with patch("code_puppy.callbacks.on_prompt_text_color", return_value="#6a9955"):
        bar.start()
        drain(tty)
        bar.set_prompt_text("> ", "puppies", len("puppies"))

    output = written(tty)
    assert "\x1b[38;2;106;153;85m" in output
    assert "\x1b[39m" in output


def test_styled_prefix_restores_theme_foreground_for_user_text(bar, tty):
    theme_sgr = "\x1b[38;2;76;79;105m"
    with patch("code_puppy.callbacks.on_prompt_text_color", return_value="#4c4f69"):
        bar.start()
        drain(tty)
        bar.set_prompt_text(
            "> ", "readable latte", len("readable latte"), ["1;34", "1;34"]
        )

    output = written(tty)
    prefix_reset = output.index("\x1b[0m")
    user_text = output.index("readable latte")

    assert theme_sgr in output[prefix_reset:user_text]


# =========================================================================
# Non-TTY: silent no-ops
# =========================================================================


def test_non_tty_start_is_noop():
    pipe = FakePipe()
    bar = BottomBar(stream=pipe, get_size=lambda: (80, 24))
    bar.start()
    assert written(pipe) == ""
    assert bar.is_active() is False


def test_non_tty_all_methods_are_silent():
    pipe = FakePipe()
    bar = BottomBar(stream=pipe, get_size=lambda: (80, 24))
    bar.start()
    bar.set_status("tokens: 123")
    bar.set_prompt_text("> ", "hello", 5)
    with bar.suspended():
        pass
    bar.stop()
    assert written(pipe) == ""


def test_none_stream_is_silent(monkeypatch):
    bar = BottomBar(get_size=lambda: (80, 24))
    monkeypatch.setattr("sys.__stdout__", None)
    bar.start()  # must not raise
    assert bar.is_active() is False


# =========================================================================
# start / stop
# =========================================================================


def test_start_establishes_region(bar, tty):
    bar.start()
    out = written(tty)
    # 24-row terminal, empty status (hidden): scrollable region rows 1..22.
    assert "\n" * RESERVED_ROWS in out
    assert "\x1b[1;22r" in out
    # Cursor parked INSIDE the region (bottom of scrollable area).
    assert "\x1b[22;1H" in out
    assert bar.is_active() is True


def test_start_paints_reserved_rows(bar, tty):
    bar.start()
    out = written(tty)
    assert "\x1b[23;1H\x1b[2K" in out  # top margin (transcript separator)
    assert "\x1b[24;1H\x1b[2K" in out  # prompt row (bottom -- no status yet)


def test_start_is_idempotent(bar, tty):
    bar.start()
    drain(tty)
    bar.start()
    assert written(tty) == ""


def test_stop_restores_terminal(bar, tty):
    bar.start()
    drain(tty)
    bar.stop()
    out = written(tty)
    assert "\x1b[r" in out
    for row in (23, 24):
        assert f"\x1b[{row};1H\x1b[2K" in out
    assert bar.is_active() is False


def test_stop_is_idempotent(bar, tty):
    bar.start()
    bar.stop()
    drain(tty)
    bar.stop()
    assert written(tty) == ""


def test_stop_without_start_is_noop(bar, tty):
    bar.stop()
    assert written(tty) == ""


def test_tiny_terminal_stays_dormant(tty):
    bar = BottomBar(stream=tty, get_size=lambda: (80, 2))
    bar.start()
    # No room for a scrollable area: no DECSTBM emitted.
    assert "r" not in written(tty).replace("\r", "")
    assert bar.is_active() is True  # still "started", just dormant


# =========================================================================
# set_status
# =========================================================================


def test_set_status_materializes_row_below_prompt(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("tokens: 1234")
    out = written(tty)
    # First non-empty status: the row materializes on the BOTTOM row --
    # the region scrolls up one line and shrinks (reserved 2 -> 3).
    assert "\x1b[1S" in out
    assert "\x1b[1;21r" in out
    assert "\x1b[24;1H\x1b[2K\x1b[2mtokens: 1234\x1b[22m" in out  # dim chrome


def test_set_status_repaint_keeps_cursor_bracketing(bar, tty):
    bar.start()
    bar.set_status("first")
    drain(tty)
    bar.set_status("second")  # same reserved count -> plain repaint
    out = written(tty)
    assert "\x1b[24;1H\x1b[2K\x1b[2msecond\x1b[22m" in out
    # Save/restore cursor bracketing so streaming output is undisturbed.
    assert out.startswith("\x1b7")
    assert out.endswith("\x1b8")


def test_empty_status_collapses_row(bar, tty):
    bar.start()
    bar.set_status("visible")
    drain(tty)
    bar.set_status("")
    out = written(tty)
    assert "\x1b[1;22r" in out  # region grows back over the freed row


def test_set_status_truncates_to_width(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("x" * 200)
    assert "x" * 80 in written(tty)
    assert "x" * 81 not in written(tty)


def test_set_status_strips_control_chars(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("a\x1b[31mb\x07c")
    out = written(tty)
    assert "\x1b[24;1H\x1b[2K\x1b[2ma[31mbc\x1b[22m" in out
    assert "\x07" not in out


def test_set_status_while_inactive_only_caches(bar, tty):
    bar.set_status("cached")
    assert written(tty) == ""
    bar.start()
    assert "cached" in written(tty)


# =========================================================================
# set_status_prefix (spinner slot)
# =========================================================================


def test_status_prefix_paints_before_status(bar, tty):
    bar.start()
    bar.set_status("tokens: 1234")
    drain(tty)
    bar.set_status_prefix("(pup) thinking... ")
    assert "(pup) thinking... tokens: 1234" in written(tty)


def test_status_suffix_paints_after_status(bar, tty):
    bar.start()
    bar.set_status("tokens: 42")
    drain(tty)
    bar.set_status_suffix(" (2 queued)")
    assert "tokens: 42 (2 queued)" in written(tty)


def test_status_suffix_alone_materializes_row(bar, tty):
    """A queued-count with no token info yet still shows the row."""
    bar.start()
    drain(tty)
    bar.set_status_suffix(" (1 queued)")
    out = written(tty)
    assert "\x1b[1S" in out  # row materialized (reserved 2 -> 3)
    assert "(1 queued)" in out
    drain(tty)
    bar.set_status_suffix("")
    assert "\x1b[1;22r" in written(tty)  # collapses again


def test_reserved_grow_preserves_transcript_cursor(bar, tty):
    """Growing the reserved area must FOLLOW the transcript cursor, not
    park at ``top;1``: the grow-scroll moves a half-typed streaming line
    up onto the new region bottom, so a blind park put the cursor at
    column 1 ON that line and the smooth typewriter overwrote its head
    (the mangled-response artifact)."""
    bar.start()
    drain(tty)
    bar.set_status("tokens: 1")  # status row materializes: reserved 2 -> 3
    out = written(tty)
    # Save -> scroll -> DECSTBM -> restore -> follow content up one row.
    assert "\x1b7\x1b[1S\x1b[1;21r\x1b8\x1b[1A" in out
    # No blind park at the new region bottom.
    assert "\x1b[21;1H" not in out


def test_reserved_shrink_preserves_transcript_cursor(bar, tty):
    """Shrinking clears the vacated row but restores the cursor exactly
    (content doesn't move on shrink — no CUU adjustment)."""
    bar.start()
    bar.set_status("tokens: 1")
    drain(tty)
    bar.set_status("")  # status row collapses: reserved 3 -> 2
    out = written(tty)
    # Save -> clear vacated row -> DECSTBM -> restore (no ESC[nA).
    assert "\x1b7\x1b[22;1H\x1b[2K\x1b[1;22r\x1b8" in out
    assert "\x1b8\x1b[1A" not in out


def test_status_prefix_and_status_are_independent_slots(bar, tty):
    """Each writer owns its slot: updating one never erases the other."""
    bar.start()
    bar.set_status_prefix("(pup) ")
    drain(tty)
    bar.set_status("tokens: 9")  # context writer repaints...
    assert "(pup) tokens: 9" in written(tty)  # ...spinner survives
    drain(tty)
    bar.set_status_prefix("")  # spinner clears...
    out = written(tty)
    assert "tokens: 9" in out  # ...context survives
    assert "(pup)" not in out


# =========================================================================
# set_prompt_text
# =========================================================================


def test_set_prompt_text_paints_prompt_row(bar, tty):
    bar.start()
    drain(tty)
    bar.set_prompt_text("› ", "hi", 2)
    out = written(tty)
    # Prompt on the bottom row (status hidden), cursor as reverse-video.
    assert "\x1b[24;1H\x1b[2K› hi\x1b[7m \x1b[27m" in out


def test_set_prompt_text_cursor_mid_buffer(bar, tty):
    bar.start()
    drain(tty)
    bar.set_prompt_text("> ", "abc", 1)
    # Cursor sits on 'b': "> a" + reverse(b) + "c"
    assert "> a\x1b[7mb\x1b[27mc" in written(tty)


def test_set_prompt_text_soft_wraps_long_lines(bar, tty):
    """Phase B follow-up: long single-line input GROWS the viewport and
    soft-wraps instead of scrolling horizontally."""
    bar.start()
    drain(tty)
    long = "a" * 200
    bar.set_prompt_text("> ", long, 200)
    out = written(tty)
    # 202 chars @ 80 cols -> 3 visual rows: reserved 4 -> region 1..20.
    assert "\x1b[1;20r" in out
    assert "> a" in out  # the head stays visible (wrapped, not scrolled)
    assert "\x1b[7m \x1b[27m" in out  # cursor cell on the last row


def test_set_prompt_text_while_inactive_only_caches(bar, tty):
    bar.set_prompt_text("> ", "later", 5)
    assert written(tty) == ""
    bar.start()
    assert "> later" in written(tty)


# =========================================================================
# set_panel_lines (sub-agent panel rows)
# =========================================================================


def test_panel_grow_scrolls_then_shrinks_region(bar, tty):
    bar.start()
    drain(tty)
    bar.set_panel_lines(["agent one", "agent two"])
    out = written(tty)
    # Content scrolled up 2 lines so the new reserved rows start blank.
    assert "\x1b[2S" in out
    # Region shrinks: 24 rows - (2 base + 2 panel) = 1..20.
    assert "\x1b[1;20r" in out
    # Cursor restored to the transcript position and moved up with the
    # scrolled content (2 rows) — never blind-parked at ``top;1``, which
    # used to overwrite half-typed streaming lines.
    assert "\x1b7\x1b[2S\x1b[1;20r\x1b8\x1b[2A" in out
    assert "\x1b[20;1H" not in out
    # Panel rows painted at rows 22-23 (above the prompt row 24).
    assert "\x1b[22;1H\x1b[2K\x1b[2magent one\x1b[22m" in out
    assert "\x1b[23;1H\x1b[2K\x1b[2magent two\x1b[22m" in out


def test_panel_collapse_clears_vacated_rows(bar, tty):
    bar.start()
    bar.set_panel_lines(["a", "b"])
    drain(tty)
    bar.set_panel_lines([])
    out = written(tty)
    # Vacated rows 21-22 are cleared before returning to the region.
    assert "\x1b[21;1H\x1b[2K" in out
    assert "\x1b[22;1H\x1b[2K" in out
    # Region grows back to 1..22.
    assert "\x1b[1;22r" in out


def test_panel_same_count_repaints_without_region_change(bar, tty):
    bar.start()
    bar.set_panel_lines(["a", "b"])
    drain(tty)
    bar.set_panel_lines(["x", "y"])
    out = written(tty)
    assert "\x1b[22;1H\x1b[2K\x1b[2mx\x1b[22m" in out
    assert "\x1b[23;1H\x1b[2K\x1b[2my\x1b[22m" in out
    assert "r" not in out.replace("\r", "")  # no DECSTBM re-issue


def test_panel_retains_every_row(bar, tty):
    lines = [f"line{i}" for i in range(10)]
    bar.start()
    drain(tty)
    bar.set_panel_lines(lines)

    out = written(tty)

    assert bar.get_panel_lines() == lines
    # Region for 2 base + 10 panel rows: 1..12.
    assert "\x1b[1;12r" in out
    assert "\x1b[14;1H\x1b[2K\x1b[2mline0\x1b[22m" in out
    assert "\x1b[23;1H\x1b[2K\x1b[2mline9\x1b[22m" in out


def test_panel_and_status_coexist(bar, tty):
    bar.start()
    bar.set_panel_lines(["panel row"])
    drain(tty)
    bar.set_status("Tokens: 5/10")
    out = written(tty)
    # Status takes the bottom row (24); panel sits above the prompt.
    assert "\x1b[24;1H\x1b[2K\x1b[2mTokens: 5/10\x1b[22m" in out
    assert bar.get_panel_lines() == ["panel row"]


def test_panel_sanitizes_control_chars(bar, tty):
    bar.start()
    drain(tty)
    bar.set_panel_lines(["a\x1b[31mb\x07c"])
    assert "\x1b[23;1H\x1b[2K\x1b[2ma[31mbc\x1b[22m" in written(tty)


def test_panel_styled_text_row_paints_sgrs_undimmed(bar, tty):
    from rich.text import Text

    bar.start()
    drain(tty)
    row = Text()
    row.append(" INVOKE AGENT ", style="bold white on red")
    row.append(" worker")
    bar.set_panel_lines([row])
    out = written(tty)
    assert " INVOKE AGENT " in out
    assert " worker" in out
    # Styled segments carry regenerated SGRs (with a trailing reset)...
    assert "\x1b[0m" in out
    # ...and styled rows are NOT flattened to dim chrome.
    assert "\x1b[2m" not in out


def test_panel_styled_text_content_still_sanitized(bar, tty):
    from rich.text import Text

    bar.start()
    drain(tty)
    bar.set_panel_lines([Text("evil\x1b[31m\x07name", style="bold")])
    out = written(tty)
    # In-band escapes smuggled in the CONTENT are stripped; only the
    # trusted Style's own SGR bytes survive.
    assert "evil[31mname" in out


def test_panel_while_inactive_only_caches(bar, tty):
    bar.set_panel_lines(["cached row"])
    assert written(tty) == ""
    bar.start()
    assert "cached row" in written(tty)


# =========================================================================
# Chrome dimming (popup/status/panel read as UI, not transcript content)
# =========================================================================


def test_popup_nonselected_rows_dim_selected_accent_not_dim(bar, tty):
    bar.start()
    drain(tty)
    bar.set_popup_lines(["/alpha", "/beta", "/gamma"], selected=1)
    out = written(tty)
    assert "\x1b[2m/alpha\x1b[22m" in out  # non-selected: dim
    assert "\x1b[2m/gamma\x1b[22m" in out
    # Selected: full-brightness brand accent (bold + ANSI cyan — the
    # theme plugin remaps the cyan palette slot via OSC 4).
    assert "\x1b[1;36m/beta\x1b[22;39m" in out
    # No reverse video on any popup row (the \x1b[7m elsewhere in the
    # paint is the prompt row's pseudo-cursor, which keeps it).
    for row in ("/alpha", "/beta", "/gamma"):
        assert f"\x1b[7m{row}" not in out
    assert "\x1b[2m/beta" not in out  # ...and NOT dimmed


def test_popup_sanitizes_before_dimming(bar, tty):
    """Completer-embedded escapes are stripped; only OUR chrome SGR
    survives, wrapped around the sanitized text."""
    bar.start()
    drain(tty)
    bar.set_popup_lines(["/a\x1b[31mred\x07"], selected=-1)
    out = written(tty)
    assert "\x1b[31m" not in out
    assert "\x07" not in out
    assert "\x1b[2m/a[31mred\x1b[22m" in out


def test_popup_clip_happens_before_styling(bar, tty):
    """Clip math operates on the pre-styled string: a full-width row is
    clipped to the terminal width, THEN wrapped in SGR — the dim bytes
    never eat visible cells."""
    from rich.cells import cell_len

    bar.start()
    drain(tty)
    bar.set_popup_lines(["x" * 200], selected=-1)
    out = written(tty)
    start = out.index("\x1b[2mx") + len("\x1b[2m")
    end = out.index("\x1b[22m", start)
    visible = out[start:end]
    assert cell_len(visible) == 80  # exactly terminal width, all x's
    assert visible == "x" * 80


def test_popup_below_prompt_slides_prompt_up_but_not_back(bar, tty):
    """IDE-dropdown motion: popup opens UNDER the typed line (prompt
    slides up). On close the prompt STAYS PUT — the vacated rows become
    blank slack awaiting lazy reclaim (no idle-time teleporting)."""
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)  # prompt at 24 (status hidden)
    drain(tty)
    bar.set_popup_lines(["/one", "/two"], selected=0)
    out = written(tty)
    # Reserved 4 -> region 1..20; popup rows 23-24; prompt slid to 22.
    assert "\x1b[1;20r" in out
    assert "\x1b[22;1H\x1b[2K> hi" in out
    assert "\x1b[23;1H\x1b[2K\x1b[1;36m/one\x1b[22;39m" in out  # adjacent row
    assert "\x1b[24;1H\x1b[2K\x1b[2m/two\x1b[22m" in out
    drain(tty)
    bar.set_popup_lines([])
    out = written(tty)
    assert "\x1b[1;22r" not in out  # region does NOT grow back yet
    # The prompt is NOT repainted anywhere — it never moved off row 22.
    assert "> hi" not in out
    # The vacated popup rows are actively blanked (no stale menu paint).
    assert "\x1b[23;1H\x1b[2K" in out
    assert "\x1b[24;1H\x1b[2K" in out
    assert "/one" not in out and "/two" not in out


def test_popup_slack_reclaimed_one_row_per_output(bar, tty):
    """notify_transcript_output releases ONE slack row per call: the
    prompt STEPS down with the flow of output instead of teleporting
    on the first message (e.g. the submit echo)."""
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.set_popup_lines(["/one", "/two"], selected=0)
    bar.set_popup_lines([])  # close -> slack of 2, prompt still at 22
    drain(tty)
    bar.notify_transcript_output()  # first message: one row back
    out = written(tty)
    assert "\x1b[1;21r" in out  # region grows by ONE row only
    assert "\x1b[23;1H\x1b[2K> hi" in out  # prompt steps to 23
    assert "\x1b[1;22r" not in out  # NOT all the way down yet
    drain(tty)
    bar.notify_transcript_output()  # second message: last row back
    out = written(tty)
    assert "\x1b[1;22r" in out  # region fully restored
    assert "\x1b[24;1H\x1b[2K> hi" in out  # prompt back at the bottom
    drain(tty)
    bar.notify_transcript_output()  # no slack left: no writes at all
    assert written(tty) == ""


def test_popup_reopen_reuses_slack_without_scrolling(bar, tty):
    """Reopening the menu while slack is pending reuses the reserved
    rows: no region change, no fresh scroll-up."""
    bar.start()
    bar.set_prompt_text("> ", "hi", 2)
    bar.set_popup_lines(["/one", "/two"], selected=0)
    bar.set_popup_lines([])  # close -> slack 2
    drain(tty)
    bar.set_popup_lines(["/one", "/two"], selected=1)
    out = written(tty)
    # No region change and no fresh scroll-up — the rows were reused,
    # and the prompt (still parked at 22) needed no repaint at all.
    assert "\x1b[1;20r" not in out and "\x1b[1;22r" not in out
    assert "\x1b[2S" not in out
    assert "> hi" not in out
    assert "\x1b[23;1H\x1b[2K\x1b[2m/one\x1b[22m" in out
    assert "\x1b[24;1H\x1b[2K\x1b[1;36m/two\x1b[22;39m" in out


def test_popup_sheds_rows_when_terminal_short_prompt_wins():
    """Tight space: popup shrinks first; prompt viewport keeps its rows
    and the bar never goes dormant just because a menu opened."""
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (80, 10))
    bar.start()
    buffer = "one\ntwo\nthree\nfour\nfive"  # 5 prompt rows (cap)
    bar.set_prompt_text("> ", buffer, len(buffer))
    drain(tty)
    bar.set_popup_lines(["/a", "/b", "/c", "/d"], selected=0)
    out = written(tty)
    # Budget: 10 - 5 prompt - (margin+status+scroll) = 2 popup rows.
    assert "/a" in out and "/b" in out
    assert "/c" not in out and "/d" not in out
    # Reserved = 1+5+2 = 8 -> region 1..2, not dormant.
    assert "\x1b[1;2r" in out
    assert bar.is_active()
    bar.stop()


def test_status_row_is_dim_chrome(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("Tokens: 900/200k")
    assert "\x1b[2mTokens: 900/200k\x1b[22m" in written(tty)


def test_empty_status_row_has_no_stray_sgr(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("")
    out = written(tty)
    assert "\x1b[2m" not in out  # _dim() no-ops on empty text


def test_panel_too_tall_for_terminal_clamps_with_overflow(tty):
    """A panel taller than the terminal no longer blanks the whole bar:
    it clamps to the rows that fit and collapses the remainder into a
    '+N more' summary, keeping the prompt + status on screen."""
    bar = BottomBar(stream=tty, get_size=lambda: (80, 6))
    bar.start()  # 2 reserved + 1 scrollable fits in 6 rows
    assert "\x1b[1;4r" in written(tty)
    drain(tty)
    bar.set_panel_lines(["a", "b", "c", "d"])  # 4 rows, only 3 fit
    out = written(tty)
    # NOT dormant: budget is 3 (6 - 1 margin - 1 prompt - 1 scroll), so
    # 2 rows show + a summary. Reserved = 5 -> region re-established at 1;1.
    assert "\x1b[1;1r" in out
    assert "+2 more" in out  # the 2 clamped rows collapse into a summary
    assert bar.is_active()
    # The raw panel state still holds every row (clamp is render-only).
    assert bar.get_panel_lines() == ["a", "b", "c", "d"]
    bar.stop()


def test_panel_all_rows_render_when_they_fit(bar, tty):
    """On a roomy terminal every tracked agent renders -- no summary."""
    lines = [f"agent-{i}" for i in range(12)]
    bar.start()
    drain(tty)
    bar.set_panel_lines(lines)
    out = written(tty)
    for i in range(12):
        assert f"agent-{i}" in out
    assert "more" not in out  # no overflow summary when everything fits


def test_panel_user_ceiling_clamps_rows_without_losing_raw_state(bar, tty):
    lines = [f"agent-{i}" for i in range(6)]
    bar.start()
    bar.set_panel_max_rows(4)
    drain(tty)
    bar.set_panel_lines(lines)
    out = written(tty)

    assert "agent-0" in out and "agent-1" in out and "agent-2" in out
    assert "agent-3" not in out
    assert "+3 more" in out
    assert bar.get_panel_lines() == lines


def test_panel_zero_ceiling_restores_automatic_sizing(bar, tty):
    lines = [f"agent-{i}" for i in range(6)]
    bar.start()
    bar.set_panel_max_rows(2)
    bar.set_panel_lines(lines)
    drain(tty)

    bar.set_panel_max_rows(0)
    out = written(tty)

    for line in lines:
        assert line in out
    assert "more" not in out


def test_terminal_height_wins_over_larger_user_ceiling(tty):
    bar = BottomBar(stream=tty, get_size=lambda: (80, 6))
    bar.set_panel_max_rows(12)
    bar.start()
    drain(tty)
    bar.set_panel_lines(["a", "b", "c", "d"])

    out = written(tty)
    assert "+2 more" in out
    assert bar._panel_row_budget() == 3
    bar.stop()


def test_teardown_clears_panel_rows_too(bar, tty):
    bar.start()
    bar.set_panel_lines(["a", "b"])
    drain(tty)
    bar.stop()
    out = written(tty)
    for row in (21, 22, 23, 24):
        assert f"\x1b[{row};1H\x1b[2K" in out


# =========================================================================
# suspended()
# =========================================================================


def test_suspended_tears_down_and_restores(bar, tty):
    bar.start()
    drain(tty)
    with bar.suspended():
        out = drain(tty)
        assert "\x1b[r" in out  # region reset
        for row in (23, 24):
            assert f"\x1b[{row};1H\x1b[2K" in out  # rows cleared
    out = written(tty)
    assert "\x1b[1;22r" in out  # region re-established
    assert bar.is_active() is True


def test_suspended_is_reentrant(bar, tty):
    bar.start()
    drain(tty)
    with bar.suspended():
        drain(tty)
        with bar.suspended():
            pass
        # Inner exit must NOT re-establish the region.
        assert written(tty) == ""
    assert "\x1b[1;22r" in written(tty)


def test_suspended_when_inactive_is_noop(bar, tty):
    with bar.suspended():
        pass
    assert written(tty) == ""


def test_stop_inside_suspended_does_not_reestablish(bar, tty):
    bar.start()
    with bar.suspended():
        bar.stop()
        drain(tty)
    assert written(tty) == ""


# =========================================================================
# Resize (lazy geometry poll — the Windows path)
# =========================================================================


def test_repaint_reestablishes_on_resize(tty):
    size = [(80, 24)]
    bar = BottomBar(stream=tty, get_size=lambda: size[0])
    bar.start()
    drain(tty)
    size[0] = (100, 30)
    bar.set_status("after resize")
    out = written(tty)
    assert "\x1b[1;27r" in out  # new region for 30 rows (status visible)
    assert "after resize" in out


def test_sigwinch_handler_only_invalidates_geometry(tty):
    """The signal handler must NOT paint (it can interrupt _establish on
    the same thread and re-enter through the RLock); it just invalidates
    the cached geometry so the next repaint re-establishes."""
    size = [(80, 24)]
    bar = BottomBar(stream=tty, get_size=lambda: size[0])
    bar.start()
    drain(tty)
    size[0] = (80, 40)
    bar._on_resize()
    assert written(tty) == ""  # no immediate paint from the handler
    bar.set_status("poke")  # next repaint picks up the new size
    assert "\x1b[1;37r" in written(tty)


# =========================================================================
# Phase 6: sanitization hardening (C1 + Cf)
# =========================================================================


def test_panel_strips_c1_single_byte_csi(bar, tty):
    """U+009B is a one-byte CSI — a model-controlled agent name carrying
    it must not be able to smuggle escape sequences into reserved rows."""
    bar.start()
    drain(tty)
    bar.set_panel_lines(["helper\u009b2J"])
    out = written(tty)
    assert "\u009b" not in out
    assert "helper2J" in out  # payload neutered, text preserved


def test_panel_strips_all_c1_controls(bar, tty):
    bar.start()
    drain(tty)
    bar.set_panel_lines(["a" + "".join(chr(c) for c in range(0x80, 0xA0)) + "b"])
    out = drain(tty)
    for c in range(0x80, 0xA0):
        assert chr(c) not in out
    assert "ab" in out


def test_status_strips_format_chars_bidi_zwj(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("safe\u202etxet\u200dend")  # RLO override + ZWJ
    out = written(tty)
    assert "\u202e" not in out
    assert "\u200d" not in out
    assert "safetxetend" in out


# =========================================================================
# Phase 6: emergency restore (atexit)
# =========================================================================


def test_start_registers_atexit_once(bar, tty):
    assert bar._atexit_registered is False
    bar.start()
    assert bar._atexit_registered is True
    bar.stop()
    bar.start()  # second start must not double-register
    assert bar._atexit_registered is True


def test_emergency_restore_resets_live_region(bar, tty):
    bar.start()
    drain(tty)
    bar._emergency_restore()
    out = written(tty)
    assert "\x1b[r" in out  # region reset
    assert "\x1b[2K" in out  # reserved rows cleared


def test_emergency_restore_after_normal_stop_only_shows_cursor(bar, tty):
    """After a clean stop there's no region to reset — but the cursor-show
    is UNCONDITIONAL (visible cursor = the safe failure mode)."""
    bar.start()
    bar.stop()
    drain(tty)
    bar._emergency_restore()
    out = written(tty)
    # Cursor-show + paste-off + modkeys-off only: no region reset.
    assert out == "\x1b[?25h\x1b[?2004l\x1b[>4;0m"


def test_emergency_restore_never_started_only_shows_cursor(bar, tty):
    bar._emergency_restore()
    assert written(tty) == "\x1b[?25h\x1b[?2004l\x1b[>4;0m"


def test_emergency_restore_non_tty_is_silent():
    pipe = FakePipe()
    bar = BottomBar(stream=pipe, get_size=lambda: (80, 24))
    bar._emergency_restore()
    assert pipe.getvalue() == ""


# =========================================================================
# Rogue-cursor fix: DECTCEM hide/show lifecycle
# =========================================================================


def test_start_hides_hardware_cursor(bar, tty):
    bar.start()
    out = written(tty)
    assert "\x1b[?25l" in out
    # Hide precedes the region setup so the cursor never blinks mid-paint.
    assert out.index("\x1b[?25l") < out.index("\x1b[1;22r")


def test_stop_shows_hardware_cursor(bar, tty):
    bar.start()
    drain(tty)
    bar.stop()
    assert "\x1b[?25h" in written(tty)


def test_hide_show_are_idempotent(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("repaint")  # repaints must not re-emit DECTCEM
    assert "\x1b[?25l" not in written(tty)
    drain(tty)
    bar.stop()
    assert written(tty).count("\x1b[?25h") == 1
    drain(tty)
    bar.stop()  # idempotent stop: no extra show
    assert written(tty) == ""


def test_suspend_shows_cursor_then_rehides_on_exit(bar, tty):
    bar.start()
    drain(tty)
    with bar.suspended():
        # prompt_toolkit menus / input prompts need the real cursor back.
        assert "\x1b[?25h" in drain(tty)
    # Region re-established on exit -> pseudo-cursor takes over again.
    out = written(tty)
    assert "\x1b[?25l" in out


def test_dormant_transition_restores_cursor(tty):
    size = [(80, 24)]
    bar = BottomBar(stream=tty, get_size=lambda: size[0])
    bar.start()
    drain(tty)
    size[0] = (80, 3)  # too small for any region
    bar.set_status("poke")  # geometry poll -> dormant teardown
    out = written(tty)
    assert "\x1b[r" in out
    assert "\x1b[?25h" in out


def test_swarm_cancel_panel_clear_keeps_cursor_hidden(bar, tty, monkeypatch):
    """Ctrl+C swarm cancel clears panel rows but the RUN CONTINUES — the
    bar stays up and the hardware cursor must stay hidden."""
    from code_puppy.tools.command_runner import _tear_down_live_panels

    bar.start()
    bar.set_panel_lines(["worker one"])
    drain(tty)
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    _tear_down_live_panels()
    out = written(tty)
    assert "\x1b[?25h" not in out  # cursor stays hidden
    assert bar.is_active() is True


def test_non_tty_never_emits_cursor_sequences():
    pipe = FakePipe()
    bar = BottomBar(stream=pipe, get_size=lambda: (80, 24))
    bar.start()
    bar.stop()
    with bar.suspended():
        pass
    assert pipe.getvalue() == ""


# =========================================================================
# Phase 6: cell-width truncation (emoji / CJK)
# =========================================================================


def test_status_truncates_by_cells_not_codepoints(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("\U0001f436" * 50)  # 100 cells on an 80-col terminal
    out = written(tty)
    assert "\U0001f436" * 40 in out  # 80 cells fit
    assert "\U0001f436" * 41 not in out  # the 41st would wrap the row


def test_panel_truncates_by_cells(bar, tty):
    bar.start()
    drain(tty)
    bar.set_panel_lines(["\u6c49" * 60])  # CJK: 120 cells
    out = written(tty)
    assert "\u6c49" * 40 in out
    assert "\u6c49" * 41 not in out


def test_reserved_row_paints_disable_autowrap(bar, tty):
    bar.start()
    drain(tty)
    bar.set_status("x")
    out = drain(tty)
    assert "\x1b[?7l" in out and "\x1b[?7h" in out
    bar.set_panel_lines(["row"])
    out = drain(tty)
    assert "\x1b[?7l" in out and "\x1b[?7h" in out


def test_prompt_window_measured_in_cells(bar, tty):
    from rich.cells import cell_len

    bar.start()
    drain(tty)
    bar.set_prompt_text("> ", "\u6c49" * 100, 100)  # cursor at end, 200 cells
    out = written(tty)
    # Extract the LAST prompt row's payload and measure real cells.
    payload = out.split("\x1b[24;1H\x1b[2K", 1)[1].split("\x1b[?7h", 1)[0]
    visible = payload.replace("\x1b[7m", "").replace("\x1b[27m", "")
    assert cell_len(visible) <= 80
    assert "\u6c49" in visible  # left context shown, cursor at right edge


# =========================================================================
# Phase 6: teardown re-polls geometry (resize while suspended)
# =========================================================================


def test_stop_clears_rows_of_current_size_after_resize(tty):
    size = [(80, 24)]
    bar = BottomBar(stream=tty, get_size=lambda: size[0])
    bar.start()
    size[0] = (80, 30)  # terminal grew; cached geometry is stale
    drain(tty)
    bar.stop()
    out = written(tty)
    for row in (29, 30):  # bottom rows of the CURRENT size
        assert f"\x1b[{row};1H\x1b[2K" in out


# =========================================================================
# Singleton
# =========================================================================


def test_singleton_identity_and_reset():
    reset_bottom_bar()
    a = get_bottom_bar()
    b = get_bottom_bar()
    assert a is b
    reset_bottom_bar()
    assert get_bottom_bar() is not a
    reset_bottom_bar()
