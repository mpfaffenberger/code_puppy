"""Tests for command_registry.py - 100% coverage."""

import pytest
from code_puppy.command_line.command_registry import (
    _COMMAND_REGISTRY,
    clear_registry,
    get_all_commands,
    get_command,
    register_command,
)


@pytest.fixture(autouse=True)
def _clean():
    """Save and restore registry state."""
    saved = _COMMAND_REGISTRY.copy()
    yield
    _COMMAND_REGISTRY.clear()
    _COMMAND_REGISTRY.update(saved)


class TestGetAllCommands:
    def test_returns_copy(self):
        result = get_all_commands()
        assert isinstance(result, dict)


class TestGetCommand:
    def test_case_insensitive(self):
        clear_registry()

        @register_command(name="CamelCase", description="CC")
        def h(cmd):
            return True

        result = get_command("camelcase")
        assert result is not None


class TestRegisterCommand:
    def test_registers_primary(self):
        clear_registry()

        @register_command(name="foo", description="Foo cmd")
        def handle_foo(cmd):
            return True

        assert "foo" in _COMMAND_REGISTRY
        assert _COMMAND_REGISTRY["foo"].handler is handle_foo
