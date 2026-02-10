"""Integration tests for project-level agent discovery using real filesystem."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents.json_agent import discover_json_agents


class TestProjectAgentIntegration:
    """Integration tests that use real CWD changes instead of mocking."""

    def test_discover_project_agent_via_cwd(self, tmp_path):
        """Test that changing to a directory with .code_puppy discovers agents."""
        # Create project structure: project/.code_puppy/agents/
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        agents_dir = project_dir / ".code_puppy" / "agents"
        agents_dir.mkdir(parents=True)

        # Create agent file
        agent_config = {
            "name": "project-agent",
            "description": "A project-level agent",
            "system_prompt": "I'm project-specific",
            "tools": ["list_files"],
        }
        agent_file = agents_dir / "project-agent.json"
        agent_file.write_text(json.dumps(agent_config))

        # Mock user directory to be empty
        empty_user_dir = tmp_path / "empty_user"
        empty_user_dir.mkdir()

        original_cwd = os.getcwd()
        try:
            # Change to project directory
            os.chdir(str(project_dir))

            with patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(empty_user_dir),
            ):
                agents = discover_json_agents()

            # Should discover the project agent
            assert "project-agent" in agents
            assert agents["project-agent"] == str(agent_file)
        finally:
            os.chdir(original_cwd)

    def test_no_project_agent_when_outside_project(self, tmp_path):
        """Test that project agents are NOT discovered when outside project dir."""
        # Create project with agent
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        agents_dir = project_dir / ".code_puppy" / "agents"
        agents_dir.mkdir(parents=True)

        agent_config = {
            "name": "project-agent",
            "description": "Should not be found",
            "system_prompt": "I'm project-specific",
            "tools": ["list_files"],
        }
        agent_file = agents_dir / "project-agent.json"
        agent_file.write_text(json.dumps(agent_config))

        # Create different directory without .code_puppy
        other_dir = tmp_path / "otherdir"
        other_dir.mkdir()

        empty_user_dir = tmp_path / "empty_user"
        empty_user_dir.mkdir()

        original_cwd = os.getcwd()
        try:
            # Change to OTHER directory (not project)
            os.chdir(str(other_dir))

            with patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(empty_user_dir),
            ):
                agents = discover_json_agents()

            # Should NOT find the project agent
            assert "project-agent" not in agents
        finally:
            os.chdir(original_cwd)

    def test_project_agent_overrides_user_agent_via_cwd(self, tmp_path):
        """Test that project agent overrides user agent with same name."""
        # Create project with agent
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        project_agents_dir = project_dir / ".code_puppy" / "agents"
        project_agents_dir.mkdir(parents=True)

        project_config = {
            "name": "shared-name",
            "description": "Project version",
            "system_prompt": "I'm from the project",
            "tools": ["list_files"],
        }
        project_file = project_agents_dir / "shared-name.json"
        project_file.write_text(json.dumps(project_config))

        # Create user agent with same name
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        user_config = {
            "name": "shared-name",
            "description": "User version",
            "system_prompt": "I'm from user config",
            "tools": ["read_file"],
        }
        user_file = user_dir / "shared-name.json"
        user_file.write_text(json.dumps(user_config))

        original_cwd = os.getcwd()
        try:
            # Change to project directory
            os.chdir(str(project_dir))

            with patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ):
                agents = discover_json_agents()

            # Should have project version (not user version)
            assert "shared-name" in agents
            assert agents["shared-name"] == str(project_file)
        finally:
            os.chdir(original_cwd)

    def test_nested_project_discovery(self, tmp_path):
        """Test that .code_puppy is found from nested subdirectories."""
        # Create project/.code_puppy/agents/
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        agents_dir = project_dir / ".code_puppy" / "agents"
        agents_dir.mkdir(parents=True)

        agent_config = {
            "name": "nested-agent",
            "description": "Found from subdir",
            "system_prompt": "Test",
            "tools": ["list_files"],
        }
        agent_file = agents_dir / "nested-agent.json"
        agent_file.write_text(json.dumps(agent_config))

        # Create nested subdirectory
        nested_dir = project_dir / "src" / "components"
        nested_dir.mkdir(parents=True)

        empty_user_dir = tmp_path / "empty_user"
        empty_user_dir.mkdir()

        original_cwd = os.getcwd()
        try:
            # Change to NESTED directory (not root)
            os.chdir(str(nested_dir))

            with patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(empty_user_dir),
            ):
                agents = discover_json_agents()

            # NOTE: Current implementation uses os.getcwd(), so it should NOT find
            # the agent from nested directories (would need to walk up to find .code_puppy)
            # This test documents current behavior - may need updating if we add
            # parent directory searching later
            assert "nested-agent" not in agents
        finally:
            os.chdir(original_cwd)
