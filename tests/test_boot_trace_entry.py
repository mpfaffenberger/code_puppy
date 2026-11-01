"""Boot-trace wiring in the CLI entry: root, splash, hooks, runner and parse spans.

The recorder reads ``CODE_PUPPY_BOOT_TRACE`` once at import, so every traced
run goes through a child process via ``_run_py``.
"""

import json
from collections import namedtuple

import pytest

from tests.boot_trace_support import _run_py

PREFIX = "CODE_PUPPY_BOOT_TRACE "
TERMINAL_KINDS = ("end", "error", "skip")

PROBE = """
import runpy
import code_puppy.callbacks as callbacks
{patch}
runpy.run_module("code_puppy.main", run_name="__main__")
"""

DIRECT_PROBE = """
import code_puppy.boot_trace as boot_trace
import code_puppy.callbacks as callbacks

callbacks.on_handle_cli_args = lambda args: [{'handled': True, 'exit_code': 0}]
boot_trace.begin_boot()
boot_trace.begin_boot()
from code_puppy.cli_runner import main_entry

main_entry()
"""

# Blocks only the runner import, after a fake splash is installed, so the test
# can prove the splash stops and the root closes on an import failure.
RUNNER_IMPORT_FAILS_PROBE = """
import importlib.abc
import pathlib
import runpy
import sys

import code_puppy.splash as splash


class _FakeSplash:
    def stop(self):
        pathlib.Path(sys.argv[1]).write_text("stopped")


class _BlockRunner(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "code_puppy.cli_runner":
            raise ImportError("runner blocked for test")
        return None


sys.meta_path.insert(0, _BlockRunner())
splash.start_splash = lambda *a, **k: _FakeSplash()
runpy.run_module("code_puppy.main", run_name="__main__")
"""

HANDLE_RETURNS_ZERO = (
    "callbacks.on_handle_cli_args = lambda args: [{'handled': True, 'exit_code': 0}]"
)
HANDLE_RETURNS_THREE = (
    "callbacks.on_handle_cli_args = lambda args: [{'handled': True, 'exit_code': 3}]"
)
HANDLE_RAISES = "def _boom(args):\n    raise RuntimeError('boom')\n\ncallbacks.on_handle_cli_args = _boom"
REGISTER_RAISES = "def _boom(parser):\n    raise ValueError('boom')\n\ncallbacks.on_register_cli_args = _boom"

Scenario = namedtuple("Scenario", "patch args rc expect")

SCENARIOS = {
    "handled_zero": Scenario(
        patch=HANDLE_RETURNS_ZERO,
        args=(),
        rc=0,
        expect={
            "boot": ("end", {}),
            "cli.handle_args": ("end", {}),
            "splash": ("skip", {"reason": "non_tty"}),
        },
    ),
    "handled_nonzero": Scenario(
        patch=HANDLE_RETURNS_THREE,
        args=(),
        rc=3,
        expect={
            "boot": ("error", {"outcome": "control_exit"}),
            "cli.handle_args": ("end", {}),
        },
    ),
    "handle_raises": Scenario(
        patch=HANDLE_RAISES,
        args=(),
        rc=1,
        expect={
            "cli.parse": ("end", {}),
            "cli.handle_args": ("error", {"exceptionClass": "RuntimeError"}),
            "boot": ("error", {"exceptionClass": "RuntimeError"}),
        },
    ),
    "register_raises": Scenario(
        patch=REGISTER_RAISES,
        args=(),
        rc=1,
        expect={
            "cli.register_args": ("error", {"exceptionClass": "ValueError"}),
            "cli.parse": ("error", {"exceptionClass": "ValueError"}),
            "boot": ("error", {"exceptionClass": "ValueError"}),
        },
    ),
    "argparse_error": Scenario(
        patch="",
        args=("--no-such-flag",),
        rc=2,
        expect={
            "cli.argparse": (
                "error",
                {"outcome": "control_exit", "exceptionClass": "SystemExit"},
            ),
            "boot": ("error", {"outcome": "control_exit"}),
        },
    ),
    "help": Scenario(
        patch="",
        args=("--help",),
        rc=0,
        expect={
            "cli.argparse": ("end", {"outcome": "control_exit"}),
            "boot": ("end", {"outcome": "control_exit"}),
        },
    ),
}


