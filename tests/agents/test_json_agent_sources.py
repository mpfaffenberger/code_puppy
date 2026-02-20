"""Unit tests for discover_json_agents_with_sources()."""

import json
from unittest.mock import patch

from code_puppy.agents.json_agent import discover_json_agents_with_sources


def _make_agent_file(directory, name, description="Test agent"):
    config = {
        "name": name,
        "description": description,
        "system_prompt": f"You are {name}",
        "tools": ["list_files"],
    }
    agent_file = directory / f"{name}.json"
    agent_file.write_text(json.dumps(config))
    return agent_file


class TestDiscoverJsonAgentsWithSources:
    """Tests for discover_json_agents_with_sources()."""

    def test_user_only_agent(self, tmp_path):
        """User-only agent has source='user' and shadowed_path=None."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        user_file = _make_agent_file(user_dir, "my-agent")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch("code_puppy.config.get_project_agents_directory", return_value=None),
        ):
            result = discover_json_agents_with_sources()

        assert "my-agent" in result
        info = result["my-agent"]
        assert info["path"] == str(user_file)
        assert info["source"] == "user"
        assert info["shadowed_path"] is None

    def test_project_only_agent(self, tmp_path):
        """Project-only agent has source='project' and shadowed_path=None."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()
        project_file = _make_agent_file(project_dir, "team-agent")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert "team-agent" in result
        info = result["team-agent"]
        assert info["path"] == str(project_file)
        assert info["source"] == "project"
        assert info["shadowed_path"] is None

    def test_project_overrides_user(self, tmp_path):
        """When a project agent shadows a user agent, source='project' and shadowed_path points to user file."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()

        user_file = _make_agent_file(user_dir, "shared-agent", "User version")
        project_file = _make_agent_file(project_dir, "shared-agent", "Project version")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert "shared-agent" in result
        info = result["shared-agent"]
        assert info["path"] == str(project_file)
        assert info["source"] == "project"
        assert info["shadowed_path"] == str(user_file)

    def test_both_directories_no_collision(self, tmp_path):
        """Agents from both directories are merged; non-colliding agents keep their source."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()

        user_file = _make_agent_file(user_dir, "user-only")
        project_file = _make_agent_file(project_dir, "project-only")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert len(result) == 2
        assert result["user-only"]["source"] == "user"
        assert result["user-only"]["path"] == str(user_file)
        assert result["user-only"]["shadowed_path"] is None
        assert result["project-only"]["source"] == "project"
        assert result["project-only"]["path"] == str(project_file)
        assert result["project-only"]["shadowed_path"] is None

    def test_invalid_user_agent_skipped(self, tmp_path):
        """Invalid JSON files in the user directory are skipped gracefully."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()

        valid_file = _make_agent_file(user_dir, "valid-agent")
        (user_dir / "bad-syntax.json").write_text("{invalid json}")
        (user_dir / "missing-fields.json").write_text('{"name": "incomplete"}')

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch("code_puppy.config.get_project_agents_directory", return_value=None),
        ):
            result = discover_json_agents_with_sources()

        assert len(result) == 1
        assert "valid-agent" in result
        assert result["valid-agent"]["path"] == str(valid_file)

    def test_invalid_project_agent_skipped(self, tmp_path):
        """Invalid JSON files in the project directory are skipped gracefully."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()

        _make_agent_file(project_dir, "valid-proj")
        (project_dir / "bad.json").write_text("{not valid}")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert len(result) == 1
        assert "valid-proj" in result
        assert result["valid-proj"]["source"] == "project"

    def test_empty_directories(self, tmp_path):
        """Empty user and project directories return an empty dict."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert result == {}

    def test_no_project_directory(self, tmp_path):
        """When get_project_agents_directory returns None, only user agents are returned."""
        user_dir = tmp_path / "user_agents"
        user_dir.mkdir()
        user_file = _make_agent_file(user_dir, "user-agent")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value=str(user_dir),
            ),
            patch("code_puppy.config.get_project_agents_directory", return_value=None),
        ):
            result = discover_json_agents_with_sources()

        assert list(result.keys()) == ["user-agent"]
        assert result["user-agent"]["source"] == "user"
        assert result["user-agent"]["path"] == str(user_file)

    def test_nonexistent_user_directory(self, tmp_path):
        """When the user agents directory doesn't exist, return only project agents."""
        project_dir = tmp_path / "project_agents"
        project_dir.mkdir()
        _make_agent_file(project_dir, "proj-agent")

        with (
            patch(
                "code_puppy.config.get_user_agents_directory",
                return_value="/nonexistent/path",
            ),
            patch(
                "code_puppy.config.get_project_agents_directory",
                return_value=str(project_dir),
            ),
        ):
            result = discover_json_agents_with_sources()

        assert list(result.keys()) == ["proj-agent"]
        assert result["proj-agent"]["source"] == "project"
        assert result["proj-agent"]["shadowed_path"] is None
