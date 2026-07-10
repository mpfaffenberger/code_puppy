"""Tests for the Windows scrollback guard (transcript_guard).

Covers the pure cursor simulator, the fast-path/dance routing in
``BottomBar.guarded_write``, escape-tail withholding, the deferred-wrap
commit, the history-safe grow-scroll variant, and install gating
(Windows-only, real-stdout-only).
"""

import io
import sys

from code_puppy.messaging.bottom_bar import BottomBar
from code_puppy.messaging.transcript_guard import (
    SYNC_OFF,
    SYNC_ON,
    StreamGuard,
    feed,
    first_effective_is_printable,
)


class FakeTTY(io.StringIO):
    def isatty(self):  # pragma: no cover - trivial
        return True


def make_bar(cols=80, rows=24):
    tty = FakeTTY()
    bar = BottomBar(stream=tty, get_size=lambda: (cols, rows))
    return bar, tty


def start_bar(cols=80, rows=24):
    bar, tty = make_bar(cols, rows)
    bar.start()
    tty.seek(0)
    tty.truncate(0)  # drop the establish escapes; tests assert deltas
    return bar, tty


def drain(tty):
    value = tty.getvalue()
    tty.seek(0)
    tty.truncate(0)
    return value


# =============================================================================
# feed() — the pure cursor simulator
# =============================================================================


class TestFeed:
    def test_plain_text_advances_column(self):
        state, scrolls, tail, moved = feed((1, 1, False), "abc", 80, 24)
        assert state == (1, 4, False)
        assert scrolls == 0
        assert tail == 3
        assert moved is True

    def test_newline_is_crlf_and_scrolls_at_bottom(self):
        state, scrolls, _, _ = feed((24, 5, False), "\n", 80, 24)
        assert state == (24, 1, False)
        assert scrolls == 1

    def test_crlf_pair_advances_one_row(self):
        state, scrolls, _, _ = feed((3, 7, False), "\r\n", 80, 24)
        assert state == (4, 1, False)
        assert scrolls == 0

    def test_deferred_wrap_sets_pending_at_last_column(self):
        state, _, _, _ = feed((1, 79, False), "xy", 80, 24)
        assert state == (1, 80, True)

    def test_pending_wrap_resolves_on_next_printable(self):
        state, _, _, _ = feed((1, 80, True), "z", 80, 24)
        assert state == (2, 2, False)

    def test_pending_wrap_at_bottom_counts_scroll(self):
        _, scrolls, _, _ = feed((24, 80, True), "z", 80, 24)
        assert scrolls == 1

    def test_wide_char_wraps_when_it_cannot_fit(self):
        state, _, _, _ = feed((1, 80, False), "\U0001f436", 80, 24)
        assert state == (2, 3, False)

    def test_csi_cup_moves_absolute(self):
        state, _, _, _ = feed((1, 1, False), "\x1b[5;10H", 80, 24)
        assert state == (5, 10, False)

    def test_csi_movement_clamps(self):
        state, _, _, _ = feed((2, 3, False), "\x1b[9A\x1b[999C", 80, 24)
        assert state == (1, 80, False)

    def test_sgr_does_not_move_or_clear_pending(self):
        state, _, _, moved = feed((4, 80, True), "\x1b[31m", 80, 24)
        assert state == (4, 80, True)
        assert moved is False

    def test_osc_sequence_is_zero_width(self):
        text = "\x1b]8;;http://example.com\x07ab"
        state, _, tail, _ = feed((1, 1, False), text, 80, 24)
        assert state == (1, 3, False)
        assert tail == len(text)

    def test_incomplete_csi_tail_is_reported(self):
        state, _, tail, _ = feed((1, 1, False), "ab\x1b[3", 80, 24)
        assert state == (1, 3, False)  # only "ab" consumed
        assert tail == 2

    def test_incomplete_osc_tail_is_reported(self):
        _, _, tail, _ = feed((1, 1, False), "x\x1b]8;;unterminated", 80, 24)
        assert tail == 1

    def test_csi_scroll_up_counts_as_scroll(self):
        _, scrolls, _, _ = feed((1, 1, False), "\x1b[3S", 80, 24)
        assert scrolls == 3

    def test_carriage_return_and_backspace(self):
        state, _, _, _ = feed((5, 10, False), "\rab\b", 80, 24)
        assert state == (5, 2, False)


