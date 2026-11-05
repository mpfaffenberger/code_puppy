"""Tests for the dead-handle-tolerant output proxies."""

import errno
import io

import pytest

from code_puppy.messaging.safe_stream import (
    SafeTextStream,
    ensure_safe_text_stream,
    is_dead_handle_error,
)


def _os_error(code: int, winerror: int | None = None) -> OSError:
    exc = OSError(code, "boom")
    if winerror is not None:
        exc.winerror = winerror  # type: ignore[attr-defined]
    return exc


class _FailingStream(io.StringIO):
    def __init__(self, error: BaseException, *, fail_write=True, fail_flush=True):
        super().__init__()
        self.error = error
        self.fail_write = fail_write
        self.fail_flush = fail_flush
        self.write_calls = 0
        self.flush_calls = 0

    def write(self, text):
        self.write_calls += 1
        if self.fail_write:
            raise self.error
        return super().write(text)

    def flush(self):
        self.flush_calls += 1
        if self.fail_flush:
            raise self.error

    def isatty(self):
        return True


class TestIsDeadHandleError:
    @pytest.mark.parametrize("code", [errno.EINVAL, errno.EPIPE, errno.EBADF])
    def test_allowlisted_errnos(self, code):
        assert is_dead_handle_error(_os_error(code))

    @pytest.mark.parametrize("winerror", [6, 109, 232])
    def test_allowlisted_winerrors(self, winerror):
        assert is_dead_handle_error(_os_error(errno.EIO, winerror))

    def test_broken_pipe_subclass(self):
        assert is_dead_handle_error(BrokenPipeError())

    @pytest.mark.parametrize("code", [errno.ENOSPC, errno.EACCES, errno.EIO])
    def test_other_oserrors_are_not_dead_handles(self, code):
        assert not is_dead_handle_error(_os_error(code))

    def test_non_oserror(self):
        assert not is_dead_handle_error(ValueError("nope"))


class TestSafeTextStream:
    def test_passes_through_when_healthy(self):
        buf = io.StringIO()
        stream = SafeTextStream(buf)
        assert stream.write("hi") == 2
        stream.flush()
        assert buf.getvalue() == "hi"

    def test_write_failure_is_swallowed_and_latches(self):
        target = _FailingStream(_os_error(errno.EINVAL))
        stream = SafeTextStream(target)
        assert stream.write("abc") == 3
        assert stream.write("def") == 3
        assert target.write_calls == 1

    def test_flush_failure_is_swallowed_and_latches(self):
        target = _FailingStream(_os_error(errno.EBADF), fail_write=False)
        stream = SafeTextStream(target)
        stream.flush()
        stream.flush()
        stream.write("x")
        assert target.flush_calls == 1
        assert target.write_calls == 0

    def test_unrelated_oserror_propagates(self):
        stream = SafeTextStream(_FailingStream(_os_error(errno.ENOSPC)))
        with pytest.raises(OSError):
            stream.write("x")

    def test_non_oserror_propagates(self):
        stream = SafeTextStream(_FailingStream(ValueError("bad")))
        with pytest.raises(ValueError):
            stream.write("x")

    def test_writelines_accepts_an_iterator(self):
        buf = io.StringIO()
        SafeTextStream(buf).writelines(iter(["a", "b"]))
        assert buf.getvalue() == "ab"

    def test_delegates_everything_else(self):
        buf = io.StringIO()
        stream = SafeTextStream(buf)
        assert stream.isatty() is False
        assert stream.getvalue() == ""


def test_ensure_safe_text_stream_is_idempotent():
    safe = ensure_safe_text_stream(io.StringIO())
    assert isinstance(safe, SafeTextStream)
    assert ensure_safe_text_stream(safe) is safe


def test_copy_does_not_recurse_through_the_delegating_getattr():
    import copy

    clone = copy.copy(SafeTextStream(io.StringIO()))
    assert clone.write("x") == 1
