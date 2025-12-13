"""Integration tests for local agent discovery with agent_manager."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents.agent_manager import (
    get_available_agents,
    load_agent,
    set_current_agent,
    _discover_agents,
)
from code_puppy.agents.json_agent import JSONAgent


class TestLocalAgentIntegration:
    """Test local agent integration with agent_manager."""

    def test_agent_manager_discovers_local_agents(self, monkeypatch):
        """Test that agent_manager discovers local agents."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create local agent
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "test-local-integration",
                "description": "Test local integration agent",
                "system_prompt": "Test integration prompt",
                "tools": ["list_files"],
            }
            local_path = local_agents_dir / "test-local-integration.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Get available agents from agent_manager
            agents = get_available_agents()

            # Should include the local agent
            assert "test-local-integration" in agents

    def test_agent_manager_loads_local_agent(self, monkeypatch):
        """Test that agent_manager can load a local agent."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create local agent
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "test-load-local",
                "display_name": "Test Load Local 🧪",
                "description": "Test loading local agent",
                "system_prompt": "Test load prompt",
                "tools": ["list_files", "read_file"],
            }
            local_path = local_agents_dir / "test-load-local.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Load the agent
            agent = load_agent("test-load-local")

            # Verify it's a JSONAgent with correct config
            assert isinstance(agent, JSONAgent)
            assert agent.name == "test-load-local"
            assert agent.display_name == "Test Load Local 🧪"
            assert agent.description == "Test loading local agent"
            assert "list_files" in agent.get_available_tools()
            assert "read_file" in agent.get_available_tools()

    def test_agent_manager_local_overrides_global(self, monkeypatch):
        """Test that agent_manager respects local agent override of global agent."""
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
                "name": "override-test",
                "description": "Global version",
                "system_prompt": "Global prompt",
                "tools": ["list_files"],
            }
            global_path = Path(global_dir) / "override-test.json"
            with open(global_path, "w") as f:
                json.dump(global_config, f)

            # Create local agent with same name
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "override-test",
                "description": "Local version (OVERRIDE)",
                "system_prompt": "Local override prompt",
                "tools": ["read_file", "grep"],
            }
            local_path = local_agents_dir / "override-test.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Load the agent
            agent = load_agent("override-test")

            # Verify it loaded the local version
            assert agent.description == "Local version (OVERRIDE)"
            assert agent.get_system_prompt() == "Local override prompt"
            assert "read_file" in agent.get_available_tools()
            assert "grep" in agent.get_available_tools()

    def test_set_current_agent_with_local_agent(self, monkeypatch):
        """Test setting current agent to a local agent."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create local agent
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "test-set-current",
                "display_name": "Test Set Current 🎯",
                "description": "Test setting as current",
                "system_prompt": "Test current prompt",
                "tools": ["list_files"],
            }
            local_path = local_agents_dir / "test-set-current.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Set as current agent
            result = set_current_agent("test-set-current")

            # Should succeed
            assert result is True

    def test_discover_agents_includes_local(self, monkeypatch):
        """Test that _discover_agents includes local agents in registry."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create global and local agents
            global_config = {
                "name": "global-discover",
                "description": "Global agent",
                "system_prompt": "Global",
                "tools": ["list_files"],
            }
            global_path = Path(global_dir) / "global-discover.json"
            with open(global_path, "w") as f:
                json.dump(global_config, f)

            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "local-discover",
                "description": "Local agent",
                "system_prompt": "Local",
                "tools": ["read_file"],
            }
            local_path = local_agents_dir / "local-discover.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Discover agents
            _discover_agents()

            # Get available agents
            agents = get_available_agents()

            # Should have both
            assert "global-discover" in agents
            assert "local-discover" in agents

    def test_local_agent_with_pinned_model(self, monkeypatch):
        """Test local agent with pinned model configuration."""
        with (
            tempfile.TemporaryDirectory() as global_dir,
            tempfile.TemporaryDirectory() as local_dir,
        ):
            # Mock directories
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: global_dir
            )
            monkeypatch.setattr("os.getcwd", lambda: local_dir)

            # Create local agent with pinned model
            local_agents_dir = Path(local_dir) / ".code_puppy" / "agents"
            local_agents_dir.mkdir(parents=True)

            local_config = {
                "name": "pinned-model-test",
                "description": "Test pinned model",
                "system_prompt": "Test prompt",
                "tools": ["list_files"],
                "model": "gpt-4o",  # Pinned model
            }
            local_path = local_agents_dir / "pinned-model-test.json"
            with open(local_path, "w") as f:
                json.dump(local_config, f)

            # Load the agent
            agent = load_agent("pinned-model-test")

            # Verify pinned model
            assert agent.get_model_name() == "gpt-4o"

    def test_local_agent_directory_relative_to_cwd(self, monkeypatch):
        """Test that local agents are discovered relative to CWD."""
        with (
            tempfile.TemporaryDirectory() as dir1,
            tempfile.TemporaryDirectory() as dir2,
        ):
            # Mock global directory
            monkeypatch.setattr(
                "code_puppy.config.get_user_agents_directory", lambda: "/nonexistent"
            )

            # Create agent in dir1
            local_agents_dir1 = Path(dir1) / ".code_puppy" / "agents"
            local_agents_dir1.mkdir(parents=True)

            config1 = {
                "name": "dir1-agent",
                "description": "Agent in dir1",
                "system_prompt": "Dir1",
                "tools": ["list_files"],
            }
            path1 = local_agents_dir1 / "dir1-agent.json"
            with open(path1, "w") as f:
                json.dump(config1, f)

            # Create agent in dir2
            local_agents_dir2 = Path(dir2) / ".code_puppy" / "agents"
            local_agents_dir2.mkdir(parents=True)

            config2 = {
                "name": "dir2-agent",
                "description": "Agent in dir2",
                "system_prompt": "Dir2",
                "tools": ["read_file"],
            }
            path2 = local_agents_dir2 / "dir2-agent.json"
            with open(path2, "w") as f:
                json.dump(config2, f)

            # Test from dir1
            monkeypatch.setattr("os.getcwd", lambda: dir1)
            agents1 = get_available_agents()
            assert "dir1-agent" in agents1
            assert "dir2-agent" not in agents1

            # Test from dir2
            monkeypatch.setattr("os.getcwd", lambda: dir2)
            agents2 = get_available_agents()
            assert "dir2-agent" in agents2
            assert "dir1-agent" not in agents2