class TestFirstEffective:
    def test_printable(self):
        assert first_effective_is_printable("Q") is True

    def test_printable_behind_sgr(self):
        assert first_effective_is_printable("\x1b[1mQ") is True

    def test_newline_is_not(self):
        assert first_effective_is_printable("\nQ") is False

    def test_empty_and_pure_sgr(self):
        assert first_effective_is_printable("") is False
        assert first_effective_is_printable("\x1b[0m") is False


# =============================================================================
# guarded_write routing
# =============================================================================


class TestFastPath:
    def test_passthrough_is_byte_identical(self):
        bar, tty = start_bar()
        bar.guarded_write("hello")
        assert drain(tty) == "hello"
        assert (bar._sim_row, bar._sim_col) == (22, 6)

    def test_passthrough_when_region_down(self):
        bar, tty = make_bar()  # never started
        bar.guarded_write("raw")
        assert drain(tty) == "raw"

    def test_passthrough_while_suspended(self):
        bar, tty = start_bar()
        with bar.suspended():
            drain(tty)  # teardown escapes
            bar.guarded_write("x")
            assert drain(tty) == "x"

    def test_carry_withholds_incomplete_escape(self):
        bar, tty = start_bar()
        bar.guarded_write("ab\x1b[3")
        assert drain(tty) == "ab"
        assert bar._carry == "\x1b[3"
        bar.guarded_write("1mz")
        assert drain(tty) == "\x1b[31mz"
        assert bar._carry == ""

    def test_teardown_flushes_carry(self):
        bar, tty = start_bar()
        bar.guarded_write("ab\x1b[3")
        drain(tty)
        bar.stop()
        assert "\x1b[3" in drain(tty)


class TestDance:
    def test_scrolling_write_takes_the_dance(self):
        bar, tty = start_bar()  # region 1..22, sim at (22, 1)
        bar.guarded_write("one\ntwo\n")
        out = drain(tty)
        # Frame markers + margin toggling, in order.
        i_sync_on = out.index(SYNC_ON)
        i_reset = out.index("\x1b[r")
        i_text = out.index("one\ntwo\n")
        i_lfs = out.index("\x1b[24;1H\n\n")
        i_margins = out.index("\x1b[1;22r")
        i_sync_off = out.index(SYNC_OFF)
        assert i_sync_on < i_reset < i_text < i_lfs < i_margins < i_sync_off
        # Bar rows blanked before margins reset (no paint into history).
        assert out.index("\x1b[23;1H\x1b[2K") < i_reset
        # Sim re-parked at the region top.
        assert (bar._sim_row, bar._sim_col) == (22, 1)

    def test_non_scrolling_write_never_dances(self):
        bar, tty = start_bar()
        bar.guarded_write("short")
        assert SYNC_ON not in drain(tty)

    def test_dance_clears_real_wrap_flag_tracking(self):
        bar, tty = start_bar(cols=10)
        # Exactly-width line with no newline -> ends pending after dance.
        bar.guarded_write("\n" * 1 + "x" * 10)
        drain(tty)
        assert bar._sim_pending is True
        assert bar._sim_real_flag is False

    def test_wrap_commit_prepends_crlf_for_printable(self):
        bar, tty = start_bar()
        bar._sim_row, bar._sim_col = 5, 80
        bar._sim_pending, bar._sim_real_flag = True, False
        bar.guarded_write("Q")
        assert drain(tty) == "\r\nQ"
        assert (bar._sim_row, bar._sim_col) == (6, 2)

    def test_wrap_commit_skipped_for_leading_newline(self):
        bar, tty = start_bar()
        bar._sim_row, bar._sim_col = 5, 80
        bar._sim_pending, bar._sim_real_flag = True, False
        bar.guarded_write("\nQ")
        assert drain(tty) == "\nQ"


