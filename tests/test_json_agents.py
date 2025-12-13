"""Tests for JSON agent functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.agents.json_agent import (
    JSONAgent,
    discover_json_agents,
    discover_local_json_agents,
)
from code_puppy.config import get_user_agents_directory


class TestJSONAgent:
    """Test JSON agent functionality."""

    @pytest.fixture
    def sample_json_config(self):
        """Sample JSON agent configuration."""
        return {
            "name": "test-agent",
            "display_name": "Test Agent 🧪",
            "description": "A test agent for unit testing",
            "system_prompt": "You are a test agent.",
            "tools": ["list_files", "read_file", "edit_file"],
            "user_prompt": "Enter your test request:",
            "tools_config": {"timeout": 30},
        }

    @pytest.fixture
    def sample_json_config_with_list_prompt(self):
        """Sample JSON agent configuration with list-based system prompt."""
        return {
            "name": "list-prompt-agent",
            "description": "Agent with list-based system prompt",
            "system_prompt": [
                "You are a helpful assistant.",
                "You help users with coding tasks.",
                "Always be polite and professional.",
            ],
            "tools": ["list_files", "read_file"],
        }

    @pytest.fixture
    def temp_json_file(self, sample_json_config):
        """Create a temporary JSON file with sample config."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-agent.json", delete=False
        ) as f:
            json.dump(sample_json_config, f)
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_json_agent_loading(self, temp_json_file):
        """Test loading a JSON agent from file."""
        agent = JSONAgent(temp_json_file)

        assert agent.name == "test-agent"
        assert agent.display_name == "Test Agent 🧪"
        assert agent.description == "A test agent for unit testing"
        assert agent.get_system_prompt() == "You are a test agent."
        assert agent.get_user_prompt() == "Enter your test request:"
        assert agent.get_tools_config() == {"timeout": 30}

    def test_json_agent_with_list_prompt(self, sample_json_config_with_list_prompt):
        """Test JSON agent with list-based system prompt."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-agent.json", delete=False
        ) as f:
            json.dump(sample_json_config_with_list_prompt, f)
            temp_path = f.name

        try:
            agent = JSONAgent(temp_path)

            assert agent.name == "list-prompt-agent"
            assert agent.display_name == "List-Prompt-Agent 🤖"  # Fallback display name

            # List-based prompt should be joined with newlines
            expected_prompt = "\n".join(
                [
                    "You are a helpful assistant.",
                    "You help users with coding tasks.",
                    "Always be polite and professional.",
                ]
            )
            assert agent.get_system_prompt() == expected_prompt

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_json_agent_available_tools(self, temp_json_file):
        """Test that JSON agent filters tools correctly."""
        agent = JSONAgent(temp_json_file)
        tools = agent.get_available_tools()

        # Should only return tools that exist in our registry
        # "final_result" from JSON should be filtered out
        expected_tools = ["list_files", "read_file", "edit_file"]
        assert tools == expected_tools

    def test_json_agent_inheritance(self, temp_json_file):
        """Test that JSONAgent properly inherits from BaseAgent."""
        agent = JSONAgent(temp_json_file)

        assert isinstance(agent, BaseAgent)
        assert hasattr(agent, "name")
        assert hasattr(agent, "display_name")
        assert hasattr(agent, "description")
        assert callable(agent.get_system_prompt)
        assert callable(agent.get_available_tools)

    def test_invalid_json_file(self):
        """Test handling of invalid JSON files."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-agent.json", delete=False
        ) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Failed to load JSON agent config"):
                JSONAgent(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_missing_required_fields(self):
        """Test handling of JSON with missing required fields."""
        incomplete_config = {
            "name": "incomplete-agent"
            # Missing description, system_prompt, tools
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-agent.json", delete=False
        ) as f:
            json.dump(incomplete_config, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Missing required field"):
                JSONAgent(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_invalid_tools_field(self):
        """Test handling of invalid tools field."""
        invalid_config = {
            "name": "invalid-tools-agent",
            "description": "Test agent",
            "system_prompt": "Test prompt",
            "tools": "not a list",  # Should be a list
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix="-agent.json", delete=False
        ) as f:
            json.dump(invalid_config, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="'tools' must be a list"):
                JSONAgent(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestJSONAgentDiscovery:
    """Test JSON agent discovery functionality."""

    def test_discover_json_agents(self, monkeypatch):
        """Test discovering JSON agents in the user directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the agents directory to use our temp directory
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: temp_dir
            )
            # Mock CWD to prevent local agents from interfering
            monkeypatch.setattr("os.getcwd", lambda: "/nonexistent/test/dir")

            # Create valid JSON agent
            agent1_config = {
                "name": "agent1",
                "description": "First agent",
                "system_prompt": "Agent 1 prompt",
                "tools": ["list_files"],
            }
            agent1_path = (
                Path(temp_dir) / "agent1.json"
            )  # Changed from agent1-agent.json
            with open(agent1_path, "w") as f:
                json.dump(agent1_config, f)

            # Create another valid JSON agent
            agent2_config = {
                "name": "agent2",
                "description": "Second agent",
                "system_prompt": "Agent 2 prompt",
                "tools": ["read_file"],
            }
            agent2_path = Path(temp_dir) / "custom-agent.json"
            with open(agent2_path, "w") as f:
                json.dump(agent2_config, f)

            # Create invalid JSON file (should be skipped)
            invalid_path = (
                Path(temp_dir) / "invalid.json"
            )  # Changed from invalid-agent.json
            with open(invalid_path, "w") as f:
                f.write("invalid json")

            # Create non-agent JSON file (should be skipped)
            other_path = Path(temp_dir) / "other.json"
            with open(other_path, "w") as f:
                json.dump({"not": "an agent"}, f)

            # Discover agents
            agents = discover_json_agents()

            # Should find only the two valid agents
            assert len(agents) == 2
            assert "agent1" in agents
            assert "agent2" in agents
            assert agents["agent1"] == str(agent1_path)
            assert agents["agent2"] == str(agent2_path)

    def test_discover_nonexistent_directory(self, monkeypatch):
        """Test discovering agents when directory doesn't exist."""
        # Mock the agents directory to point to non-existent directory
        monkeypatch.setattr(
            "code_puppy.config.get_user_agents_directory",
            lambda: "/nonexistent/directory",
        )
        # Mock CWD to prevent local agents from interfering
        monkeypatch.setattr("os.getcwd", lambda: "/nonexistent/test/dir")
        agents = discover_json_agents()
        assert agents == {}

    def test_get_user_agents_directory(self):
        """Test getting user agents directory."""
        user_dir = get_user_agents_directory()

        assert isinstance(user_dir, str)
        # Should contain code_puppy (either legacy .code_puppy or XDG code_puppy)
        assert "code_puppy" in user_dir
        assert "agents" in user_dir

        # Directory should be created
        assert Path(user_dir).exists()
        assert Path(user_dir).is_dir()

    def test_user_agents_directory_windows(self, monkeypatch):
        """Test user agents directory cross-platform consistency."""
        mock_agents_dir = "/fake/home/.code_puppy/agents"

        # Override the AGENTS_DIR constant directly
        monkeypatch.setattr("code_puppy.config.AGENTS_DIR", mock_agents_dir)

        with patch("code_puppy.config.os.makedirs") as mock_makedirs:
            user_dir = get_user_agents_directory()

            assert user_dir == mock_agents_dir
            mock_makedirs.assert_called_once_with(mock_agents_dir, exist_ok=True)

    def test_user_agents_directory_macos(self, monkeypatch):
        """Test user agents directory on macOS."""
        mock_agents_dir = "/fake/home/.code_puppy/agents"

        # Override the AGENTS_DIR constant directly
        monkeypatch.setattr("code_puppy.config.AGENTS_DIR", mock_agents_dir)

        with patch("code_puppy.config.os.makedirs") as mock_makedirs:
            user_dir = get_user_agents_directory()

            assert user_dir == mock_agents_dir
            mock_makedirs.assert_called_once_with(mock_agents_dir, exist_ok=True)


class TestLocalJSONAgentDiscovery:
    """Test local JSON agent discovery functionality."""

    def test_discover_local_json_agents(self, monkeypatch):
        """Test discovering JSON agents in the local .code_puppy/agents directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the current working directory
            monkeypatch.setattr("os.getcwd", lambda: temp_dir)

            # Create .code_puppy/agents directory
            local_agents_dir = Path(temp_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            # Create valid JSON agents
            agent1_config = {
                "name": "local-agent-1",
                "description": "First local agent",
                "system_prompt": "Local agent 1 prompt",
                "tools": ["list_files"],
            }
            agent1_path = local_agents_dir / "local-agent-1.json"
            with open(agent1_path, "w") as f:
                json.dump(agent1_config, f)

            agent2_config = {
                "name": "local-agent-2",
                "description": "Second local agent",
                "system_prompt": "Local agent 2 prompt",
                "tools": ["read_file"],
            }
            agent2_path = local_agents_dir / "local-agent-2.json"
            with open(agent2_path, "w") as f:
                json.dump(agent2_config, f)

            # Discover local agents
            agents = discover_local_json_agents()

            # Should find both local agents
            assert len(agents) == 2
            assert "local-agent-1" in agents
            assert "local-agent-2" in agents
            assert agents["local-agent-1"] == str(agent1_path)
            assert agents["local-agent-2"] == str(agent2_path)

    def test_discover_local_agents_no_directory(self, monkeypatch):
        """Test discovering local agents when .code_puppy/agents doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the current working directory
            monkeypatch.setattr("os.getcwd", lambda: temp_dir)

            # Don't create .code_puppy/agents directory
            agents = discover_local_json_agents()

            # Should return empty dict
            assert agents == {}

    def test_discover_local_agents_empty_directory(self, monkeypatch):
        """Test discovering local agents when directory is empty."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the current working directory
            monkeypatch.setattr("os.getcwd", lambda: temp_dir)

            # Create empty .code_puppy/agents directory
            local_agents_dir = Path(temp_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            agents = discover_local_json_agents()

            # Should return empty dict
            assert agents == {}

    def test_discover_local_agents_skip_invalid(self, monkeypatch):
        """Test that invalid local agent files are skipped."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock the current working directory
            monkeypatch.setattr("os.getcwd", lambda: temp_dir)

            # Create .code_puppy/agents directory
            local_agents_dir = Path(temp_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            # Create valid agent
            valid_config = {
                "name": "valid-local-agent",
                "description": "Valid agent",
                "system_prompt": "Valid prompt",
                "tools": ["list_files"],
            }
            valid_path = local_agents_dir / "valid.json"
            with open(valid_path, "w") as f:
                json.dump(valid_config, f)

            # Create invalid JSON
            invalid_path = local_agents_dir / "invalid.json"
            with open(invalid_path, "w") as f:
                f.write("invalid json content")

            # Create JSON with missing fields
            incomplete_path = local_agents_dir / "incomplete.json"
            with open(incomplete_path, "w") as f:
                json.dump({"name": "incomplete"}, f)

            agents = discover_local_json_agents()

            # Should only find the valid agent
            assert len(agents) == 1
            assert "valid-local-agent" in agents

    def test_local_agents_override_global_agents(self, monkeypatch):
        """Test that local agents override global agents with the same name."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create global agent
            global_config = {
                "name": "test-agent",
                "description": "Global agent",
                "system_prompt": "Global prompt",
                "tools": ["list_files"],
            }
            global_path = Path(global_dir) / "test-agent.json"
            with open(global_path, "w") as f:
                json.dump(global_config, f)

            # Create local agent with same name
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "test-agent",
                "description": "Local agent (override)",
                "system_prompt": "Local override prompt",
                "tools": ["read_file"],
            }
            local_path = local_agents_dir / "test-agent.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Discover all agents
            agents = discover_json_agents()

            # Should have only one entry for 'test-agent'
            assert "test-agent" in agents

            # The path should be the local one (not global)
            assert agents["test-agent"] == str(local_path)
            assert agents["test-agent"] != str(global_path)

            # Verify the agent loads with local config
            agent = JSONAgent(agents["test-agent"])
            assert agent.description == "Local agent (override)"
            assert agent.get_system_prompt() == "Local override prompt"

    def test_mixed_global_and_local_agents(self, monkeypatch):
        """Test discovery with both global and local agents."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create global agents
            global_config_1 = {
                "name": "global-agent-1",
                "description": "Global agent 1",
                "system_prompt": "Global prompt 1",
                "tools": ["list_files"],
            }
            global_path_1 = Path(global_dir) / "global-agent-1.json"
            with open(global_path_1, "w") as f:
                json.dump(global_config_1, f)

            global_config_2 = {
                "name": "global-agent-2",
                "description": "Global agent 2",
                "system_prompt": "Global prompt 2",
                "tools": ["read_file"],
            }
            global_path_2 = Path(global_dir) / "global-agent-2.json"
            with open(global_path_2, "w") as f:
                json.dump(global_config_2, f)

            # Create local agents
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config_1 = {
                "name": "local-agent-1",
                "description": "Local agent 1",
                "system_prompt": "Local prompt 1",
                "tools": ["grep"],
            }
            local_path_1 = local_agents_dir / "local-agent-1.json"
            with open(local_path_1, "w") as f:
                json.dump(local_config_1, f)

            local_config_2 = {
                "name": "local-agent-2",
                "description": "Local agent 2",
                "system_prompt": "Local prompt 2",
                "tools": ["edit_file"],
            }
            local_path_2 = local_agents_dir / "local-agent-2.json"
            with open(local_path_2, "w") as f:
                json.dump(local_config_2, f)

            # Discover all agents
            agents = discover_json_agents()

            # Should have all 4 agents
            assert len(agents) == 4
            assert "global-agent-1" in agents
            assert "global-agent-2" in agents
            assert "local-agent-1" in agents
            assert "local-agent-2" in agents

            # Verify paths
            assert agents["global-agent-1"] == str(global_path_1)
            assert agents["global-agent-2"] == str(global_path_2)
            assert agents["local-agent-1"] == str(local_path_1)
            assert agents["local-agent-2"] == str(local_path_2)

    def test_local_agents_only(self, monkeypatch):
        """Test discovery when only local agents exist (no global)."""
        with tempfile.TemporaryDirectory() as local_dir:
            # Mock directories - global doesn't exist
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory",
                lambda: "/nonexistent/global",
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create local agents
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "local-only-agent",
                "description": "Local only agent",
                "system_prompt": "Local only prompt",
                "tools": ["list_files"],
            }
            local_path = local_agents_dir / "local-only-agent.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Discover all agents
            agents = discover_json_agents()

            # Should find local agent even without global directory
            assert len(agents) == 1
            assert "local-only-agent" in agents
            assert agents["local-only-agent"] == str(local_path)
