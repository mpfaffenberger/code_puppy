#!/usr/bin/env python3
"""Comprehensive tests for command_registry.py.

Tests the decorator-based command registration system including:
- CommandInfo dataclass
- @register_command decorator
- Registry storage and retrieval
- Alias handling
- Category management
"""

import pytest

from code_puppy.command_line.command_registry import (
    CommandInfo,
    clear_registry,
    get_all_commands,
    get_command,
    get_unique_commands,
    register_command,
)


class TestCommandInfo:
    """Tests for CommandInfo dataclass."""

    def test_command_info_all_parameters(self):
        """Test creating CommandInfo with all parameters."""
        cmd = CommandInfo(
            name="test",
            description="Test command",
            handler=lambda x: True,
            usage="/test <arg>",
            aliases=["t", "tst"],
            category="testing",
            detailed_help="Detailed help text",
        )
        assert cmd.name == "test"
        assert cmd.description == "Test command"
        assert callable(cmd.handler)
        assert cmd.usage == "/test <arg>"
        assert cmd.aliases == ["t", "tst"]
        assert cmd.category == "testing"
        assert cmd.detailed_help == "Detailed help text"

    def test_command_info_minimal_parameters(self):
        """Test creating CommandInfo with minimal parameters (defaults)."""
        cmd = CommandInfo(
            name="minimal", description="Minimal command", handler=lambda x: True
        )
        assert cmd.name == "minimal"
        assert cmd.description == "Minimal command"
        assert callable(cmd.handler)
        assert cmd.usage == "/minimal"  # Auto-generated
        assert cmd.aliases == []  # Default empty list
        assert cmd.category == "core"  # Default category
        assert cmd.detailed_help is None  # Default None

    def test_command_info_default_usage_generation(self):
        """Test that usage is auto-generated from name if not provided."""
        cmd = CommandInfo(name="autoname", description="Test", handler=lambda x: True)
        assert cmd.usage == "/autoname"

    def test_command_info_empty_usage_gets_default(self):
        """Test that empty usage string triggers default generation."""
        cmd = CommandInfo(
            name="test", description="Test", handler=lambda x: True, usage=""
        )
        assert cmd.usage == "/test"

    def test_command_info_handler_is_callable(self):
        """Test that handler must be callable."""

        def test_handler(cmd: str) -> bool:
            return True

        cmd = CommandInfo(name="test", description="Test", handler=test_handler)
        assert callable(cmd.handler)
        assert cmd.handler("test") is True


