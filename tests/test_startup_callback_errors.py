"""Startup-phase callback failures reach errors.log; per-event phases stay out of it."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from typing import Any, get_args

import pytest

from code_puppy import callbacks, error_hooks, error_logging

SYNC_CONTEXT = (
    "code_puppy.callbacks::_trigger_callbacks_sync: startup/cli-args: "
    "run a startup-phase callback registered by a plugin"
)
ASYNC_CONTEXT = (
    "code_puppy.callbacks::_trigger_callbacks: startup/plugin-startup: "
    "run a startup-phase async callback registered by a plugin"
)
TOUCHED_PHASES = (
    "register_cli_args",
    "handle_cli_args",
    "version_check",
    "startup",
    "stream_event",
    "shutdown",
    "register_tools",
    "pre_tool_call",
    "error_logged",
)


def broken_plugin_callback(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("plugin bug")


async def broken_async_plugin_callback(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("async plugin bug")


BROKEN_STYLES = pytest.mark.parametrize(
    "broken",
    [broken_plugin_callback, broken_async_plugin_callback],
    ids=["sync-def", "async-def"],
)


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    """Redirect errors.log and give the test an empty registry for the touched phases."""
    path = tmp_path / "errors.log"
    monkeypatch.setattr(error_logging, "LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(error_logging, "ERROR_LOG_FILE", str(path))
    monkeypatch.setattr(error_logging, "_fallback", OrderedDict())
    monkeypatch.setattr(callbacks, "_fail_closed_callbacks", set())
    for phase in TOUCHED_PHASES:
        monkeypatch.setitem(callbacks._callbacks, phase, [])
    return path


def _contexts(path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.removeprefix("Context: ")
        for line in path.read_text().splitlines()
        if line.startswith("Context: ")
    ]


def _entry_count(path) -> int:
    return path.read_text().count("Error Type:") if path.exists() else 0


def _healthy(tag: str, ran: list[str]):
    def callback(*_args: Any, **_kwargs: Any) -> str:
        ran.append(tag)
        return f"{tag}-result"

    return callback


def _register_around(phase: str, broken, ran: list[str]) -> None:
    callbacks.register_callback(phase, _healthy("before", ran))
    callbacks.register_callback(phase, broken)
    callbacks.register_callback(phase, _healthy("after", ran))


def test_startup_phases_are_exactly_the_planned_set_and_real_phase_names():
    assert callbacks._STARTUP_PHASES == {
        "register_cli_args",
        "handle_cli_args",
        "version_check",
        "startup",
    }
    assert callbacks._STARTUP_PHASES <= set(get_args(callbacks.PhaseType))


@BROKEN_STYLES
def test_sync_dispatcher_records_a_failing_startup_callback_once(log_file, broken):
    ran: list[str] = []
    _register_around("handle_cli_args", broken, ran)

    results = callbacks.on_handle_cli_args(argparse.Namespace())

    assert results == ["before-result", None, "after-result"]
    assert ran == ["before", "after"]
    assert _contexts(log_file) == [
        f"{SYNC_CONTEXT} (handle_cli_args, {broken.__name__})"
    ]
    assert _entry_count(log_file) == 1


@BROKEN_STYLES
@pytest.mark.parametrize(
    ("phase", "invoke"),
    [
        ("startup", lambda: callbacks.on_startup()),
        ("version_check", lambda: callbacks.on_version_check("1.0.0")),
    ],
    ids=["startup", "version_check"],
)
async def test_async_dispatcher_records_a_failing_startup_callback_once(
    log_file, broken, phase, invoke
):
    ran: list[str] = []
    _register_around(phase, broken, ran)

    results = await invoke()

    assert results == ["before-result", None, "after-result"]
    assert ran == ["before", "after"]
    assert _contexts(log_file) == [f"{ASYNC_CONTEXT} ({phase}, {broken.__name__})"]
    assert _entry_count(log_file) == 1


@pytest.mark.parametrize(
    ("phase", "is_async"),
    [("stream_event", True), ("shutdown", True), ("register_tools", False)],
)
async def test_non_startup_phases_write_nothing_and_still_isolate(
    log_file, phase, is_async
):
    ran: list[str] = []
    _register_around(phase, broken_plugin_callback, ran)

    for _ in range(3):  # a per-event phase would otherwise write once per event
        if is_async:
            results = await callbacks._trigger_callbacks(phase, "event", {})
        else:
            results = callbacks._trigger_callbacks_sync(phase, "event", {})
        assert results == ["before-result", None, "after-result"]

    assert ran == ["before", "after"] * 3
    assert not log_file.exists()


def test_raise_on_error_logs_then_propagates_and_hook_does_not_repeat(log_file):
    ran: list[str] = []
    _register_around("register_cli_args", broken_plugin_callback, ran)

    with pytest.raises(RuntimeError, match="plugin bug") as raised:
        callbacks.on_register_cli_args(argparse.ArgumentParser())

    exc = raised.value
    assert ran == ["before"]  # fail-fast: later callbacks never run
    assert _contexts(log_file) == [
        f"{SYNC_CONTEXT} (register_cli_args, broken_plugin_callback)"
    ]
    assert error_logging.was_logged(exc)

    # What sys.excepthook would do when this exception reaches the top level.
    assert error_hooks.report_exception(exc, context="hook") is False
    assert _entry_count(log_file) == 1


async def test_fail_closed_result_is_unchanged_and_not_written(log_file):
    callbacks.register_callback(
        "pre_tool_call", broken_plugin_callback, fail_closed=True
    )

    results = await callbacks.on_pre_tool_call("some_tool", {})

    assert results == [
        callbacks._failure_result(
            broken_plugin_callback, "pre_tool_call", RuntimeError("plugin bug")
        )
    ]
    assert results[0]["blocked"] is True
    assert not log_file.exists()


class _HostileCallback:
    """Named, failing, and with a ``__repr__`` that must never be called."""

    __name__ = "broken"

    def __call__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("plugin bug")

    def __repr__(self) -> str:
        raise AssertionError("repr was evaluated while reporting a failure")


async def test_sync_and_async_dispatch_isolate_a_callback_with_a_throwing_repr(
    log_file,
):
    ran: list[str] = []
    _register_around("handle_cli_args", _HostileCallback(), ran)
    _register_around("startup", _HostileCallback(), ran)

    sync_results = callbacks.on_handle_cli_args(argparse.Namespace())
    async_results = await callbacks.on_startup()

    expected = ["before-result", None, "after-result"]
    assert sync_results == async_results == expected
    assert _contexts(log_file) == [
        f"{SYNC_CONTEXT} (handle_cli_args, broken)",
        f"{ASYNC_CONTEXT} (startup, broken)",
    ]


def test_fail_fast_dispatch_still_raises_the_original_exception(log_file):
    _register_around("register_cli_args", _HostileCallback(), [])

    with pytest.raises(RuntimeError, match="plugin bug"):
        callbacks.on_register_cli_args(argparse.ArgumentParser())

    assert _contexts(log_file) == [f"{SYNC_CONTEXT} (register_cli_args, broken)"]
