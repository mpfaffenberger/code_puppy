"""Tests for Helios unlock functionality.

Helios requires the secret phrase 'there is no cow level' to be entered
before it becomes available. This is a classic Blizzard cheat code easter egg!
"""

import importlib

import pytest


class TestHeliosUnlock:
    """Test the helios secret phrase unlock mechanism."""

    @pytest.fixture(autouse=True)
    def reset_helios_state(self):
        """Reset helios unlock state before each test."""
        import code_puppy.config as config

        # Reset the module to clear the global state
        importlib.reload(config)
        yield
        # Reset again after the test
        importlib.reload(config)

    def test_helios_initially_locked(self):
        """Test that helios is locked by default."""
        from code_puppy.config import is_helios_unlocked

        assert is_helios_unlocked() is False

    def test_unlock_helios(self):
        """Test that unlock_helios() unlocks helios."""
        from code_puppy.config import is_helios_unlocked, unlock_helios

        assert is_helios_unlocked() is False
        unlock_helios()
        assert is_helios_unlocked() is True

    def test_secret_phrase_constant(self):
        """Test that the secret phrase is correct."""
        from code_puppy.config import HELIOS_SECRET_PHRASE

        assert HELIOS_SECRET_PHRASE == "there is no cow level"

    def test_unlock_helios_is_idempotent(self):
        """Test that calling unlock_helios multiple times is safe."""
        from code_puppy.config import is_helios_unlocked, unlock_helios

        unlock_helios()
        assert is_helios_unlocked() is True
        unlock_helios()  # Call again
        assert is_helios_unlocked() is True


class TestHeliosAgentVisibility:
    """Test that helios visibility is controlled by unlock state."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset helios unlock state and agent registry before each test."""
        import code_puppy.agents.agent_manager as am
        import code_puppy.config as config

        # Reset config module
        importlib.reload(config)
        # Clear agent registry
        am._AGENT_REGISTRY.clear()
        yield
        # Reset again after test
        importlib.reload(config)
        am._AGENT_REGISTRY.clear()

    def test_helios_hidden_when_locked(self):
        """Test that helios is not in available agents when locked."""
        from code_puppy.agents.agent_manager import get_available_agents
        from code_puppy.config import is_helios_unlocked

        assert is_helios_unlocked() is False
        agents = get_available_agents()
        assert "helios" not in agents

    def test_helios_visible_when_unlocked(self):
        """Test that helios appears in available agents when unlocked."""
        import code_puppy.agents.agent_manager as am

        from code_puppy.agents.agent_manager import get_available_agents
        from code_puppy.config import is_helios_unlocked, unlock_helios

        unlock_helios()
        assert is_helios_unlocked() is True

        # Clear registry to force rediscovery with new state
        am._AGENT_REGISTRY.clear()
        agents = get_available_agents()
        assert "helios" in agents


class TestHeliosLoadAgent:
    """Test that load_agent enforces helios lock."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset helios unlock state and agent registry before each test."""
        import code_puppy.agents.agent_manager as am
        import code_puppy.config as config

        # Reset config module
        importlib.reload(config)
        # Clear agent registry
        am._AGENT_REGISTRY.clear()
        yield
        # Reset again after test
        importlib.reload(config)
        am._AGENT_REGISTRY.clear()

    def test_load_helios_fails_when_locked(self):
        """Test that load_agent('helios') raises ValueError when locked."""
        from code_puppy.agents.agent_manager import load_agent
        from code_puppy.config import is_helios_unlocked

        assert is_helios_unlocked() is False
        with pytest.raises(ValueError) as exc_info:
            load_agent("helios")

        assert "locked" in str(exc_info.value).lower()
        assert "secret phrase" in str(exc_info.value).lower()

    def test_load_helios_succeeds_when_unlocked(self):
        """Test that load_agent('helios') works when unlocked."""
        from code_puppy.agents.agent_manager import load_agent
        from code_puppy.config import unlock_helios

        unlock_helios()
        agent = load_agent("helios")
        assert agent.name == "helios"
        assert "Helios" in agent.display_name


