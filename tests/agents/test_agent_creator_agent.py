"""Tests for AgentCreatorAgent functionality."""

from unittest.mock import patch

from code_puppy.agents.agent_creator_agent import AgentCreatorAgent


class TestAgentCreatorAgent:
    """Test AgentCreatorAgent functionality."""

    def test_name_property(self):
        """Test that name property returns the expected value."""
        agent = AgentCreatorAgent()
        assert agent.name == "agent-creator"

    def test_display_name_property(self):
        """Test that display_name property returns the expected value."""
        agent = AgentCreatorAgent()
        assert agent.display_name == "Agent Creator 🏗️"

    def test_description_property(self):
        """Test that description property returns the expected value."""
        agent = AgentCreatorAgent()
        expected = "Helps you create new JSON agent configurations with proper schema validation"
        assert agent.description == expected

    def test_get_system_prompt_injects_tools_list(self, monkeypatch):
        """Test that get_system_prompt() injects the tools list from get_available_tool_names()."""
        # Mock the tools function
        mock_tools = ["tool1", "tool2", "tool3"]
        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            lambda: mock_tools,
        )

        # Mock other dependencies
        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            lambda: "/mock/agents/dir",
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.ModelFactory.load_config", lambda: {}
        )

        agent = AgentCreatorAgent()
        prompt = agent.get_system_prompt()

        # Verify each tool is mentioned in the prompt
        for tool in mock_tools:
            assert f"**{tool}**" in prompt

        # Verify the tools are in the ALL AVAILABLE TOOLS section
        all_tools_section = "## ALL AVAILABLE TOOLS:\n" + ", ".join(
            f"- **{tool}**" for tool in mock_tools
        )
        assert all_tools_section in prompt

    def test_get_system_prompt_injects_agents_directory(self, monkeypatch):
        """Test that get_system_prompt() injects the agents directory path."""
        mock_dir = "/custom/user/agents"

        # Mock all dependencies
        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            lambda: ["tool1"],
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            lambda: mock_dir,
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.ModelFactory.load_config", lambda: {}
        )

        agent = AgentCreatorAgent()
        prompt = agent.get_system_prompt()

        # Verify the agents directory is mentioned in file creation section
        assert f"Save to the agents directory: `{mock_dir}`" in prompt

    def test_get_system_prompt_injects_model_inventory(self, monkeypatch):
        """Test that get_system_prompt() injects model inventory from ModelFactory.load_config()."""
        mock_models_config = {
            "gpt-5": {"type": "OpenAI", "context_length": "128k"},
            "claude-4": {"type": "Anthropic", "context_length": "200k"},
            "gemini-pro": {"type": "Google", "context_length": "32k"},
        }

        # Mock all dependencies
        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            lambda: ["tool1"],
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            lambda: "/mock/agents/dir",
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.ModelFactory.load_config",
            lambda: mock_models_config,
        )

        agent = AgentCreatorAgent()
        prompt = agent.get_system_prompt()

        # Verify each model is mentioned in the prompt
        for model_name, model_info in mock_models_config.items():
            model_type = model_info.get("type", "Unknown")
            context_length = model_info.get("context_length", "Unknown")
            expected_model_line = (
                f"- **{model_name}**: {model_type} model with {context_length} context"
            )
            assert expected_model_line in prompt

        # Verify the models are in the ALL AVAILABLE MODELS section
        assert "## ALL AVAILABLE MODELS:" in prompt

    def test_get_system_prompt_comprehensive_injection(self, monkeypatch):
        """Test that get_system_prompt() correctly injects all dynamic content."""
        mock_tools = ["list_files", "read_file", "edit_file", "invoke_agent"]
        mock_agents_dir = "/home/user/.code_puppy/agents"
        mock_models_config = {
            "gpt-5": {"type": "OpenAI", "context_length": "128k"},
            "claude-4-sonnet": {"type": "Anthropic", "context_length": "200k"},
        }

        # Mock all dependencies
        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_available_tool_names",
            lambda: mock_tools,
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.get_user_agents_directory",
            lambda: mock_agents_dir,
        )

        monkeypatch.setattr(
            "code_puppy.agents.agent_creator_agent.ModelFactory.load_config",
            lambda: mock_models_config,
        )

        agent = AgentCreatorAgent()
        prompt = agent.get_system_prompt()

        # Verify tools are injected
        for tool in mock_tools:
            assert f"**{tool}**" in prompt

        # Verify agents directory is injected
        assert f"Save to the agents directory: `{mock_agents_dir}`" in prompt

        # Verify models are injected
        for model_name, model_info in mock_models_config.items():
            model_type = model_info.get("type", "Unknown")
            context_length = model_info.get("context_length", "Unknown")
            expected_model_line = (
                f"- **{model_name}**: {model_type} model with {context_length} context"
            )
            assert expected_model_line in prompt

        # Verify key sections are present
        assert "## ALL AVAILABLE TOOLS:" in prompt
        assert "## ALL AVAILABLE MODELS:" in prompt
        assert "You are the Agent Creator! 🏗️" in prompt

    def test_get_available_tools_with_uc_enabled(self):
        """Test that get_available_tools includes UC when enabled."""
        with patch(
            "code_puppy.config.get_universal_constructor_enabled",
            return_value=True,
        ):
            agent = AgentCreatorAgent()
            expected_tools = [
                "list_files",
                "read_file",
                "edit_file",
                "agent_share_your_reasoning",
                "ask_user_question",
                "list_agents",
                "invoke_agent",
                "universal_constructor",
            ]
            assert agent.get_available_tools() == expected_tools

    def test_get_available_tools_with_uc_disabled(self):
        """Test that get_available_tools excludes UC when disabled."""
        with patch(
            "code_puppy.config.get_universal_constructor_enabled",
            return_value=False,
        ):
            agent = AgentCreatorAgent()
            expected_tools = [
                "list_files",
                "read_file",
                "edit_file",
                "agent_share_your_reasoning",
                "ask_user_question",
                "list_agents",
                "invoke_agent",
            ]
            assert agent.get_available_tools() == expected_tools

    def test_get_user_prompt(self):
        """Test that get_user_prompt returns the expected greeting."""
        agent = AgentCreatorAgent()
        expected = "Hi! I'm the Agent Creator 🏗️ Let's build an awesome agent together!"
        assert agent.get_user_prompt() == expected
