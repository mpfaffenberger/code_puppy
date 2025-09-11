"""Tests for agent tools functionality."""

from unittest.mock import MagicMock

from code_puppy.tools.agent_tools import register_invoke_agent, register_list_agents


class TestAgentTools:
    """Test suite for agent tools."""

    def test_list_agents_tool(self):
        """Test that list_agents tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_list_agents(mock_agent)

    def test_invoke_agent_tool(self):
        """Test that invoke_agent tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_invoke_agent(mock_agent)
