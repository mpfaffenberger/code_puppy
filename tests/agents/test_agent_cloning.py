"""Tests for agent cloning functionality."""

import json

from code_puppy.agents.agent_manager import clone_agent


class TestAgentCloneProjectDirectory:
    """Tests for cloning agents to project directories."""

    def test_clone_to_project_directory(self, tmp_path, monkeypatch):
        """Test cloning an agent to the project directory."""
        # Setup project structure
        project_agents_dir = tmp_path / ".code_puppy" / "agents"
        project_agents_dir.mkdir(parents=True)

        # Create a source agent JSON file
        user_agents_dir = tmp_path / "user_agents"
        user_agents_dir.mkdir()
        source_agent_path = user_agents_dir / "source-agent.json"
        source_config = {
            "name": "source-agent",
            "description": "Source agent for cloning",
            "system_prompt": "Test prompt",
            "tools": ["read_file"],
        }
        with open(source_agent_path, "w") as f:
            json.dump(source_config, f)

        # Mock config functions in the config module
        monkeypatch.setattr(
            "code_puppy.config.get_project_agents_directory",
            lambda: str(project_agents_dir),
        )
        monkeypatch.setattr(
            "code_puppy.config.get_user_agents_directory", lambda: str(user_agents_dir)
        )

        # Mock _ask_clone_location to return project directory
        monkeypatch.setattr(
            "code_puppy.agents.agent_manager._ask_clone_location",
            lambda: project_agents_dir,
        )

        # Mock agent registry
        from code_puppy.agents.agent_manager import _AGENT_REGISTRY

        _AGENT_REGISTRY.clear()
        _AGENT_REGISTRY["source-agent"] = str(source_agent_path)

        # Mock get_available_tool_names from tools module
        monkeypatch.setattr(
            "code_puppy.tools.get_available_tool_names",
            lambda: ["read_file", "edit_file"],
        )

        # Test clone
        clone_name = clone_agent("source-agent")

        # Verify clone created in project directory
        assert clone_name is not None
        assert clone_name == "source-agent-clone-1"
        clone_path = project_agents_dir / f"{clone_name}.json"
        assert clone_path.exists()

        # Verify clone config
        with open(clone_path) as f:
            clone_config = json.load(f)
        assert clone_config["name"] == clone_name
        assert clone_config["description"] == source_config["description"]

    def test_clone_to_user_directory(self, tmp_path, monkeypatch):
        """Test cloning an agent to the user directory."""
        # Setup directories
        user_agents_dir = tmp_path / "user_agents"
        user_agents_dir.mkdir()

        # Create a source agent JSON file
        source_agent_path = user_agents_dir / "source-agent.json"
        source_config = {
            "name": "source-agent",
            "description": "Source agent",
            "system_prompt": "Test",
            "tools": ["read_file"],
        }
        with open(source_agent_path, "w") as f:
            json.dump(source_config, f)

        # Mock config functions in the config module
        monkeypatch.setattr(
            "code_puppy.config.get_project_agents_directory", lambda: None
        )
        monkeypatch.setattr(
            "code_puppy.config.get_user_agents_directory", lambda: str(user_agents_dir)
        )

        # Mock _ask_clone_location to return user directory
        monkeypatch.setattr(
            "code_puppy.agents.agent_manager._ask_clone_location",
            lambda: user_agents_dir,
        )

        # Mock agent registry
        from code_puppy.agents.agent_manager import _AGENT_REGISTRY

        _AGENT_REGISTRY.clear()
        _AGENT_REGISTRY["source-agent"] = str(source_agent_path)

        # Mock get_available_tool_names from tools module
        monkeypatch.setattr(
            "code_puppy.tools.get_available_tool_names",
            lambda: ["read_file", "edit_file"],
        )

        # Test clone
        clone_name = clone_agent("source-agent")

        # Verify clone created in user directory
        assert clone_name is not None
        clone_path = user_agents_dir / f"{clone_name}.json"
        assert clone_path.exists()

    def test_clone_user_cancels_location(self, tmp_path, monkeypatch):
        """Test handling when user cancels clone location selection."""
        # Setup
        user_agents_dir = tmp_path / "user_agents"
        user_agents_dir.mkdir()

        # Create a source agent
        source_agent_path = user_agents_dir / "source-agent.json"
        source_config = {
            "name": "source-agent",
            "description": "Source",
            "system_prompt": "Test",
            "tools": [],
        }
        with open(source_agent_path, "w") as f:
            json.dump(source_config, f)

        # Mock agent registry
        from code_puppy.agents.agent_manager import _AGENT_REGISTRY

        _AGENT_REGISTRY.clear()
        _AGENT_REGISTRY["source-agent"] = str(source_agent_path)

        # Disable project agent discovery to avoid non-deterministic CWD reads
        monkeypatch.setattr(
            "code_puppy.config.get_project_agents_directory", lambda: None
        )

        # Mock: User cancels
        monkeypatch.setattr(
            "code_puppy.agents.agent_manager._ask_clone_location", lambda: None
        )

        # Test
        clone_name = clone_agent("source-agent")

        # Verify clone was cancelled
        assert clone_name is None

    def test_clone_nonexistent_agent(self, monkeypatch):
        """Test cloning a non-existent agent."""
        # Mock empty registry
        from code_puppy.agents.agent_manager import _AGENT_REGISTRY

        _AGENT_REGISTRY.clear()

        # Mock _ask_clone_location (shouldn't be called)
        monkeypatch.setattr(
            "code_puppy.agents.agent_manager._ask_clone_location", lambda: None
        )

        # Test
        clone_name = clone_agent("nonexistent-agent")

        # Verify
        assert clone_name is None