class TestRegisterCommand:
    """Tests for @register_command decorator."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def test_register_command_basic(self):
        """Test basic command registration."""

        @register_command(name="basic", description="Basic command")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("basic")
        assert cmd is not None
        assert cmd.name == "basic"
        assert cmd.description == "Basic command"
        assert cmd.handler is handler

    def test_register_command_with_all_params(self):
        """Test registration with all parameters."""

        @register_command(
            name="full",
            description="Full command",
            usage="/full <args>",
            aliases=["f", "fl"],
            category="test",
            detailed_help="Detailed help",
        )
        def handler(command: str) -> bool:
            return True

        cmd = get_command("full")
        assert cmd.name == "full"
        assert cmd.usage == "/full <args>"
        assert cmd.aliases == ["f", "fl"]
        assert cmd.category == "test"
        assert cmd.detailed_help == "Detailed help"

    def test_register_command_with_aliases(self):
        """Test that aliases are registered."""

        @register_command(name="cmd", description="Command", aliases=["c", "command"])
        def handler(command: str) -> bool:
            return True

        # All should retrieve the same command
        cmd_by_name = get_command("cmd")
        cmd_by_alias1 = get_command("c")
        cmd_by_alias2 = get_command("command")

        assert cmd_by_name is not None
        assert cmd_by_name is cmd_by_alias1
        assert cmd_by_name is cmd_by_alias2

    def test_register_command_without_aliases(self):
        """Test registration without aliases."""

        @register_command(name="noalias", description="No aliases")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("noalias")
        assert cmd.aliases == []

    def test_register_multiple_commands(self):
        """Test registering multiple commands."""

        @register_command(name="first", description="First")
        def handler1(command: str) -> bool:
            return True

        @register_command(name="second", description="Second")
        def handler2(command: str) -> bool:
            return False

        cmd1 = get_command("first")
        cmd2 = get_command("second")

        assert cmd1 is not None
        assert cmd2 is not None
        assert cmd1.name == "first"
        assert cmd2.name == "second"
        assert cmd1.handler("test") is True
        assert cmd2.handler("test") is False

    def test_register_command_twice_overwrites(self):
        """Test that registering same command twice overwrites."""

        @register_command(name="dup", description="First version")
        def handler1(command: str) -> bool:
            return True

        @register_command(name="dup", description="Second version")
        def handler2(command: str) -> bool:
            return False

        cmd = get_command("dup")
        assert cmd.description == "Second version"
        assert cmd.handler("test") is False

    def test_decorator_returns_original_function(self):
        """Test that decorator returns the original function unchanged."""

        def original_handler(command: str) -> bool:
            return True

        decorated = register_command(name="test", description="Test")(original_handler)

        assert decorated is original_handler

    def test_register_different_categories(self):
        """Test registering commands in different categories."""

        @register_command(name="core_cmd", description="Core", category="core")
        def handler1(command: str) -> bool:
            return True

        @register_command(name="session_cmd", description="Session", category="session")
        def handler2(command: str) -> bool:
            return True

        @register_command(name="config_cmd", description="Config", category="config")
        def handler3(command: str) -> bool:
            return True

        core = get_command("core_cmd")
        session = get_command("session_cmd")
        config = get_command("config_cmd")

        assert core.category == "core"
        assert session.category == "session"
        assert config.category == "config"


class TestGetCommand:
    """Tests for get_command() function."""

    def setup_method(self):
        """Clear registry and register test commands."""
        clear_registry()

        @register_command(name="test", description="Test", aliases=["t", "tst"])
        def handler(command: str) -> bool:
            return True

    def test_get_command_by_name(self):
        """Test retrieving command by primary name."""
        cmd = get_command("test")
        assert cmd is not None
        assert cmd.name == "test"

    def test_get_command_by_alias(self):
        """Test retrieving command by alias."""
        cmd = get_command("t")
        assert cmd is not None
        assert cmd.name == "test"

        cmd2 = get_command("tst")
        assert cmd2 is not None
        assert cmd2.name == "test"

    def test_get_nonexistent_command_returns_none(self):
        """Test that getting non-existent command returns None."""
        cmd = get_command("nonexistent")
        assert cmd is None

    def test_get_command_empty_string_returns_none(self):
        """Test that empty string returns None."""
        cmd = get_command("")
        assert cmd is None

    def test_get_command_is_case_sensitive(self):
        """Test that command retrieval is case-sensitive."""
        cmd = get_command("TEST")  # Wrong case
        assert cmd is None

        cmd = get_command("test")  # Correct case
        assert cmd is not None


class TestGetAllCommands:
    """Tests for get_all_commands() function."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def test_get_all_commands_empty_registry(self):
        """Test that empty registry returns empty dict."""
        cmds = get_all_commands()
        assert cmds == {}
        assert isinstance(cmds, dict)

    def test_get_all_commands_includes_aliases(self):
        """Test that returned dict includes all aliases."""

        @register_command(name="test", description="Test", aliases=["t", "tst"])
        def handler(command: str) -> bool:
            return True

        cmds = get_all_commands()
        # Should have: test, t, tst = 3 entries
        assert len(cmds) == 3
        assert "test" in cmds
        assert "t" in cmds
        assert "tst" in cmds

    def test_get_all_commands_aliases_point_to_same_object(self):
        """Test that aliases reference the same CommandInfo object."""

        @register_command(name="test", description="Test", aliases=["t"])
        def handler(command: str) -> bool:
            return True

        cmds = get_all_commands()
        assert cmds["test"] is cmds["t"]

    def test_get_all_commands_returns_copy(self):
        """Test that returned dict is a copy (mutations don't affect registry)."""

        @register_command(name="test", description="Test")
        def handler(command: str) -> bool:
            return True

        cmds1 = get_all_commands()
        cmds1["fake"] = "value"

        cmds2 = get_all_commands()
        assert "fake" not in cmds2
        assert "test" in cmds2


class TestGetUniqueCommands:
    """Tests for get_unique_commands() function."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def test_get_unique_commands_empty_registry(self):
        """Test that empty registry returns empty list."""
        cmds = get_unique_commands()
        assert cmds == []
        assert isinstance(cmds, list)

    def test_get_unique_commands_no_duplicates(self):
        """Test that aliases don't create duplicates."""

        @register_command(
            name="test", description="Test", aliases=["t", "tst", "testing"]
        )
        def handler(command: str) -> bool:
            return True

        cmds = get_unique_commands()
        assert len(cmds) == 1  # Only 1 unique command
        assert cmds[0].name == "test"

    def test_get_unique_commands_multiple_commands(self):
        """Test getting unique commands when multiple are registered."""

        @register_command(name="first", description="First", aliases=["f"])
        def handler1(command: str) -> bool:
            return True

        @register_command(name="second", description="Second", aliases=["s"])
        def handler2(command: str) -> bool:
            return True

        @register_command(name="third", description="Third")
        def handler3(command: str) -> bool:
            return True

        cmds = get_unique_commands()
        assert len(cmds) == 3
        names = {cmd.name for cmd in cmds}
        assert names == {"first", "second", "third"}

    def test_get_unique_commands_with_no_aliases(self):
        """Test unique commands when command has no aliases."""

        @register_command(name="noalias", description="No aliases")
        def handler(command: str) -> bool:
            return True

        cmds = get_unique_commands()
        assert len(cmds) == 1
        assert cmds[0].name == "noalias"
        assert cmds[0].aliases == []


