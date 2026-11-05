"""Tests for ``SafeConsole``: a dead output handle must not abort rendering."""

import errno
import io

import pytest
from rich.console import Console
from rich.control import Control
from rich.segment import ControlType

from code_puppy.messaging.safe_console import SafeConsole
from code_puppy.messaging.safe_stream import SafeTextStream


class _DeadStream(io.StringIO):
    def __init__(self, error: BaseException):
        super().__init__()
        self.error = error
        self.touches = 0

    def write(self, text):
        self.touches += 1
        raise self.error

    def flush(self):
        self.touches += 1
        raise self.error

    def isatty(self):
        return True


def _console(stream, **kwargs) -> SafeConsole:
    return SafeConsole(file=stream, force_terminal=True, width=80, **kwargs)


def test_healthy_console_renders_normally():
    buf = io.StringIO()
    _console(buf).print("hello")
    assert "hello" in buf.getvalue()


@pytest.mark.parametrize("code", [errno.EINVAL, errno.EBADF, errno.EPIPE])
def test_dead_write_is_swallowed_and_console_goes_silent(code):
    stream = _DeadStream(OSError(code, "dead"))
    console = _console(stream)
    console.print("first")
    touched = stream.touches
    console.print("second")
    console.control(
        Control((ControlType.ERASE_IN_LINE, 2), ControlType.CARRIAGE_RETURN)
    )
    assert stream.touches == touched
    assert len(console._buffer) == 0


def test_dead_flush_does_not_raise():
    class _FlushDead(io.StringIO):
        def flush(self):
            raise OSError(errno.EINVAL, "dead")

        def isatty(self):
            return True

    _console(_FlushDead()).print("hello")


def test_file_is_a_cached_safe_stream_and_direct_flush_is_safe():
    stream = _DeadStream(OSError(errno.EINVAL, "dead"))
    console = _console(stream)
    assert isinstance(console.file, SafeTextStream)
    assert console.file is console.file
    console.file.flush()


def test_file_follows_runtime_stdout_replacement(monkeypatch):
    first, second = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdout", first)
    console = SafeConsole(force_terminal=True, width=80)
    console.print("one")
    monkeypatch.setattr("sys.stdout", second)
    console.print("two")
    assert "one" in first.getvalue() and "two" not in first.getvalue()
    assert "two" in second.getvalue()


def test_broken_pipe_goes_silent_without_exiting():
    console = _console(io.StringIO())
    console.on_broken_pipe()
    console.print("still alive")
    assert len(console._buffer) == 0


def test_non_dead_oserror_still_propagates():
    stream = _DeadStream(OSError(errno.ENOSPC, "disk full"))
    with pytest.raises(OSError):
        _console(stream).print("x")


class TestLatchedConsoleKeepsScopedBuffers:
    @staticmethod
    def _latched() -> Console:
        console = _console(io.StringIO(), record=True)
        console.print("before")
        console.on_broken_pipe()
        return console

    def test_recorded_output_survives_a_latch(self):
        assert "before" in self._latched().export_text()

    def test_capture_still_works_after_a_latch(self):
        console = self._latched()
        with console.capture() as capture:
            console.print("captured")
        assert "captured" in capture.get()

    def test_nested_block_keeps_its_buffer_until_the_outermost_exit(self):
        console = self._latched()
        with console:
            console.print("pending")
            assert len(console._buffer) > 0
        assert len(console._buffer) == 0


def test_nested_buffering_stays_balanced():
    stream = _DeadStream(OSError(errno.EINVAL, "dead"))
    console = _console(stream)
    with console:
        with console:
            console.print("nested")
    assert console._buffer_index == 0


def test_is_a_rich_console():
    assert isinstance(_console(io.StringIO()), Console)


class TestRenderPathFailures:
    """Failures raised inside Rich's renderer, bypassing ``file.write`` (legacy Windows)."""

    @staticmethod
    def _failing_render(monkeypatch, error: BaseException) -> list[int]:
        calls: list[int] = []

        def boom(self):
            calls.append(1)
            raise error

        monkeypatch.setattr(Console, "_check_buffer", boom)
        return calls

    @pytest.mark.parametrize("code", [errno.EINVAL, errno.EBADF, errno.EPIPE])
    def test_dead_handle_error_is_swallowed_then_latched(self, monkeypatch, code):
        calls = self._failing_render(monkeypatch, OSError(code, "dead"))
        console = _console(io.StringIO())
        console.print("first")
        assert len(console._buffer) == 0
        console.print("second")
        console.control(
            Control((ControlType.ERASE_IN_LINE, 2), ControlType.CARRIAGE_RETURN)
        )
        assert len(calls) == 1
        assert len(console._buffer) == 0

    def test_non_dead_error_propagates(self, monkeypatch):
        self._failing_render(monkeypatch, OSError(errno.ENOSPC, "disk full"))
        with pytest.raises(OSError):
            _console(io.StringIO()).print("x")

    def test_non_oserror_propagates(self, monkeypatch):
        self._failing_render(monkeypatch, ValueError("bug"))
        with pytest.raises(ValueError):
            _console(io.StringIO()).print("x")
