"""Tests for the command catalog consumed by /help and completion tooling."""

import json
import os
import subprocess
import sys

import pytest

from code_puppy import callbacks
from code_puppy.command_line import command_catalog
from code_puppy.command_line.command_catalog import (
    CommandEntry,
    _hint_from_usage,
    list_commands,
    list_plugin_commands,
    list_registry_commands,
)
from code_puppy.command_line.command_registry import get_command, get_unique_commands


def _plugin_entry(name: str, description: str) -> CommandEntry:
    return CommandEntry(
        name=name,
        description=description,
        usage=f"/{name}",
        hint="",
        aliases=(),
        category="plugin",
        interactive=False,
    )


@pytest.mark.parametrize(
    ("usage", "expected_hint"),
    [
        ("/cd <dir>", "<dir>"),
        ("/session [id|new]", "[id|new]"),
        ("/help, /h", ""),
        ("/model, /m <model>", "<model>"),
        ("/agent <name>, /a <name>", "<name>"),
        ("/paste, /clipboard, /cb", ""),
        ("/set [key [value]]", "[key [value]]"),
        ("/uc", ""),
    ],
)
def test_hint_from_usage(usage, expected_hint):
    assert _hint_from_usage(usage) == expected_hint


def test_registry_entries_have_well_formed_fields():
    entries = list_commands()

    assert len(entries) > 30
    for entry in entries:
        assert isinstance(entry.name, str) and entry.name
        assert "/" not in entry.name
        assert isinstance(entry.aliases, tuple)
        assert all(isinstance(alias, str) for alias in entry.aliases)
        assert entry.category
        assert isinstance(entry.interactive, bool)


def test_registry_names_unique_and_hidden_aliases_excluded():
    registry_names = [entry.name for entry in list_registry_commands()]
    all_aliases = {alias for entry in list_commands() for alias in entry.aliases}

    hidden = {alias for info in get_unique_commands() for alias in info.hidden_aliases}

    assert len(registry_names) == len(set(registry_names))
    assert "qr" in hidden
    assert not hidden & all_aliases


def test_entries_carry_registry_interactive_flag():
    for entry in list_registry_commands():
        assert entry.interactive == get_command(entry.name).interactive


@pytest.mark.parametrize(
    ("callback_result", "expected"),
    [
        pytest.param(("tup", "Tuple desc"), [("tup", "Tuple desc")], id="bare-tuple"),
        pytest.param(
            [("lst_one", "One"), ("lst_two", "Two")],
            [("lst_one", "One"), ("lst_two", "Two")],
            id="list-of-tuples",
        ),
        pytest.param(
            ["/legacy - Legacy desc"],
            [("legacy", "Legacy desc")],
            id="legacy-string-list",
        ),
        pytest.param(
            ("/slashy", "d"),
            [("slashy", "d")],
            id="leading-slash-stripped",
        ),
        pytest.param([None, 42], [], id="none-and-junk"),
    ],
)
def test_plugin_callback_shapes_become_plugin_entries(
    monkeypatch, callback_result, expected
):
    monkeypatch.setattr(callbacks, "on_custom_command_help", lambda: [callback_result])
    registry_count = len(list_registry_commands())

    plugin_tail = list_commands()[registry_count:]

    assert plugin_tail == [_plugin_entry(name, desc) for name, desc in expected]


def test_list_commands_dedupes_names_first_entry_wins(monkeypatch):
    registry_name = list_registry_commands()[0].name
    monkeypatch.setattr(
        callbacks,
        "on_custom_command_help",
        lambda: [
            [("dup", "first"), (registry_name, "shadows registry")],
            [("dup", "second")],
        ],
    )

    entries = list_commands()

    names = [entry.name for entry in entries]
    assert len(names) == len(set(names))
    assert [e.description for e in entries if e.name == "dup"] == ["first"]
    assert next(e for e in entries if e.name == registry_name).category != "plugin"


@pytest.fixture
def logged(monkeypatch):
    """Capture log_error calls so tests never write the real errors.log."""
    calls = []
    monkeypatch.setattr(
        command_catalog,
        "log_error",
        lambda exc, context=None: calls.append((exc, context)),
    )
    return calls


def _raising(exc):
    def _raise():
        raise exc

    return _raise


def test_failing_callback_yields_no_plugin_entries_and_logs_once(monkeypatch, logged):
    error = RuntimeError("plugin is broken")
    monkeypatch.setattr(callbacks, "on_custom_command_help", _raising(error))

    assert list_plugin_commands() == []
    assert logged == [
        (error, "command_catalog::list_plugin_commands: callbacks failed")
    ]


def test_failing_logger_does_not_change_plugin_commands(monkeypatch):
    def bad_logger(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(command_catalog, "log_error", bad_logger)
    monkeypatch.setattr(
        callbacks, "on_custom_command_help", _raising(RuntimeError("boom"))
    )

    assert list_plugin_commands() == []


def test_control_flow_exception_propagates_unlogged(monkeypatch, logged):
    monkeypatch.setattr(
        callbacks, "on_custom_command_help", _raising(KeyboardInterrupt())
    )

    with pytest.raises(KeyboardInterrupt):
        list_plugin_commands()
    assert logged == []


@pytest.mark.parametrize("callback_result", [[], [None, 42]])
def test_empty_or_junk_callbacks_are_not_errors(monkeypatch, logged, callback_result):
    monkeypatch.setattr(callbacks, "on_custom_command_help", lambda: callback_result)

    assert list_plugin_commands() == []
    assert logged == []


# Plugin discovery is stubbed in the subprocess: it costs ~57s cold and is the
# flaky part. The built-in set must come from the lazy command_handler import.
_FRESH_INTERPRETER_SNIPPET = """
import json
import sys
import code_puppy.plugins as p
p.load_plugin_callbacks = lambda *a, **k: None
from code_puppy.command_line.command_catalog import list_registry_commands
assert "code_puppy.command_line.command_handler" not in sys.modules
print(json.dumps(sorted(e.name for e in list_registry_commands())))
"""


def test_registry_catalog_is_complete_in_fresh_interpreter(monkeypatch, tmp_path):
    import code_puppy.command_line.command_handler  # noqa: F401
    import code_puppy.plugins as plugins

    monkeypatch.setattr(plugins, "load_plugin_callbacks", lambda *a, **k: None)
    expected = {
        info.name
        for info in get_unique_commands()
        if info.handler.__module__.startswith("code_puppy.command_line.")
    }
    assert len(expected) > 20

    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", _FRESH_INTERPRETER_SNIPPET],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    names = json.loads(
        [line for line in result.stdout.splitlines() if line.strip()][-1]
    )
    assert set(names) >= expected, sorted(expected - set(names))
