"""Tests for agent switching functionality."""

import pytest
from unittest.mock import patch, MagicMock

from code_puppy.agents import (
    get_available_agents,
    get_current_agent_config,
    set_current_agent,
    load_agent_config,
    clear_agent_cache,
)
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.agents.code_puppy_agent import CodePuppyAgent


class TestAgentDiscovery:
    """Test agent discovery and registration."""
    
    def test_get_available_agents(self):
        """Test that available agents are discovered correctly."""
        agents = get_available_agents()
        
        # Should contain our default agent
        assert "code-puppy" in agents
        
        # Check display names
        assert "🐶" in agents["code-puppy"]
    
    def test_load_agent_config(self):
        """Test loading specific agent configurations."""
        # Test loading Code-Puppy agent
        code_puppy = load_agent_config("code-puppy")
        assert isinstance(code_puppy, CodePuppyAgent)
        assert code_puppy.name == "code-puppy"
        assert "🐶" in code_puppy.display_name
    
    def test_load_invalid_agent(self):
        """Test loading an invalid agent raises appropriate error."""
        with pytest.raises(ValueError, match="Agent 'nonexistent' not found"):
            load_agent_config("nonexistent")


class TestAgentSwitching:
    """Test agent switching functionality."""
    
    def test_get_current_agent_config_default(self):
        """Test getting current agent config returns default."""
        # Clear any cached state
        clear_agent_cache()
        
        # Should return default agent (code-puppy)
        agent = get_current_agent_config()
        assert agent.name == "code-puppy"
        assert isinstance(agent, CodePuppyAgent)
    
    @patch('code_puppy.config.set_config_value')
    def test_set_current_agent_valid(self, mock_set_config):
        """Test setting current agent to a valid agent."""
        result = set_current_agent("code-puppy")
        
        assert result is True
        mock_set_config.assert_called_once_with("current_agent", "code-puppy")
    
    def test_set_current_agent_invalid(self):
        """Test setting current agent to an invalid agent."""
        result = set_current_agent("nonexistent")
        
        assert result is False
    
    @patch('code_puppy.config.get_value')
    def test_get_current_agent_config_cached(self, mock_get_value):
        """Test that agent config is cached properly."""
        mock_get_value.return_value = "code-puppy"
        
        # First call should load agent
        agent1 = get_current_agent_config()
        
        # Second call should return cached agent
        agent2 = get_current_agent_config()
        
        assert agent1 is agent2  # Same instance due to caching
        assert agent1.name == "code-puppy"


class TestBaseAgent:
    """Test base agent functionality."""
    
    def test_base_agent_interface(self):
        """Test that CodePuppyAgent implements BaseAgent interface correctly."""
        agent = CodePuppyAgent()
        
        # Test required properties
        assert hasattr(agent, 'name')
        assert hasattr(agent, 'display_name')
        assert hasattr(agent, 'description')
        
        # Test required methods
        assert callable(agent.get_system_prompt)
        assert callable(agent.get_available_tools)
        
        # Test actual values
        assert agent.name == "code-puppy"
        assert "🐶" in agent.display_name
        assert len(agent.description) > 0
        assert len(agent.get_system_prompt()) > 0
        assert isinstance(agent.get_available_tools(), list)
        assert len(agent.get_available_tools()) > 0
    
    def test_code_puppy_agent_tools(self):
        """Test that CodePuppyAgent specifies the expected tools."""
        agent = CodePuppyAgent()
        tools = agent.get_available_tools()
        
        # Check that all expected tools are present
        expected_tools = [
            "list_files",
            "read_file", 
            "grep",
            "edit_file",
            "delete_file",
            "agent_run_shell_command",
            "agent_share_your_reasoning"
        ]
        
        for tool in expected_tools:
            assert tool in tools, f"Tool {tool} should be available to CodePuppyAgent"
        
        # Ensure no extra tools
        assert len(tools) == len(expected_tools), f"Expected {len(expected_tools)} tools, got {len(tools)}"
    
    def test_json_agent_integration(self):
        """Test that JSON agents integrate properly with the agent system."""
        from code_puppy.agents import get_available_agents, clear_agent_cache
        
        # Clear cache to ensure fresh discovery
        clear_agent_cache()
        
        # Get available agents
        agents = get_available_agents()
        
        # Should include both Python and JSON agents
        assert 'code-puppy' in agents  # Python agent
        # Note: We can't guarantee JSON agents in test environment
        # since they depend on user directory, but the system should work
        
        assert isinstance(agents, dict)
        assert len(agents) >= 1  # At least code-puppy should be available
    
    def test_system_prompt_includes_config(self):
        """Test that system prompt includes config values."""
        with patch('code_puppy.agents.code_puppy_agent.get_puppy_name', return_value='TestPuppy'):
            with patch('code_puppy.agents.code_puppy_agent.get_owner_name', return_value='TestOwner'):
                agent = CodePuppyAgent()
                prompt = agent.get_system_prompt()
                
                assert 'TestPuppy' in prompt
                assert 'TestOwner' in prompt
