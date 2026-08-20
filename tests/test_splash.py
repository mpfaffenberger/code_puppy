"""Tests for the import-time neon splash (code_puppy/splash.py)."""

import io
import re
import time

from code_puppy import splash

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class FakeTty(io.StringIO):
    def isatty(self):
        return True


class TestGating:
    def test_non_tty_gets_null_splash(self):
        result = splash.start_splash(stream=io.StringIO())
        assert isinstance(result, splash._NullSplash)

    def test_headless_argv_gets_null_splash(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["code-puppy", "-p", "do the thing"])
        result = splash.start_splash(stream=FakeTty())
        assert isinstance(result, splash._NullSplash)
        result.stop()  # must be a harmless no-op

    def test_interactive_argv_wants_splash(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["code-puppy", "-i"])
        monkeypatch.delenv("CODE_PUPPY_NO_SPLASH", raising=False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert splash._wants_splash(["code-puppy", "-i"]) is True

    def test_env_kill_switch(self, monkeypatch):
        monkeypatch.setenv("CODE_PUPPY_NO_SPLASH", "1")
        assert splash._wants_splash(["code-puppy"]) is False

    def test_no_color_respected(self, monkeypatch):
        monkeypatch.delenv("CODE_PUPPY_NO_SPLASH", raising=False)
        monkeypatch.setenv("NO_COLOR", "1")
        assert splash._wants_splash(["code-puppy"]) is False

    def test_dumb_term_skipped(self, monkeypatch):
        monkeypatch.delenv("CODE_PUPPY_NO_SPLASH", raising=False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        assert splash._wants_splash(["code-puppy"]) is False


FULL = splash._compose_rows(120, 50)


class TestFrame:
    def test_full_lockup_dimensions(self):
        frame = splash._build_frame(0, True, FULL)
        lines = frame.splitlines()
        assert len(lines) == len(FULL)
        allowed = set(" \u2591\u2592\u2588") | splash._SHADOW_TRIM
        for line in lines:
            visible = ANSI_RE.sub("", line)
            assert len(visible) <= splash._TAGLINE_TOP_WIDTH + 8
            assert set(visible) <= allowed

    def test_sheen_moves_between_phases(self):
        assert splash._build_frame(0, True, FULL) != splash._build_frame(20, True, FULL)

    def test_fallback_palette_has_no_truecolor_codes(self):
        frame = splash._build_frame(0, False, FULL)
        assert "38;2;" not in frame

    def test_baked_figlet_matches_pyfiglet(self):
        import pyfiglet

        for text, baked in (
            ("Powered by", splash._TAGLINE_TOP),
            ("Pydantic", splash._TAGLINE_BOTTOM),
        ):
            rendered = pyfiglet.figlet_format(text, font="ansi_shadow", width=300)
            lines = [ln.rstrip() for ln in rendered.splitlines()]
            while lines and not lines[-1]:
                lines.pop()
            assert tuple(lines) == baked, f"baked figlet drifted for {text!r}"


class TestComposeRows:
    def test_wide_terminal_gets_full_lockup(self):
        kinds = [k for k, _ in splash._compose_rows(120, 50)]
        assert kinds.count("art") == len(splash._PYRAMID)
        assert kinds.count("text") == 1 + len(splash._TAGLINE_TOP) + 1 + len(
            splash._TAGLINE_BOTTOM
        )

    def test_medium_terminal_gets_pydantic_only(self):
        rows = splash._compose_rows(70, 50)
        text_rows = [c for k, c in rows if k == "text" and c]
        assert len(text_rows) == len(splash._TAGLINE_BOTTOM)

    def test_narrow_terminal_gets_pyramid_only(self):
        rows = splash._compose_rows(50, 50)
        assert all(k == "art" for k, _ in rows)

    def test_short_terminal_drops_text(self):
        rows = splash._compose_rows(120, 22)
        assert all(k == "art" for k, _ in rows)

    def test_pyramid_centered_over_text(self):
        rows = splash._compose_rows(120, 50)
        # Compare a row against its unpadded source: the pad is the diff.
        idx = max(range(len(splash._PYRAMID)), key=lambda i: len(splash._PYRAMID[i]))
        pad = len(rows[idx][1]) - len(splash._PYRAMID[idx])
        assert pad == (splash._TAGLINE_TOP_WIDTH - splash._PYRAMID_WIDTH) // 2

    def test_pydantic_block_centered_under_powered_by(self):
        rows = splash._compose_rows(120, 50)
        text_lines = [c for k, c in rows if k == "text" and c]
        bottom = text_lines[-len(splash._TAGLINE_BOTTOM) :]
        expected_pad = (splash._TAGLINE_TOP_WIDTH - splash._TAGLINE_BOTTOM_WIDTH) // 2
        for line in bottom:
            assert line.startswith(" " * expected_pad)
            assert not line.startswith(" " * (expected_pad + 1))


class TestLifecycle:
    def test_start_animate_stop(self):
        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0)
        assert isinstance(handle, splash._Splash)
        time.sleep(0.15)  # let a few frames render
        handle.stop()
        output = stream.getvalue()
        assert splash._HIDE_CURSOR in output
        assert splash._SHOW_CURSOR in output
        assert "\u2588" in output  # some pyramid actually got drawn
        assert not handle._thread.is_alive()
        assert handle._height == len(handle._rows)

    def test_stop_is_idempotent(self):
        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0)
        handle.stop()
        before = stream.getvalue()
        handle.stop()
        assert stream.getvalue() == before

    def test_broken_stream_fails_soft(self):
        class BrokenTty(io.StringIO):
            def isatty(self):
                return True

            def write(self, *_a, **_k):
                raise OSError("terminal went for a walk")

        handle = splash.start_splash(stream=BrokenTty(), force=True, min_seconds=0)
        time.sleep(0.05)
        handle.stop()  # must not raise

    def test_stop_honors_minimum_showtime(self):
        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0.3)
        t0 = time.monotonic()
        handle.stop()  # called "instantly" -- must block out the remainder
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.25  # slack for scheduler jitter
        assert not handle._thread.is_alive()
        # the extra showtime produced extra frames, not a frozen screen
        assert stream.getvalue().count("\x1b[2K") > handle._height

    def test_default_minimum_is_three_seconds(self):
        assert splash._MIN_SHOW_SECONDS == 3.0


