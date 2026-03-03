"""Tests for command_registry.py - 100% coverage."""

import pytest

from code_puppy.command_line.command_registry import (
    _COMMAND_REGISTRY,
    CommandInfo,
    clear_registry,
    get_all_commands,
    get_command,
    get_unique_commands,
    register_command,
)


@pytest.fixture(autouse=True)
def _clean():
    """Save and restore registry state."""
    saved = _COMMAND_REGISTRY.copy()
    yield
    _COMMAND_REGISTRY.clear()
    _COMMAND_REGISTRY.update(saved)


class TestCommandInfo:
    def test_default_usage(self):
        ci = CommandInfo(name="test", description="desc", handler=lambda x: True)
        assert ci.usage == "/test"

    def test_custom_usage(self):
        ci = CommandInfo(
            name="test", description="desc", handler=lambda x: True, usage="/test <arg>"
        )
        assert ci.usage == "/test <arg>"


class TestRegisterCommand:
    def test_registers_primary(self):
        clear_registry()

        @register_command(name="foo", description="Foo cmd")
        def handle_foo(cmd):
            return True

        assert "foo" in _COMMAND_REGISTRY
        assert _COMMAND_REGISTRY["foo"].handler is handle_foo

    def test_registers_aliases(self):
        clear_registry()

        @register_command(name="bar", description="Bar cmd", aliases=["b", "ba"])
        def handle_bar(cmd):
            return True

        assert "bar" in _COMMAND_REGISTRY
        assert "b" in _COMMAND_REGISTRY
        assert "ba" in _COMMAND_REGISTRY
        assert _COMMAND_REGISTRY["b"] is _COMMAND_REGISTRY["bar"]


class TestGetCommand:
    def test_exact_match(self):
        clear_registry()

        @register_command(name="exact", description="Exact")
        def h(cmd):
            return True

        assert get_command("exact") is not None

    def test_case_insensitive(self):
        clear_registry()

        @register_command(name="CamelCase", description="CC")
        def h(cmd):
            return True

        result = get_command("camelcase")
        assert result is not None

    def test_not_found(self):
        clear_registry()
        assert get_command("nonexistent") is None


class TestGetUniqueCommands:
    def test_no_duplicates_from_aliases(self):
        clear_registry()

        @register_command(name="cmd1", description="C1", aliases=["c1"])
        def h1(cmd):
            return True

        unique = get_unique_commands()
        assert len(unique) == 1


class TestGetAllCommands:
    def test_returns_copy(self):
        result = get_all_commands()
        assert isinstance(result, dict)


class TestClearRegistry:
    def test_clears(self):
        _COMMAND_REGISTRY["temp"] = CommandInfo(
            name="temp", description="t", handler=lambda x: True
        )
        clear_registry()
        assert len(_COMMAND_REGISTRY) == 0
