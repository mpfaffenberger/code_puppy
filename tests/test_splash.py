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


class TestFrame:
    def test_frame_dimensions(self):
        frame = splash._build_frame(0, truecolor=True)
        lines = frame.splitlines()
        assert len(lines) == splash._HEIGHT
        for line in lines:
            visible = ANSI_RE.sub("", line)
            assert len(visible) <= 44
            assert set(visible) <= set(" \u2591\u2592\u2588")

    def test_sheen_moves_between_phases(self):
        assert splash._build_frame(0, truecolor=True) != splash._build_frame(
            20, truecolor=True
        )

    def test_fallback_palette_has_no_truecolor_codes(self):
        frame = splash._build_frame(0, truecolor=False)
        assert "38;2;" not in frame


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
        assert stream.getvalue().count("\x1b[2K") > splash._HEIGHT

    def test_default_minimum_is_two_seconds(self):
        assert splash._MIN_SHOW_SECONDS == 2.0


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
