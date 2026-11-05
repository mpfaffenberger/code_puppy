"""Uncaught-exception hooks: report once, always delegate, never print."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
import threading
from collections import OrderedDict
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from code_puppy import callbacks, error_hooks, error_logging
from code_puppy.error_policy import ExpectedFlow

Outcome = tuple[list[Any], list[Any], str]  # (delegated calls, expected calls, context)

MAIN_CONTEXT = "code_puppy.error_hooks::_install_excepthook.hook: uncaught exception reached sys.excepthook"


def _boom() -> Exception:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


def _main(exc: BaseException) -> Outcome:
    calls: list[Any] = []
    sys.excepthook = lambda *args: calls.append(args)
    error_hooks.install_error_hooks()
    error_hooks.install_error_hooks()
    sys.excepthook(type(exc), exc, exc.__traceback__)
    return calls, [(type(exc), exc, exc.__traceback__)], MAIN_CONTEXT


def _thread(exc: BaseException) -> Outcome:
    calls: list[Any] = []
    threading.excepthook = lambda args: calls.append(args)
    error_hooks.install_error_hooks()
    error_hooks.install_error_hooks()
    args = threading.ExceptHookArgs(
        (type(exc), exc, exc.__traceback__, SimpleNamespace(name="worker-7"))
    )
    threading.excepthook(args)
    context = (
        "code_puppy.error_hooks::_thread_report: uncaught exception ended a worker thread"
        " (worker-7)"
    )
    return calls, [args], context


SCENARIOS: dict[str, Callable[[BaseException], Outcome]] = {
    "main": _main,
    "thread": _thread,
}
SOURCES = pytest.mark.parametrize("source", list(SCENARIOS))


@pytest.fixture(autouse=True)
def _restore_global_hooks():
    # An earlier test may have run main_entry(), which installs the hooks for good.
    error_hooks.uninstall_error_hooks()
    saved = (sys.excepthook, threading.excepthook)
    yield
    error_hooks.uninstall_error_hooks()
    sys.excepthook, threading.excepthook = saved


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


@pytest.fixture
def logged(monkeypatch) -> list[tuple[BaseException, dict[str, Any]]]:
    records: list[tuple[BaseException, dict[str, Any]]] = []
    monkeypatch.setattr(
        error_hooks, "log_error", lambda exc, **kwargs: records.append((exc, kwargs))
    )
    return records


def _raises(*_args, **_kwargs):
    raise RuntimeError("sink down")


@SOURCES
def test_reports_once_with_exact_context_and_delegates_once(source, logged):
    exc = _boom()
    calls, expected, context = SCENARIOS[source](exc)

    assert calls == expected  # installed twice, chained once, original args
    assert logged == [(exc, {"context": context})]


@SOURCES
@pytest.mark.parametrize("never_report", [KeyboardInterrupt(), SystemExit(1)])
def test_never_report_types_are_delegated_but_not_logged(source, never_report, logged):
    calls, expected, _ = SCENARIOS[source](never_report)

    assert calls == expected
    assert logged == []


@SOURCES
def test_log_error_failure_does_not_escape_and_still_delegates(source, monkeypatch):
    monkeypatch.setattr(error_hooks, "log_error", _raises)

    calls, expected, _ = SCENARIOS[source](_boom())

    assert calls == expected


def test_real_thread_failure_reports_and_reaches_previous_hook(logged):
    seen: list[threading.ExceptHookArgs] = []
    threading.excepthook = seen.append
    error_hooks.install_error_hooks()

    def work() -> None:
        raise KeyError("in-thread")

    thread = threading.Thread(target=work, name="worker-real")
    thread.start()
    thread.join()

    assert len(seen) == 1
    assert seen[0].exc_type is KeyError and seen[0].thread is thread
    assert [kw["context"] for _, kw in logged] == [
        "code_puppy.error_hooks::_thread_report: uncaught exception ended a worker thread"
        " (worker-real)"
    ]


class _Hostile:
    """Thread-hook args whose every attribute read raises."""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"no {name}")


@pytest.mark.parametrize(
    "make_args",
    [
        lambda: None,
        _Hostile,
        lambda: SimpleNamespace(exc_value=None, thread=None),
        lambda: SimpleNamespace(exc_value=_boom(), thread=_Hostile()),
    ],
    ids=["none", "raising-attributes", "no-exception", "raising-thread"],
)
def test_hostile_hook_arguments_never_raise_and_still_delegate(make_args, logged):
    seen: list[Any] = []
    threading.excepthook = seen.append
    error_hooks.install_error_hooks()
    args = make_args()

    threading.excepthook(args)

    assert seen == [args]


def test_double_install_is_a_no_op():
    originals = (sys.excepthook, threading.excepthook)

    error_hooks.install_error_hooks()
    error_hooks.install_error_hooks()

    for hook, original in zip((sys.excepthook, threading.excepthook), originals):
        assert getattr(hook, error_hooks._PREVIOUS) is original  # one wrapper layer


def test_uninstall_restores_original_hooks():
    originals = (sys.excepthook, threading.excepthook)
    error_hooks.install_error_hooks()
    assert all(
        getattr(hook, error_hooks._MARKER, False)
        for hook in (sys.excepthook, threading.excepthook)
    )

    error_hooks.uninstall_error_hooks()

    assert (sys.excepthook, threading.excepthook) == originals


def test_uninstall_leaves_a_hook_chained_on_top_untouched():
    error_hooks.install_error_hooks()

    def theirs(*args):
        pass

    sys.excepthook = theirs
    error_hooks.uninstall_error_hooks()

    assert sys.excepthook is theirs


def test_import_has_no_side_effects():
    probe = (
        "import sys, threading;"
        "h=(sys.excepthook, threading.excepthook);"
        "import code_puppy.error_hooks;"
        "assert h == (sys.excepthook, threading.excepthook);"
        "loaded = [m for m in ('pydantic_ai', 'code_puppy.callbacks') if m in sys.modules];"
        "assert not loaded, loaded"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, timeout=60)


@pytest.mark.parametrize(
    ("make_exc", "already_logged", "sink", "expected_result", "expected_entries"),
    [
        (KeyboardInterrupt, False, None, False, 0),
        (lambda: SystemExit(1), False, None, False, 0),
        (lambda: ExpectedFlow("anticipated"), False, None, False, 0),
        (_boom, True, None, False, 1),
        (_boom, False, None, True, 1),
        (_boom, False, _raises, False, 0),
    ],
    ids=[
        "keyboard-interrupt",
        "system-exit",
        "expected-flow",
        "already-logged",
        "true-error",
        "sink-raises",
    ],
)
def test_report_exception_contract(
    isolated_log,
    monkeypatch,
    make_exc,
    already_logged,
    sink,
    expected_result,
    expected_entries,
):
    exc = make_exc()
    if already_logged:
        error_logging.log_error(exc, context="first")
    if sink:
        monkeypatch.setattr(error_hooks, "log_error", sink)

    assert error_hooks.report_exception(exc, context="ctx") is expected_result
    assert _entries(isolated_log) == expected_entries


UNCAUGHT_SCRIPT = textwrap.dedent(
    """
    import sys, threading

    if sys.argv[1] == "hooks":
        from code_puppy.error_hooks import install_error_hooks
        install_error_hooks()

    def work():
        raise ValueError("from thread")

    thread = threading.Thread(target=work, name="worker")
    thread.start()
    thread.join()

    raise ValueError("from main")
    """
)


def _run_uncaught(mode: str, state_home) -> subprocess.CompletedProcess:
    env = {**os.environ, "XDG_STATE_HOME": str(state_home)}
    return subprocess.run(
        [sys.executable, "-c", UNCAUGHT_SCRIPT, mode],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_uncaught_exceptions_each_write_one_entry(tmp_path):
    hooked = _run_uncaught("hooks", tmp_path / "hooked")
    plain = _run_uncaught("plain", tmp_path / "plain")

    log = tmp_path / "hooked" / "code_puppy" / "logs" / "errors.log"
    assert log.read_text().count("Error Type: ValueError") == 2  # thread + main
    assert not (tmp_path / "plain").exists()
    assert hooked.returncode == plain.returncode == 1

    def normalise(text: str) -> str:
        return re.sub(r"0x[0-9a-f]+", "0x?", text)

    assert normalise(hooked.stderr) == normalise(plain.stderr)


RUNNER_PROBE = textwrap.dedent(
    """
    import importlib.abc, json, sys

    class Probe(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name == "code_puppy.cli_runner":
                marked = bool(getattr(sys.excepthook, {marker!r}, False))
                print(json.dumps({{"marked_before_runner": marked}}))
                raise SystemExit(0)  # skip the multi-second runner import

    sys.meta_path.insert(0, Probe())
    import code_puppy.main
    print(json.dumps({{"marked_before_runner": None}}))
    """
)


def test_main_installs_hooks_before_importing_the_runner(tmp_path):
    env = {
        **os.environ,
        "CODE_PUPPY_NO_SPLASH": "1",
        "XDG_STATE_HOME": str(tmp_path),
    }
    script = RUNNER_PROBE.format(marker=error_hooks._MARKER)

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"marked_before_runner": True}