# =============================================================================
# Grow-scroll variant (_resize_reserved)
# =============================================================================


class TestGrowScroll:
    def test_guarded_grow_uses_history_safe_lfs(self):
        bar, tty = start_bar()
        bar._guard_scroll_fix = True
        bar.set_status("tokens")  # reserved 2 -> 3
        out = drain(tty)
        assert "\x1b[1S" not in out
        assert "\x1b[r" in out
        assert "\x1b[24;1H\n" in out
        assert "\x1b[1;21r" in out  # new region top
        assert bar._sim_row == 21  # cursor followed its line up

    def test_default_grow_keeps_csi_s(self):
        bar, tty = start_bar()
        bar.set_status("tokens")
        out = drain(tty)
        assert "\x1b[1S" in out
        assert "\x1b[24;1H\n" not in out


# =============================================================================
# Install gating
# =============================================================================


class TestInstall:
    def test_no_install_on_posix(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.messaging.transcript_guard.platform.system",
            lambda: "Linux",
        )
        bar = BottomBar(get_size=lambda: (80, 24))
        bar._install_transcript_guard()
        assert bar._guards == []
        assert bar._guard_scroll_fix is False

    def test_no_install_for_injected_stream(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.messaging.transcript_guard.platform.system",
            lambda: "Windows",
        )
        bar, _ = make_bar()
        bar._install_transcript_guard()
        assert bar._guards == []

    def test_install_and_uninstall_on_windows(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.messaging.transcript_guard.platform.system",
            lambda: "Windows",
        )
        fake_out, fake_err, fake_dunder = FakeTTY(), FakeTTY(), FakeTTY()
        monkeypatch.setattr(sys, "stdout", fake_out)
        monkeypatch.setattr(sys, "stderr", fake_err)
        monkeypatch.setattr(sys, "__stdout__", fake_dunder)
        bar = BottomBar(get_size=lambda: (80, 24))
        bar._install_transcript_guard()
        try:
            assert isinstance(sys.stdout, StreamGuard)
            assert isinstance(sys.stderr, StreamGuard)
            assert bar._guard_scroll_fix is True
            # Region down -> guard passthrough hits the wrapped stream.
            sys.stdout.write("through")
            assert fake_out.getvalue() == "through"
            assert sys.stdout.isatty() is True  # delegation
        finally:
            bar._uninstall_transcript_guard()
        assert sys.stdout is fake_out
        assert sys.stderr is fake_err
        assert bar._guards == []
        assert bar._guard_scroll_fix is False

    def test_no_install_when_stdout_redirected(self, monkeypatch):
        monkeypatch.setattr(
            "code_puppy.messaging.transcript_guard.platform.system",
            lambda: "Windows",
        )
        monkeypatch.setattr(sys, "stdout", io.StringIO())  # not a tty
        monkeypatch.setattr(sys, "stderr", io.StringIO())
        monkeypatch.setattr(sys, "__stdout__", FakeTTY())
        bar = BottomBar(get_size=lambda: (80, 24))
        bar._install_transcript_guard()
        assert bar._guards == []


class TestStreamGuard:
    def test_write_routes_and_reports_full_length(self):
        bar, tty = start_bar()
        guard = StreamGuard(bar, tty)
        assert guard.write("hi") == 2
        assert "hi" in drain(tty)

    def test_writelines_routes_each_line(self):
        bar, tty = start_bar()
        guard = StreamGuard(bar, tty)
        guard.writelines(["a", "b"])
        assert "ab" in drain(tty)
