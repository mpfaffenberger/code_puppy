import json
from unittest.mock import patch

import pytest

from code_puppy.agents.json_agent import JSONAgent, discover_json_agents


class TestJsonAgentExtended:
    """Extended tests for JsonAgent class."""

    def test_load_valid_json_config(self, tmp_path):
        """Test loading a valid JSON configuration."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files", "read_file"],
        }

        agent_file = tmp_path / "test_agent.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))

        assert agent.name == "test_agent"
        assert agent.description == "A test agent"
        assert agent.get_system_prompt() == "You are a test agent"
        assert agent.get_available_tools() == ["list_files", "read_file"]

    def test_load_json_with_display_name(self, tmp_path):
        """Test loading JSON with custom display name."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "display_name": "Custom Test Bot",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "test_agent.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.display_name == "Custom Test Bot"

    def test_display_name_fallback(self, tmp_path):
        """Test display name fallback to name with emoji."""
        config = {
            "name": "test_bot",
            "description": "A test bot",
            "system_prompt": "You are a test bot",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "test_bot.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.display_name == "Test_Bot 🤖"

    def test_load_invalid_json_syntax(self, tmp_path):
        """Test loading invalid JSON syntax raises error."""
        agent_file = tmp_path / "invalid.json"
        agent_file.write_text('{"name": "test", invalid}')

        with pytest.raises(ValueError, match="Failed to load JSON agent config"):
            JSONAgent(str(agent_file))

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file raises error."""
        with pytest.raises(ValueError, match="Failed to load JSON agent config"):
            JSONAgent("/nonexistent/path/agent.json")

    def test_validate_missing_required_fields(self, tmp_path):
        """Test validation fails when required fields are missing."""
        # Missing name
        config1 = {
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file1 = tmp_path / "missing_name.json"
        agent_file1.write_text(json.dumps(config1))

        with pytest.raises(ValueError, match="Missing required field 'name'"):
            JSONAgent(str(agent_file1))

        # Missing description
        config2 = {
            "name": "test_agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file2 = tmp_path / "missing_description.json"
        agent_file2.write_text(json.dumps(config2))

        with pytest.raises(ValueError, match="Missing required field 'description'"):
            JSONAgent(str(agent_file2))

        # Missing system_prompt
        config3 = {
            "name": "test_agent",
            "description": "A test agent",
            "tools": ["list_files"],
        }

        agent_file3 = tmp_path / "missing_prompt.json"
        agent_file3.write_text(json.dumps(config3))

        with pytest.raises(ValueError, match="Missing required field 'system_prompt'"):
            JSONAgent(str(agent_file3))

        # Missing tools
        config4 = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
        }

        agent_file4 = tmp_path / "missing_tools.json"
        agent_file4.write_text(json.dumps(config4))

        with pytest.raises(ValueError, match="Missing required field 'tools'"):
            JSONAgent(str(agent_file4))

    def test_validate_invalid_tools_type(self, tmp_path):
        """Test validation fails when tools is not a list."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": "not_a_list",
        }

        agent_file = tmp_path / "invalid_tools.json"
        agent_file.write_text(json.dumps(config))

        with pytest.raises(ValueError, match="'tools' must be a list"):
            JSONAgent(str(agent_file))

    def test_validate_invalid_system_prompt_type(self, tmp_path):
        """Test validation fails when system_prompt is not string or list."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": 123,
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "invalid_prompt.json"
        agent_file.write_text(json.dumps(config))

        with pytest.raises(
            ValueError, match="'system_prompt' must be a string or list"
        ):
            JSONAgent(str(agent_file))

    def test_get_system_prompt_string(self, tmp_path):
        """Test getting system prompt as string."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a helpful assistant",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "string_prompt.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.get_system_prompt() == "You are a helpful assistant"

    def test_get_system_prompt_list(self, tmp_path):
        """Test getting system prompt as list joined with newlines."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": [
                "You are a helpful assistant.",
                "Be concise and accurate.",
                "Always provide code examples.",
            ],
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "list_prompt.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        expected = "You are a helpful assistant.\nBe concise and accurate.\nAlways provide code examples."
        assert agent.get_system_prompt() == expected

    def test_get_available_tools_filtering(self, tmp_path):
        """Test that get_available_tools filters out non-existent tools."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files", "nonexistent_tool", "read_file", "final_result"],
        }

        agent_file = tmp_path / "filter_tools.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        available_tools = agent.get_available_tools()

        # Should only include valid tools that exist in registry
        assert "list_files" in available_tools
        assert "read_file" in available_tools
        assert "nonexistent_tool" not in available_tools
        assert "final_result" not in available_tools

    def test_get_user_prompt(self, tmp_path):
        """Test getting custom user prompt."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
            "user_prompt": "Please help me with: {user_input}",
        }

        agent_file = tmp_path / "user_prompt.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.get_user_prompt() == "Please help me with: {user_input}"

    def test_get_user_prompt_none(self, tmp_path):
        """Test getting user prompt when not specified."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "no_user_prompt.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.get_user_prompt() is None

    def test_get_tools_config(self, tmp_path):
        """Test getting tools configuration."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
            "tools_config": {"list_files": {"recursive": True, "show_hidden": False}},
        }

        agent_file = tmp_path / "tools_config.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        tools_config = agent.get_tools_config()

        assert tools_config is not None
        assert "list_files" in tools_config
        assert tools_config["list_files"]["recursive"] is True
        assert tools_config["list_files"]["show_hidden"] is False

    def test_get_tools_config_none(self, tmp_path):
        """Test getting tools config when not specified."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "no_tools_config.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.get_tools_config() is None

    def test_refresh_config(self, tmp_path):
        """Test refreshing configuration from disk."""
        # Initial config
        config1 = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "refresh_test.json"
        agent_file.write_text(json.dumps(config1))

        agent = JSONAgent(str(agent_file))
        assert agent.description == "A test agent"

        # Update config on disk
        config2 = {
            "name": "test_agent",
            "description": "An updated test agent",
            "system_prompt": "You are an updated test agent",
            "tools": ["list_files", "read_file"],
        }

        agent_file.write_text(json.dumps(config2))

        # Refresh and verify changes
        agent.refresh_config()
        assert agent.description == "An updated test agent"
        assert agent.get_system_prompt() == "You are an updated test agent"
        assert agent.get_available_tools() == ["list_files", "read_file"]

    def test_get_model_name_specified(self, tmp_path):
        """Test getting model name when specified in config."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
            "model": "gpt-4-turbo",
        }

        agent_file = tmp_path / "model_specified.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        assert agent.get_model_name() == "gpt-4-turbo"

    def test_get_model_name_fallback(self, tmp_path):
        """Test getting model name falls back to base class when not specified."""
        config = {
            "name": "test_agent",
            "description": "A test agent",
            "system_prompt": "You are a test agent",
            "tools": ["list_files"],
        }

        agent_file = tmp_path / "no_model.json"
        agent_file.write_text(json.dumps(config))

        agent = JSONAgent(str(agent_file))
        # Should fall back to base class implementation
        model_name = agent.get_model_name()
        # We don't know what the default is, but it should not be None
        assert model_name is not None


class TestDiscoverJsonAgents:
    """Tests for discover_json_agents function."""

    def test_discover_valid_agents(self, tmp_path):
        """Test discovering valid JSON agents."""
        # Create valid agent files
        config1 = {
            "name": "agent1",
            "description": "First test agent",
            "system_prompt": "You are agent 1",
            "tools": ["list_files"],
        }

        config2 = {
            "name": "agent2",
            "description": "Second test agent",
            "system_prompt": "You are agent 2",
            "tools": ["read_file"],
        }

        agent1_file = tmp_path / "agent1.json"
        agent2_file = tmp_path / "agent2.json"

        agent1_file.write_text(json.dumps(config1))
        agent2_file.write_text(json.dumps(config2))

        # Mock the user agents directory to point to our tmp_path
        with patch("code_puppy.config.get_user_agents_directory") as mock_get_dir:
            mock_get_dir.return_value = str(tmp_path)

            agents = discover_json_agents()

            assert len(agents) == 2
            assert "agent1" in agents
            assert "agent2" in agents
            assert agents["agent1"] == str(agent1_file)
            assert agents["agent2"] == str(agent2_file)

    def test_discover_skip_invalid_agents(self, tmp_path):
        """Test that invalid agent files are skipped during discovery."""
        # Create valid agent
        valid_config = {
            "name": "valid_agent",
            "description": "A valid agent",
            "system_prompt": "You are valid",
            "tools": ["list_files"],
        }

        valid_file = tmp_path / "valid.json"
        valid_file.write_text(json.dumps(valid_config))

        # Create invalid agent files
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text('{"name": "test", invalid}')

        missing_fields = tmp_path / "missing.json"
        missing_fields.write_text('{"name": "incomplete"}')

        # Non-JSON file should be ignored
        not_json = tmp_path / "not_json.txt"
        not_json.write_text("Not a JSON file")

        with patch("code_puppy.config.get_user_agents_directory") as mock_get_dir:
            mock_get_dir.return_value = str(tmp_path)

            agents = discover_json_agents()

            # Should only include the valid agent
            assert len(agents) == 1
            assert "valid_agent" in agents
            assert agents["valid_agent"] == str(valid_file)

    def test_discover_no_agents_directory(self):
        """Test discovery when agents directory doesn't exist."""
        with patch("code_puppy.config.get_user_agents_directory") as mock_get_dir:
            mock_get_dir.return_value = "/nonexistent/directory"

            agents = discover_json_agents()
            assert agents == {}

    def test_discover_empty_directory(self, tmp_path):
        """Test discovery when agents directory is empty."""
        with patch("code_puppy.config.get_user_agents_directory") as mock_get_dir:
            mock_get_dir.return_value = str(tmp_path)

            agents = discover_json_agents()
            assert agents == {}

    def test_discover_duplicate_names(self, tmp_path):
        """Test discovery with duplicate agent names (last one wins)."""
        # Create two agents with same name
        config1 = {
            "name": "duplicate",
            "description": "First duplicate agent",
            "system_prompt": "You are first",
            "tools": ["list_files"],
        }

        config2 = {
            "name": "duplicate",
            "description": "Second duplicate agent",
            "system_prompt": "You are second",
            "tools": ["read_file"],
        }

        agent1_file = tmp_path / "agent1.json"
        agent2_file = tmp_path / "agent2.json"

        agent1_file.write_text(json.dumps(config1))
        agent2_file.write_text(json.dumps(config2))

        with patch("code_puppy.config.get_user_agents_directory") as mock_get_dir:
            mock_get_dir.return_value = str(tmp_path)

            agents = discover_json_agents()

            # Should only have one entry (last one processed wins)
            assert len(agents) == 1
            assert "duplicate" in agents
            # The path should be one of our files
            assert agents["duplicate"] in [str(agent1_file), str(agent2_file)]
