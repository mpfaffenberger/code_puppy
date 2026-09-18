"""Tests for the ``error_logged`` observation phase.

The phase is an extension point with no in-tree subscriber, so nothing else
in the suite exercises it. These tests pin the two properties a downstream
subscriber depends on: that logging still works when a subscriber misbehaves,
and that observing an error cannot itself become an error cascade.
"""

from __future__ import annotations

import logging
import os
import threading

import pytest

from code_puppy import callbacks, error_logging


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Point the error log at a temp file and clear the phase's subscribers."""
    log_file = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(log_file))

    original = list(callbacks._callbacks.get("error_logged", []))
    callbacks._callbacks["error_logged"] = []
    yield log_file
    callbacks._callbacks["error_logged"] = original


def _written(log_file) -> str:
    return log_file.read_text() if os.path.exists(log_file) else ""


def test_subscriber_receives_the_logged_error(isolated_log) -> None:
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))

    error = ValueError("boom")
    error_logging.log_error(error)

    assert seen == [error]


def test_stock_install_has_no_subscriber() -> None:
    """The zero-telemetry guarantee: core registers nothing for this phase."""
    assert callbacks._callbacks.get("error_logged", []) == []


def test_local_log_survives_a_broken_subscriber(isolated_log, caplog) -> None:
    """The file sink and the observer must fail independently."""

    def broken(error, **kwargs):
        raise RuntimeError("subscriber exploded")

    callbacks.register_callback("error_logged", broken)

    with caplog.at_level(logging.ERROR):
        error_logging.log_error(ValueError("original"))

    assert "original" in _written(isolated_log)


def test_reentrant_subscriber_does_not_recurse(isolated_log) -> None:
    """A subscriber that logs its own error is observed once, not 199 times.

    Without the per-thread latch this recursed until CPython's limit tripped,
    appending a full traceback to the local log on every level.
    """
    depth = {"current": 0, "max": 0}

    def reentrant(error, **kwargs):
        depth["current"] += 1
        depth["max"] = max(depth["max"], depth["current"])
        try:
            error_logging.log_error(RuntimeError("subscriber's own failure"))
        finally:
            depth["current"] -= 1

    callbacks.register_callback("error_logged", reentrant)

    error_logging.log_error(ValueError("original"))

    assert depth["max"] == 1


def test_latch_releases_between_independent_errors(isolated_log) -> None:
    """Suppression is scoped to one dispatch, not latched permanently."""
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(str(e)))

    error_logging.log_error(ValueError("first"))
    error_logging.log_error(ValueError("second"))

    assert seen == ["first", "second"]


def test_latch_is_per_thread(isolated_log) -> None:
    """One thread's dispatch must not blind the hook on another."""
    seen: dict[str, list[str]] = {}

    def observer(error, **kwargs):
        name = threading.current_thread().name
        if name == "A":
            worker = threading.Thread(
                target=lambda: error_logging.log_error(ValueError("from B")),
                name="B",
            )
            worker.start()
            worker.join()
        seen.setdefault(name, []).append(str(error))

    callbacks.register_callback("error_logged", observer)

    thread = threading.Thread(
        target=lambda: error_logging.log_error(ValueError("from A")),
        name="A",
    )
    thread.start()
    thread.join()

    assert seen == {"A": ["from A"], "B": ["from B"]}


def test_log_error_message_does_not_fire_the_phase(isolated_log) -> None:
    """The other half of the recursion guard.

    A subscriber reporting its own failure uses log_error_message precisely
    because it must not re-enter this phase.
    """
    seen = []
    callbacks.register_callback("error_logged", lambda e, **kw: seen.append(e))

    error_logging.log_error_message("forensic note", "context")

    assert seen == []
