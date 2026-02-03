"""Tests for the /wiggum command and state management.

The wiggum feature allows users to automatically re-run the same prompt
when the agent finishes, like Chief Wiggum chasing donuts in circles. 🍩
"""


class TestWiggumState:
    """Test wiggum state management."""

    def setup_method(self):
        """Reset wiggum state before each test."""
        from code_puppy.command_line.wiggum_state import stop_wiggum

        stop_wiggum()

    def test_initial_state_inactive(self):
        """Wiggum should be inactive by default."""
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_count,
            get_wiggum_prompt,
            is_wiggum_active,
        )

        assert not is_wiggum_active()
        assert get_wiggum_prompt() is None
        assert get_wiggum_count() == 0

    def test_start_wiggum(self):
        """Starting wiggum should set active state and prompt."""
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_count,
            get_wiggum_prompt,
            is_wiggum_active,
            start_wiggum,
        )

        start_wiggum("say hello world")

        assert is_wiggum_active()
        assert get_wiggum_prompt() == "say hello world"
        assert get_wiggum_count() == 0

    def test_stop_wiggum(self):
        """Stopping wiggum should reset all state."""
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_count,
            get_wiggum_prompt,
            increment_wiggum_count,
            is_wiggum_active,
            start_wiggum,
            stop_wiggum,
        )

        start_wiggum("test prompt")
        increment_wiggum_count()
        increment_wiggum_count()

        stop_wiggum()

        assert not is_wiggum_active()
        assert get_wiggum_prompt() is None
        assert get_wiggum_count() == 0

    def test_increment_count(self):
        """Incrementing count should return new value."""
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_count,
            increment_wiggum_count,
            start_wiggum,
        )

        start_wiggum("test")

        count1 = increment_wiggum_count()
        count2 = increment_wiggum_count()
        count3 = increment_wiggum_count()

        assert count1 == 1
        assert count2 == 2
        assert count3 == 3
        assert get_wiggum_count() == 3

    def test_get_wiggum_state_singleton(self):
        """get_wiggum_state should return the same instance."""
        from code_puppy.command_line.wiggum_state import get_wiggum_state

        state1 = get_wiggum_state()
        state2 = get_wiggum_state()

        assert state1 is state2

    def test_wiggum_state_dataclass(self):
        """WiggumState dataclass should work correctly."""
        from code_puppy.command_line.wiggum_state import get_wiggum_state

        state = get_wiggum_state()

        # Test start method
        state.start("new prompt")
        assert state.active is True
        assert state.prompt == "new prompt"
        assert state.loop_count == 0

        # Test increment method
        result = state.increment()
        assert result == 1
        assert state.loop_count == 1

        # Test stop method
        state.stop()
        assert state.active is False
        assert state.prompt is None
        assert state.loop_count == 0


class TestWiggumCommand:
    """Test wiggum command registration and handling."""

    def setup_method(self):
        """Reset wiggum state and ensure commands are registered before each test."""
        import importlib

        import code_puppy.command_line.core_commands
        from code_puppy.command_line.wiggum_state import stop_wiggum

        # Reload core_commands to ensure commands are registered
        # (in case a previous test cleared the registry)
        importlib.reload(code_puppy.command_line.core_commands)
        stop_wiggum()

    def test_wiggum_command_registered(self):
        """The /wiggum command should be registered."""
        from code_puppy.command_line.command_registry import get_command

        cmd = get_command("wiggum")

        assert cmd is not None
        assert cmd.name == "wiggum"
        assert "wiggum" in cmd.usage.lower()

    def test_wiggum_stop_command_registered(self):
        """The /wiggum_stop command should be registered with aliases."""
        from code_puppy.command_line.command_registry import get_command

        cmd = get_command("wiggum_stop")

        assert cmd is not None
        assert cmd.name == "wiggum_stop"
        assert "ws" in cmd.aliases
        assert "stopwiggum" in cmd.aliases

    def test_wiggum_command_without_prompt_returns_true(self):
        """Calling /wiggum without a prompt should show help and return True."""
        from code_puppy.command_line.command_registry import get_command
        from code_puppy.command_line.wiggum_state import is_wiggum_active

        cmd = get_command("wiggum")
        result = cmd.handler("/wiggum")

        assert result is True
        assert not is_wiggum_active()  # Should not activate without prompt

    def test_wiggum_command_with_prompt_returns_prompt(self):
        """Calling /wiggum with a prompt should return the prompt for execution."""
        from code_puppy.command_line.command_registry import get_command
        from code_puppy.command_line.wiggum_state import (
            get_wiggum_prompt,
            is_wiggum_active,
        )

        cmd = get_command("wiggum")
        result = cmd.handler("/wiggum say hello world")

        assert result == "say hello world"
        assert is_wiggum_active()
        assert get_wiggum_prompt() == "say hello world"

    def test_wiggum_stop_command_when_active(self):
        """Calling /wiggum_stop when active should stop wiggum mode."""
        from code_puppy.command_line.command_registry import get_command
        from code_puppy.command_line.wiggum_state import is_wiggum_active, start_wiggum

        start_wiggum("test prompt")
        assert is_wiggum_active()

        cmd = get_command("wiggum_stop")
        result = cmd.handler("/wiggum_stop")

        assert result is True
        assert not is_wiggum_active()

    def test_wiggum_stop_command_when_inactive(self):
        """Calling /wiggum_stop when inactive should just return True."""
        from code_puppy.command_line.command_registry import get_command
        from code_puppy.command_line.wiggum_state import is_wiggum_active

        assert not is_wiggum_active()

        cmd = get_command("wiggum_stop")
        result = cmd.handler("/wiggum_stop")

        assert result is True
        assert not is_wiggum_active()

    def test_wiggum_stop_alias_ws(self):
        """The /ws alias should work for wiggum_stop."""
        from code_puppy.command_line.command_registry import get_command

        cmd = get_command("ws")

        assert cmd is not None
        assert cmd.name == "wiggum_stop"  # Same CommandInfo
