"""Tests for the command catalog consumed by /help and completion tooling."""

import os
import subprocess
import sys

import pytest

from code_puppy import callbacks
from code_puppy.command_line.command_catalog import (
    CommandEntry,
    _hint_from_usage,
    list_commands,
    list_plugin_commands,
    list_registry_commands,
)
from code_puppy.command_line.command_registry import get_unique_commands

EXPECTED_INTERACTIVE = {
    "agent",
    "model",
    "add_model",
    "model_settings",
    "tutorial",
    "set",
    "autosave_load",
    "uc",
}


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


def test_interactive_builtins_are_exactly_expected():
    interactive = {entry.name for entry in list_commands() if entry.interactive}

    assert interactive == EXPECTED_INTERACTIVE


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


def test_failing_callback_yields_no_plugin_entries(monkeypatch):
    def boom():
        raise RuntimeError("plugin is broken")

    monkeypatch.setattr(callbacks, "on_custom_command_help", boom)

    assert list_plugin_commands() == []


def test_catalog_is_complete_in_fresh_interpreter(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from code_puppy.command_line.command_catalog import list_commands; "
            "print(len(list_commands()))",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert int(result.stdout.strip()) > 30
