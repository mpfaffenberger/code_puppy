"""Tests for agent-specific model pinning functionality."""



from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.config import (
    clear_agent_pinned_model,
    get_agent_pinned_model,
    set_agent_pinned_model,
)


class TestAgentPinnedModels:
    """Test agent-specific model pinning."""

    def test_set_and_get_agent_pinned_model(self):
        """Test setting and getting pinned models for agents."""
        agent_name = "test-agent"
        model_name = "gpt-4o"

        # Set pinned model
        set_agent_pinned_model(agent_name, model_name)

        # Get pinned model
        result = get_agent_pinned_model(agent_name)
        assert result == model_name

        # Clean up
        clear_agent_pinned_model(agent_name)
        result = get_agent_pinned_model(agent_name)
        assert result == "" or result is None

    def test_clear_agent_pinned_model(self):
        """Test clearing pinned models for agents."""
        agent_name = "test-agent-clear"
        model_name = "claude-3-5-sonnet"

        # Set and verify
        set_agent_pinned_model(agent_name, model_name)
        assert get_agent_pinned_model(agent_name) == model_name

        # Clear and verify
        clear_agent_pinned_model(agent_name)
        result = get_agent_pinned_model(agent_name)
        assert result == "" or result is None

    def test_base_agent_get_model_name(self):
        """Test BaseAgent.get_model_name() returns pinned model."""
        agent = CodePuppyAgent()
        agent_name = agent.name  # "code-puppy"
        model_name = "gpt-4o-mini"

        # Initially no pinned model
        result = agent.get_model_name()
        assert result == "" or result is None

        # Set pinned model
        set_agent_pinned_model(agent_name, model_name)

        # Should return pinned model
        result = agent.get_model_name()
        assert result == model_name

        # Clean up
        clear_agent_pinned_model(agent_name)

    def test_different_agents_different_models(self):
        """Test that different agents can have different pinned models."""
        agent1_name = "agent-one"
        agent1_model = "gpt-4o"
        agent2_name = "agent-two"
        agent2_model = "claude-3-5-sonnet"

        # Set different models for different agents
        set_agent_pinned_model(agent1_name, agent1_model)
        set_agent_pinned_model(agent2_name, agent2_model)

        # Verify each agent has its own model
        assert get_agent_pinned_model(agent1_name) == agent1_model
        assert get_agent_pinned_model(agent2_name) == agent2_model

        # Clean up
        clear_agent_pinned_model(agent1_name)
        clear_agent_pinned_model(agent2_name)
