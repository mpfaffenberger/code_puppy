"""errors.log sink: one entry per exception object, the stamp and its fallback, write failures."""

from __future__ import annotations

import inspect
from collections import OrderedDict

import pytest

from code_puppy import callbacks, error_logging


class _RefusesSetattr(Exception):
    def __setattr__(self, name, value):
        raise AttributeError("read-only")


class _CustomError(Exception):
    pass


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Redirect the log, clear subscribers and the fallback table."""
    log_file = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))
    monkeypatch.setattr(error_logging, "_fallback", OrderedDict())

    original = list(callbacks._callbacks.get("error_logged", []))
    callbacks._callbacks["error_logged"] = []
    yield log_file
    callbacks._callbacks["error_logged"] = original


def _entries(log_file) -> int:
    return log_file.read_text().count("Error Type:") if log_file.exists() else 0


def test_second_log_error_on_one_object_writes_nothing_and_fires_no_phase(
    isolated_log,
):
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))
    error = ValueError("boom")

    error_logging.log_error(error)
    error_logging.log_error(error)

    assert _entries(isolated_log) == 1
    assert seen == [error]


def test_first_context_wins(isolated_log):
    error = ValueError("boom")

    error_logging.log_error(error, context="inner")
    error_logging.log_error(error, context="outer")

    text = isolated_log.read_text()
    assert "Context: inner" in text
    assert "outer" not in text


def test_was_logged_flips_after_first_log(isolated_log):
    error = ValueError("boom")
    assert error_logging.was_logged(error) is False

    error_logging.log_error(error)

    assert error_logging.was_logged(error) is True


@pytest.mark.parametrize("exc_type", [ValueError, KeyError, _CustomError])
def test_builtin_and_subclassed_exceptions_get_the_stamp(isolated_log, exc_type):
    error = exc_type("x")

    error_logging.log_error(error)

    assert error.__code_puppy_logged__ is True


def test_exception_refusing_setattr_uses_the_bounded_fallback(isolated_log):
    first = _RefusesSetattr("first")
    error_logging.log_error(first)
    error_logging.log_error(first)

    assert _entries(isolated_log) == 1
    assert error_logging.was_logged(first) is True
    assert error_logging._fallback[id(first)] is first  # strong reference

    for number in range(error_logging._FALLBACK_MAX * 2):
        error_logging.log_error(_RefusesSetattr(str(number)))

    assert len(error_logging._fallback) == error_logging._FALLBACK_MAX
    assert error_logging.was_logged(first) is False  # evicted, oldest first


def test_distinct_exceptions_each_log(isolated_log):
    error_logging.log_error(ValueError("a"), context="first")
    error_logging.log_error(ValueError("a"), context="second")

    assert _entries(isolated_log) == 2


def test_stamp_is_set_when_the_write_fails(isolated_log, monkeypatch):
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))

    def refuse() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(error_logging, "_ensure_logs_dir", refuse)
    error = ValueError("boom")

    error_logging.log_error(error)
    error_logging.log_error(error)

    assert error_logging.was_logged(error) is True
    assert seen == [error]  # phase fired once, the failing sink was not retried


def test_log_error_message_returns_true_then_false(isolated_log, monkeypatch):
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))

    assert error_logging.log_error_message("hello", context="ctx") is True
    assert "Message: hello" in isolated_log.read_text()

    def refuse() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(error_logging, "_ensure_logs_dir", refuse)
    assert error_logging.log_error_message("again") is False
    assert seen == []


def test_log_error_accepts_exception_groups(isolated_log):
    group = BaseExceptionGroup("g", [KeyboardInterrupt(), ValueError("x")])

    error_logging.log_error(group)

    assert _entries(isolated_log) == 1
    assert "Error Type: BaseExceptionGroup" in isolated_log.read_text()


def test_on_error_logged_signature_is_unchanged():
    params = list(inspect.signature(callbacks.on_error_logged).parameters.values())

    assert [p.name for p in params] == ["error", "context", "include_traceback"]
    assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert [p.kind for p in params[1:]] == [inspect.Parameter.KEYWORD_ONLY] * 2
    assert params[1].default is None
    assert params[2].default is True
