"""Full coverage tests for agents/agent_creator_agent.py."""

from unittest.mock import MagicMock, patch

from code_puppy.agents.agent_creator_agent import AgentCreatorAgent


class TestAgentCreatorAgent:
    def test_name(self):
        agent = AgentCreatorAgent()
        assert agent.name == "agent-creator"

    def test_display_name(self):
        agent = AgentCreatorAgent()
        assert "Agent Creator" in agent.display_name

    def test_description(self):
        agent = AgentCreatorAgent()
        assert "JSON" in agent.description

    def test_get_user_prompt(self):
        agent = AgentCreatorAgent()
        prompt = agent.get_user_prompt()
        assert "Agent Creator" in prompt

    def test_get_system_prompt(self):
        agent = AgentCreatorAgent()
        with (
            patch(
                "code_puppy.agents.agent_creator_agent.get_available_tool_names",
                return_value=["read_file"],
            ),
            patch(
                "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
                return_value="/tmp/agents",
            ),
            patch("code_puppy.agents.agent_creator_agent.ModelFactory") as mock_factory,
        ):
            mock_factory.load_config.return_value = {
                "gpt-4": {"type": "openai", "context_length": 128000}
            }
            prompt = agent.get_system_prompt()
            assert "read_file" in prompt
            assert "gpt-4" in prompt

    def test_get_system_prompt_with_uc_tools(self):
        agent = AgentCreatorAgent()
        mock_tool = MagicMock()
        mock_tool.full_name = "api.weather"
        mock_tool.meta.enabled = True
        mock_tool.meta.description = "Weather tool"

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = [mock_tool]

        with (
            patch(
                "code_puppy.agents.agent_creator_agent.get_available_tool_names",
                return_value=[],
            ),
            patch(
                "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
                return_value="/tmp",
            ),
            patch("code_puppy.agents.agent_creator_agent.ModelFactory") as mock_factory,
            patch(
                "code_puppy.plugins.universal_constructor.registry.get_registry",
                return_value=mock_registry,
            ),
        ):
            mock_factory.load_config.return_value = {}
            prompt = agent.get_system_prompt()
            assert "api.weather" in prompt

    def test_get_available_tools(self):
        agent = AgentCreatorAgent()
        with patch(
            "code_puppy.config.get_universal_constructor_enabled", return_value=True
        ):
            tools = agent.get_available_tools()
            assert "universal_constructor" in tools

    def test_get_available_tools_uc_disabled(self):
        agent = AgentCreatorAgent()
        with patch(
            "code_puppy.config.get_universal_constructor_enabled", return_value=False
        ):
            tools = agent.get_available_tools()
            assert "universal_constructor" not in tools

    def test_validate_agent_json_valid(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "test-agent",
            "description": "Test",
            "system_prompt": "Be helpful",
            "tools": [],
        }
        errors = agent.validate_agent_json(config)
        assert errors == []

    def test_validate_agent_json_missing_fields(self):
        agent = AgentCreatorAgent()
        errors = agent.validate_agent_json({})
        assert len(errors) == 4

    def test_validate_agent_json_bad_name(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "bad name",
            "description": "Test",
            "system_prompt": "ok",
            "tools": [],
        }
        errors = agent.validate_agent_json(config)
        assert any("spaces" in e for e in errors)

    def test_validate_agent_json_empty_name(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "",
            "description": "Test",
            "system_prompt": "ok",
            "tools": [],
        }
        errors = agent.validate_agent_json(config)
        assert any("non-empty" in e for e in errors)

    def test_validate_agent_json_bad_tools(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "test",
            "description": "Test",
            "system_prompt": "ok",
            "tools": "not-a-list",
        }
        errors = agent.validate_agent_json(config)
        assert any("list" in e for e in errors)

    def test_validate_agent_json_invalid_tools(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "test",
            "description": "Test",
            "system_prompt": "ok",
            "tools": ["nonexistent_tool_xyz"],
        }
        errors = agent.validate_agent_json(config)
        assert any("Invalid" in e for e in errors)

    def test_validate_agent_json_bad_system_prompt(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "test",
            "description": "Test",
            "system_prompt": 123,
            "tools": [],
        }
        errors = agent.validate_agent_json(config)
        assert any("string or list" in e for e in errors)

    def test_validate_agent_json_bad_list_prompt(self):
        agent = AgentCreatorAgent()
        config = {
            "name": "test",
            "description": "Test",
            "system_prompt": ["ok", 123],
            "tools": [],
        }
        errors = agent.validate_agent_json(config)
        assert any("strings" in e for e in errors)

    def test_get_agent_file_path(self):
        agent = AgentCreatorAgent()
        with patch(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            return_value="/tmp/agents",
        ):
            path = agent.get_agent_file_path("my-agent")
            assert path.endswith("my-agent.json")

    def test_create_agent_json_success(self, tmp_path):
        agent = AgentCreatorAgent()
        config = {
            "name": "test-agent",
            "description": "Test",
            "system_prompt": "ok",
            "tools": [],
        }
        with patch.object(
            agent, "get_agent_file_path", return_value=str(tmp_path / "test-agent.json")
        ):
            success, msg = agent.create_agent_json(config)
            assert success is True
            assert "Successfully" in msg

    def test_create_agent_json_already_exists(self, tmp_path):
        agent = AgentCreatorAgent()
        config = {
            "name": "test-agent",
            "description": "Test",
            "system_prompt": "ok",
            "tools": [],
        }
        existing = tmp_path / "test-agent.json"
        existing.write_text("{}")
        with patch.object(agent, "get_agent_file_path", return_value=str(existing)):
            success, msg = agent.create_agent_json(config)
            assert success is False
            assert "already exists" in msg

    def test_create_agent_json_validation_error(self):
        agent = AgentCreatorAgent()
        success, msg = agent.create_agent_json({})
        assert success is False
        assert "Validation" in msg

    def test_create_agent_json_write_error(self, tmp_path):
        agent = AgentCreatorAgent()
        config = {
            "name": "test-agent",
            "description": "Test",
            "system_prompt": "ok",
            "tools": [],
        }
        with patch.object(
            agent, "get_agent_file_path", return_value="/nonexistent/dir/test.json"
        ):
            success, msg = agent.create_agent_json(config)
            assert success is False
            assert "Failed" in msg
