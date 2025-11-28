"""Tests for agent manager core functionality."""

import importlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents.agent_manager import (
    _AGENT_REGISTRY,
    _discover_agents,
    _load_session_data,
    _save_session_data,
    get_available_agents,
    get_current_agent,
    get_terminal_session_id,
    load_agent,
    refresh_agents,
    set_current_agent,
)
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.agents.json_agent import JSONAgent


# Define list_agents and get_agent functions for the test interface
def list_agents():
    """List available agents - wrapper for get_available_agents."""
    return list(get_available_agents().keys())


def get_agent(agent_name: str):
    """Get agent by name - wrapper for load_agent."""
    return load_agent(agent_name)


# Mock agent class for testing
class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self):
        super().__init__()
        self._name = "mock-agent"
        self._display_name = "Mock Agent 🐶"
        self._description = "A mock agent for testing purposes"

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def description(self) -> str:
        return self._description

    def get_system_prompt(self) -> str:
        return "Mock system prompt"

    def get_available_tools(self) -> list:
        return []


class TestAgentManagerBasics:
    """Test agent manager core functionality."""

    def setup_method(self):
        """Setup for each test method."""
        # Clear the registry before each test
        _AGENT_REGISTRY.clear()

    def test_list_agents_basic(self):
        """Test basic list_agents functionality."""
        agents = list_agents()
        assert isinstance(agents, list)
        assert len(agents) > 0
        assert all(isinstance(agent, str) for agent in agents)

    def test_get_agent_valid(self):
        """Test get_agent with valid agent name."""
        # First get a valid agent name
        agents = list_agents()
        if agents:
            agent = get_agent(agents[0])
            assert agent is not None
            assert hasattr(agent, "name")

    def test_list_agents_returns_list(self):
        """Test that list_agents returns a list."""
        agents = list_agents()
        assert isinstance(agents, list)

        # Should have at least one agent in the project
        assert len(agents) > 0

    def test_agent_registry_and_discovery(self):
        """Test agent registry and discovery mechanism."""
        # Get available agents to test discovery
        agents = get_available_agents()
        assert isinstance(agents, dict)
        assert len(agents) > 0

        # Verify each agent has a name and display name
        for agent_name, display_name in agents.items():
            assert isinstance(agent_name, str)
            assert isinstance(display_name, str)
            assert len(agent_name) > 0
            assert len(display_name) > 0

    def test_get_terminal_session_id(self):
        """Test that terminal session ID generation works."""
        session_id = get_terminal_session_id()
        assert isinstance(session_id, str)
        assert session_id.startswith("session_")
        # Should contain a process ID
        parts = session_id.split("_")
        assert len(parts) == 2
        assert parts[1].isdigit()

    def test_get_terminal_session_id_fallback(self):
        """Test fallback when PPID is not available."""
        with patch("os.getppid", side_effect=OSError("No PPID")):
            session_id = get_terminal_session_id()
            assert isinstance(session_id, str)
            assert session_id.startswith("fallback_")

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    @patch("importlib.import_module")
    def test_discover_agents_python_classes(
        self, mock_import, mock_iter_modules, mock_json_agents
    ):
        """Test discovering Python agent classes."""
        # Mock module discovery
        mock_iter_modules.return_value = [("code_puppy.agents", "mock_agent", True)]

        # Mock module with agent class
        mock_module = MagicMock()
        mock_module.MockAgent = MockAgent
        mock_import.return_value = mock_module

        # Mock JSON agents discovery
        mock_json_agents.return_value = {}

        _discover_agents()

        # Verify agent was registered
        assert "mock-agent" in _AGENT_REGISTRY
        assert _AGENT_REGISTRY["mock-agent"] == MockAgent

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    def test_discover_agents_json_agents(self, mock_iter_modules, mock_json_agents):
        """Test discovering JSON agents."""
        # Mock no Python modules
        mock_iter_modules.return_value = []

        # Mock JSON agents
        mock_json_agents.return_value = {"json-agent": "/path/to/agent.json"}

        _discover_agents()

        # Verify JSON agent was registered
        assert "json-agent" in _AGENT_REGISTRY
        assert _AGENT_REGISTRY["json-agent"] == "/path/to/agent.json"

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    def test_discover_agents_skips_internal_modules(
        self, mock_iter_modules, mock_json_agents
    ):
        """Test that internal modules are skipped during discovery."""
        # Mock internal modules
        mock_iter_modules.return_value = [
            ("code_puppy.agents", "_internal", True),
            ("code_puppy.agents", "base_agent", True),
            ("code_puppy.agents", "json_agent", True),
            ("code_puppy.agents", "agent_manager", True),
            ("code_puppy.agents", "valid_agent", True),
        ]

        # Mock valid module with a custom agent class
        class ValidAgent(MockAgent):
            def __init__(self):
                super().__init__()
                self._name = "valid-agent"

        mock_module = MagicMock()
        mock_module.ValidAgent = ValidAgent

        def mock_import_side_effect(module_name):
            if "valid_agent" in module_name:
                return mock_module
            return MagicMock()

        with patch("importlib.import_module", side_effect=mock_import_side_effect):
            mock_json_agents.return_value = {}
            _discover_agents()

        # Only valid agent should be registered
        assert "valid-agent" in _AGENT_REGISTRY
        assert len(_AGENT_REGISTRY) == 1

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    def test_discover_agents_handles_import_errors(
        self, mock_iter_modules, mock_json_agents
    ):
        """Test that import errors are handled gracefully."""
        mock_iter_modules.return_value = [("code_puppy.agents", "broken_agent", True)]

        # Create a side effect that only fails for the broken agent module
        def mock_import_side_effect(module_name):
            if module_name == "code_puppy.agents.broken_agent":
                raise ImportError("Module not found")
            # Import everything else normally
            return importlib.import_module(module_name)

        # Patch emit_warning where it's imported in agent_manager
        with patch("code_puppy.agents.agent_manager.emit_warning") as mock_warn:
            with patch("importlib.import_module", side_effect=mock_import_side_effect):
                mock_json_agents.return_value = {}
                _discover_agents()

                # Warning should be emitted for broken module
                mock_warn.assert_called_once()
                assert "broken_agent" in mock_warn.call_args[0][0]

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    @patch("importlib.import_module")
    def test_get_available_agents(
        self, mock_import, mock_iter_modules, mock_json_agents
    ):
        """Test getting available agents with display names."""
        # Setup mock agents
        mock_iter_modules.return_value = [("code_puppy.agents", "mock_agent", True)]

        mock_module = MagicMock()
        mock_module.MockAgent = MockAgent
        mock_import.return_value = mock_module

        mock_json_agents.return_value = {"json-agent": "/path/to/agent.json"}

        agents = get_available_agents()

        assert isinstance(agents, dict)
        assert len(agents) >= 1
        assert "mock-agent" in agents
        assert agents["mock-agent"] == "Mock Agent 🐶"
        # Check that we have some agents (the actual discovery may include real agents)
        assert len(agents) > 0

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    @patch("importlib.import_module")
    def test_load_agent_python_class(
        self, mock_import, mock_iter_modules, mock_json_agents
    ):
        """Test loading a Python agent class."""
        # Setup registry
        mock_iter_modules.return_value = [("code_puppy.agents", "mock_agent", True)]

        mock_module = MagicMock()
        mock_module.MockAgent = MockAgent
        mock_import.return_value = mock_module

        mock_json_agents.return_value = {}
        _discover_agents()

        # Load the agent
        agent = load_agent("mock-agent")

        assert isinstance(agent, MockAgent)
        assert agent.name == "mock-agent"

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    def test_load_agent_json_class(self, mock_iter_modules, mock_json_agents):
        """Test loading a JSON agent."""
        mock_iter_modules.return_value = []
        mock_json_agents.return_value = {"json-agent": "/path/to/agent.json"}
        _discover_agents()

        with patch.object(JSONAgent, "__init__", return_value=None) as mock_init:
            load_agent("json-agent")
            mock_init.assert_called_once_with("/path/to/agent.json")

    def test_load_agent_not_found(self):
        """Test loading an agent that doesn't exist."""
        # Clear registry and mock discovery to return no agents
        with patch("code_puppy.agents.agent_manager._discover_agents"):
            _AGENT_REGISTRY.clear()

            # The actual behavior is that it tries to fallback to code-puppy
            # Since we have no agents, it should raise ValueError
            with pytest.raises(ValueError, match="not found and no fallback"):
                load_agent("nonexistent-agent")

    @patch("code_puppy.agents.agent_manager.discover_json_agents")
    @patch("pkgutil.iter_modules")
    @patch("importlib.import_module")
    def test_load_agent_fallback_to_code_puppy(
        self, mock_import, mock_iter_modules, mock_json_agents
    ):
        """Test fallback to code-puppy agent when requested agent not found."""

        # Setup registry with only code-puppy
        class CodePuppyAgent(MockAgent):
            def __init__(self):
                super().__init__()
                self._name = "code-puppy"

        mock_iter_modules.return_value = [("code_puppy.agents", "code_puppy", True)]

        mock_module = MagicMock()
        mock_module.CodePuppyAgent = CodePuppyAgent

        def mock_import_side_effect(module_name):
            if "code_puppy" in module_name:
                return mock_module
            return MagicMock()

        mock_import.side_effect = mock_import_side_effect
        mock_json_agents.return_value = {}

        # Try to load non-existent agent
        agent = load_agent("nonexistent-agent")

        # Should fallback to code-puppy
        assert agent is not None
        assert agent.name == "code-puppy"

    def test_refresh_agents(self):
        """Test refreshing agent discovery."""
        with patch("code_puppy.agents.agent_manager._discover_agents") as mock_discover:
            refresh_agents()
            mock_discover.assert_called_once()

    def test_session_data_persistence(self):
        """Test session data loading and saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / "test_sessions.json"

            # Test saving
            test_sessions = {"session_123": "agent1", "session_456": "agent2"}

            with (
                patch(
                    "code_puppy.agents.agent_manager._get_session_file_path",
                    return_value=session_file,
                ),
                patch(
                    "code_puppy.agents.agent_manager._is_process_alive",
                    return_value=True,  # Mock that test session PIDs are alive
                ),
            ):
                _save_session_data(test_sessions)

                # Verify file was created
                assert session_file.exists()

                # Test loading
                loaded = _load_session_data()
                # With mocked _is_process_alive, sessions should be preserved
                assert "session_123" in loaded
                assert "session_456" in loaded
                assert isinstance(loaded, dict)

    def test_session_data_handles_corrupted_file(self):
        """Test handling of corrupted session file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / "corrupted_sessions.json"

            # Write corrupted JSON
            session_file.write_text("{ invalid json }")

            with patch(
                "code_puppy.agents.agent_manager._get_session_file_path",
                return_value=session_file,
            ):
                loaded = _load_session_data()
                assert loaded == {}  # Should return empty dict

    @patch("code_puppy.agents.agent_manager._save_session_data")
    @patch("code_puppy.agents.agent_manager._load_session_data")
    @patch("code_puppy.agents.agent_manager.load_agent")
    @patch("code_puppy.agents.agent_manager.get_current_agent_name")
    def test_set_current_agent(
        self, mock_get_name, mock_load_agent, mock_load_data, mock_save_data
    ):
        """Test setting current agent."""
        # Setup mocks
        mock_get_name.return_value = "current-agent"
        mock_load_data.return_value = {}
        mock_agent = MockAgent()
        mock_load_agent.return_value = mock_agent

        # Set current agent
        result = set_current_agent("new-agent")

        assert result is True
        mock_load_agent.assert_called_with("new-agent")
        mock_save_data.assert_called_once()

    @patch("code_puppy.agents.agent_manager.load_agent")
    @patch("code_puppy.agents.agent_manager.get_current_agent_name")
    def test_get_current_agent(self, mock_get_name, mock_load_agent):
        """Test getting current agent."""
        mock_get_name.return_value = "test-agent"
        mock_agent = MockAgent()
        mock_load_agent.return_value = mock_agent

        # Clear global current agent to force loading
        import code_puppy.agents.agent_manager as am

        am._CURRENT_AGENT = None

        agent = get_current_agent()

        assert agent == mock_agent
        mock_get_name.assert_called_once()
        mock_load_agent.assert_called_once_with("test-agent")

    def test_agent_registry_isolation(self):
        """Test that agent registry works in isolation."""
        # Test that registry starts empty
        original_size = len(_AGENT_REGISTRY)

        # Add a test agent
        _AGENT_REGISTRY["test-agent"] = MockAgent

        # Verify it was added
        assert "test-agent" in _AGENT_REGISTRY
        assert len(_AGENT_REGISTRY) == original_size + 1

        # Clear for cleanup
        _AGENT_REGISTRY.clear()

    def test_load_agent_with_empty_registry(self):
        """Test load_agent behavior with completely empty registry."""
        # Mock discovery to ensure empty registry
        with patch("code_puppy.agents.agent_manager._discover_agents"):
            _AGENT_REGISTRY.clear()

            with pytest.raises(ValueError, match="not found and no fallback"):
                load_agent("any-agent")