class TestClearRegistry:
    """Tests for clear_registry() function."""

    def test_clear_empty_registry(self):
        """Test that clearing empty registry doesn't error."""
        clear_registry()
        clear_registry()  # Should not raise
        assert get_all_commands() == {}

    def test_clear_registry_with_commands(self):
        """Test clearing registry with commands removes them."""

        @register_command(name="test", description="Test")
        def handler(command: str) -> bool:
            return True

        assert len(get_all_commands()) > 0

        clear_registry()
        assert get_all_commands() == {}
        assert get_command("test") is None

    def test_reregister_after_clear(self):
        """Test that commands can be re-registered after clear."""

        @register_command(name="test", description="First")
        def handler1(command: str) -> bool:
            return True

        clear_registry()

        @register_command(name="test", description="Second")
        def handler2(command: str) -> bool:
            return False

        cmd = get_command("test")
        assert cmd is not None
        assert cmd.description == "Second"

    def test_multiple_clears(self):
        """Test multiple sequential clears."""
        clear_registry()
        clear_registry()
        clear_registry()
        assert get_all_commands() == {}


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def setup_method(self):
        """Clear registry before each test."""
        clear_registry()

    def test_command_name_with_hyphens(self):
        """Test command names with hyphens."""

        @register_command(name="my-command", description="Test")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("my-command")
        assert cmd is not None
        assert cmd.name == "my-command"

    def test_command_name_with_underscores(self):
        """Test command names with underscores."""

        @register_command(name="my_command", description="Test")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("my_command")
        assert cmd is not None

    def test_very_long_command_name(self):
        """Test command with very long name."""
        long_name = "a" * 200

        @register_command(name=long_name, description="Test")
        def handler(command: str) -> bool:
            return True

        cmd = get_command(long_name)
        assert cmd is not None
        assert cmd.name == long_name

    def test_unicode_in_command_name(self):
        """Test Unicode characters in command name."""

        @register_command(name="tést", description="Test")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("tést")
        assert cmd is not None

    def test_unicode_in_description(self):
        """Test Unicode in description."""

        @register_command(name="test", description="测试 🐶")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("test")
        assert cmd.description == "测试 🐶"

    def test_empty_description(self):
        """Test command with empty description."""

        @register_command(name="test", description="")
        def handler(command: str) -> bool:
            return True

        cmd = get_command("test")
        assert cmd.description == ""

    def test_very_long_description(self):
        """Test command with very long description."""
        long_desc = "x" * 1000

        @register_command(name="test", description=long_desc)
        def handler(command: str) -> bool:
            return True

        cmd = get_command("test")
        assert cmd.description == long_desc

    def test_handler_that_raises_exception(self):
        """Test that handler can be registered even if it raises exceptions."""

        @register_command(name="boom", description="Raises error")
        def handler(command: str) -> bool:
            raise ValueError("Boom!")

        cmd = get_command("boom")
        assert cmd is not None

        # Calling the handler should raise
        with pytest.raises(ValueError, match="Boom!"):
            cmd.handler("test")

    def test_many_aliases(self):
        """Test command with many aliases."""
        aliases = [f"alias{i}" for i in range(50)]

        @register_command(name="test", description="Test", aliases=aliases)
        def handler(command: str) -> bool:
            return True

        # All aliases should work
        for alias in aliases:
            cmd = get_command(alias)
            assert cmd is not None
            assert cmd.name == "test"

    def test_duplicate_aliases_across_commands(self):
        """Test that duplicate aliases across commands causes overwrite."""

        @register_command(name="first", description="First", aliases=["shared"])
        def handler1(command: str) -> bool:
            return True

        @register_command(name="second", description="Second", aliases=["shared"])
        def handler2(command: str) -> bool:
            return False

        # The last registration wins
        cmd = get_command("shared")
        assert cmd.name == "second"