class TestStreamCapture:
    def test_output_during_splash_is_deferred_then_replayed(self, capsys):
        import sys

        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0)
        try:
            assert sys.stdout is handle._cap_out
            assert sys.stderr is handle._cap_err
            print("import-time chatter")
            sys.stderr.write("plugin warning\n")
            # nothing leaks to the animation stream mid-show
            assert "import-time chatter" not in stream.getvalue()
        finally:
            handle.stop()
        assert sys.stdout is not handle._cap_out  # restored
        captured = capsys.readouterr()
        assert "import-time chatter" in captured.out
        assert "plugin warning" in captured.err

    def test_streams_restored_even_if_swapped_by_someone_else(self, capsys):
        import sys

        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0)
        foreign = FakeTty()
        sys.stdout = foreign  # someone else grabbed stdout mid-import
        try:
            handle.stop()
            assert sys.stdout is foreign  # we must not clobber their swap
        finally:
            sys.stdout = handle._orig_out  # restore for pytest's sanity

    def test_capture_mirrors_isatty(self):
        stream = FakeTty()
        handle = splash.start_splash(stream=stream, force=True, min_seconds=0)
        try:
            assert handle._cap_out.isatty() is handle._orig_out.isatty()
        finally:
            handle.stop()

    def test_null_splash_leaves_streams_alone(self):
        import sys

        out, err = sys.stdout, sys.stderr
        handle = splash.start_splash(stream=io.StringIO())  # not a tty -> null
        handle.stop()
        assert sys.stdout is out and sys.stderr is err