class TestWiggumUnlock:
    """Test the wiggum secret phrase unlock mechanism."""

    @pytest.fixture(autouse=True)
    def reset_wiggum_state(self):
        """Reset wiggum unlock state before each test."""
        import code_puppy.config as config

        # Reset the module to clear the global state
        importlib.reload(config)
        yield
        # Reset again after the test
        importlib.reload(config)

    def test_wiggum_initially_locked(self):
        """Test that wiggum is locked by default."""
        from code_puppy.config import is_wiggum_unlocked

        assert is_wiggum_unlocked() is False

    def test_unlock_wiggum(self):
        """Test that unlock_wiggum() unlocks wiggum."""
        from code_puppy.config import is_wiggum_unlocked, unlock_wiggum

        assert is_wiggum_unlocked() is False
        unlock_wiggum()
        assert is_wiggum_unlocked() is True

    def test_wiggum_secret_phrase_constant(self):
        """Test that the secret phrase is correct."""
        from code_puppy.config import WIGGUM_SECRET_PHRASE

        assert WIGGUM_SECRET_PHRASE == "show me the money"

    def test_unlock_wiggum_is_idempotent(self):
        """Test that calling unlock_wiggum multiple times is safe."""
        from code_puppy.config import is_wiggum_unlocked, unlock_wiggum

        unlock_wiggum()
        assert is_wiggum_unlocked() is True
        unlock_wiggum()  # Call again
        assert is_wiggum_unlocked() is True


class TestWiggumCommandGating:
    """Test that /wiggum command is completely hidden until unlocked."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset wiggum unlock state and command registry before each test."""
        import code_puppy.config as config

        importlib.reload(config)

        # Clear and reload command registry
        from code_puppy.command_line.command_registry import clear_registry

        clear_registry()
        import code_puppy.command_line.core_commands

        importlib.reload(code_puppy.command_line.core_commands)
        yield
        importlib.reload(config)

    def test_wiggum_command_hidden_when_locked(self):
        """Test that /wiggum command is completely hidden when locked."""
        from code_puppy.command_line.command_registry import (
            get_command,
            get_unique_commands,
        )
        from code_puppy.config import is_wiggum_unlocked

        assert is_wiggum_unlocked() is False

        # Command should not be findable
        cmd = get_command("wiggum")
        assert cmd is None

        # Command should not appear in list
        cmds = get_unique_commands()
        wiggum_names = [c.name for c in cmds if "wiggum" in c.name]
        assert len(wiggum_names) == 0

    def test_wiggum_command_visible_when_unlocked(self):
        """Test that /wiggum command appears when unlocked."""
        from code_puppy.command_line.command_registry import (
            get_command,
            get_unique_commands,
        )
        from code_puppy.config import unlock_wiggum

        unlock_wiggum()

        # Command should be findable
        cmd = get_command("wiggum")
        assert cmd is not None
        assert cmd.name == "wiggum"

        # Command should appear in list
        cmds = get_unique_commands()
        wiggum_names = [c.name for c in cmds if "wiggum" in c.name]
        assert "wiggum" in wiggum_names

    def test_wiggum_command_works_when_unlocked(self, monkeypatch):
        """Test that /wiggum command works when unlocked."""
        from code_puppy.config import unlock_wiggum

        # Capture emit calls
        emitted = []

        def mock_emit(*args, **kwargs):
            emitted.append(args)

        import code_puppy.messaging

        monkeypatch.setattr(code_puppy.messaging, "emit_success", mock_emit)
        monkeypatch.setattr(code_puppy.messaging, "emit_info", mock_emit)
        monkeypatch.setattr(code_puppy.messaging, "emit_warning", mock_emit)

        from code_puppy.command_line.core_commands import handle_wiggum_command

        unlock_wiggum()
        result = handle_wiggum_command("/wiggum test prompt")

        # When unlocked and valid, returns the prompt to execute
        assert result == "test prompt"