def _target(mode, base):
    if mode == "off":
        return None
    if mode == "stderr":
        return "stderr"
    return str(base / "trace.jsonl")


def _file_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def _terminals(events, phase):
    return [e for e in events if e["phase"] == phase and e["kind"] in TERMINAL_KINDS]


def _assert_terminal(events, phase, kind, fields):
    terminals = _terminals(events, phase)
    assert len(terminals) == 1, (phase, terminals)
    event = terminals[0]
    observed = {**event.get("attrs", {}), "reason": event.get("reason")}
    assert event["kind"] == kind, (phase, event)
    assert {k: observed.get(k) for k in fields} == fields, (phase, event)


def _seq(events, phase, kind):
    matches = [e["seq"] for e in events if e["phase"] == phase and e["kind"] == kind]
    assert len(matches) == 1, (phase, kind, matches)
    return matches[0]


@pytest.fixture(scope="module")
def run_entry(tmp_path_factory):
    cache = {}

    def run(name, *, mode):
        key = (name, mode)
        if key not in cache:
            scenario = SCENARIOS[name]
            base = tmp_path_factory.mktemp(f"{name}-{mode}")
            result = _run_py(
                PROBE.format(patch=scenario.patch),
                _target(mode, base),
                base,
                *scenario.args,
            )
            cache[key] = (result, base)
        return cache[key]

    return run


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_exit_status_and_stdout_are_unchanged_by_tracing(run_entry, name):
    off, _ = run_entry(name, mode="off")
    on, _ = run_entry(name, mode="file")

    assert off.returncode == on.returncode == SCENARIOS[name].rc, on.stderr
    assert off.stdout == on.stdout


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_terminal_events_match_each_exit_path(run_entry, name):
    _, base = run_entry(name, mode="file")
    events = _file_events(base / "trace.jsonl")

    for phase, (kind, fields) in SCENARIOS[name].expect.items():
        _assert_terminal(events, phase, kind, fields)


def test_root_opens_before_splash_and_hooks_and_closes_after_handle(run_entry):
    _, base = run_entry("handled_zero", mode="file")
    events = _file_events(base / "trace.jsonl")

    ordered = [
        _seq(events, "boot", "start"),
        _seq(events, "splash", "start"),
        _seq(events, "splash", "skip"),
        _seq(events, "error_hooks", "start"),
        _seq(events, "runner.import", "start"),
        _seq(events, "cli.handle_args", "start"),
        _seq(events, "cli.handle_args", "end"),
        _seq(events, "boot", "end"),
    ]
    assert ordered == sorted(ordered)


def test_stderr_sink_keeps_stdout_clean(run_entry):
    result, _ = run_entry("handled_zero", mode="stderr")

    assert "CODE_PUPPY_BOOT_TRACE" not in result.stdout
    records = [
        json.loads(line[len(PREFIX) :])
        for line in result.stderr.splitlines()
        if line.startswith(PREFIX)
    ]
    assert {r["v"] for r in records} == {1}
    assert "boot" in {r["phase"] for r in records}


def test_runner_import_failure_stops_splash_and_closes_root(tmp_path):
    trace = tmp_path / "trace.jsonl"
    stop_marker = tmp_path / "splash-stopped"

    result = _run_py(RUNNER_IMPORT_FAILS_PROBE, str(trace), tmp_path, str(stop_marker))

    assert result.returncode == 1
    assert stop_marker.read_text() == "stopped"
    events = _file_events(trace)
    _assert_terminal(
        events, "runner.import", "error", {"exceptionClass": "ImportError"}
    )
    _assert_terminal(events, "boot", "error", {"exceptionClass": "ImportError"})
    _assert_terminal(events, "splash", "end", {})


def test_direct_entry_opens_exactly_one_root(tmp_path):
    trace = tmp_path / "trace.jsonl"

    result = _run_py(DIRECT_PROBE, str(trace), tmp_path)

    assert result.returncode == 0, result.stderr
    events = _file_events(trace)
    starts = [e for e in events if e["phase"] == "boot" and e["kind"] == "start"]
    assert len(starts) == 1
    _assert_terminal(events, "boot", "end", {})
