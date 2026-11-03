"""Tests for the CommandInfo.interactive flag on registered commands."""

import pytest

import code_puppy.command_line.command_handler  # noqa: F401  (loads built-in commands)
from code_puppy.command_line import command_registry
from code_puppy.command_line.command_registry import (
    CommandInfo,
    get_command,
    get_unique_commands,
    register_command,
)

EXPECTED_INTERACTIVE_BUILTINS = {
    "agent",
    "model",
    "add_model",
    "model_settings",
    "tutorial",
    "set",
    "autosave_load",
    "uc",
}


@pytest.fixture
def isolated_registry(monkeypatch):
    """Let tests register throwaway commands without leaking into the global registry."""
    monkeypatch.setattr(
        command_registry, "_COMMAND_REGISTRY", dict(command_registry._COMMAND_REGISTRY)
    )
    yield


def test_command_info_interactive_defaults_to_false():
    info = CommandInfo(name="x", description="d", handler=lambda _: True)
    assert info.interactive is False


def test_register_command_sets_interactive_flag(isolated_registry):
    @register_command(name="zz-interactive-probe", description="d", interactive=True)
    def _handler(command: str) -> bool:
        return True

    info = get_command("zz-interactive-probe")
    assert info is not None
    assert info.interactive is True


def test_builtin_interactive_commands_are_exactly_the_picker_set():
    interactive_builtins = {
        cmd.name
        for cmd in get_unique_commands()
        if cmd.interactive
        and cmd.handler.__module__.startswith("code_puppy.command_line.")
    }
    assert interactive_builtins == EXPECTED_INTERACTIVE_BUILTINS


@pytest.mark.parametrize("name", ["help", "cd", "mcp", "clear", "show", "quick-resume"])
def test_non_picker_builtins_are_not_interactive(name):
    info = get_command(name)
    assert info is not None
    assert info.interactive is False
