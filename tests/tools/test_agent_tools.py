"""Unit tests for code_puppy.tools.agent_tools - focused on reaching 50% coverage.

Tests the data models and simpler functionality.
"""
import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.agent_tools import (
    register_list_agents,
    register_invoke_agent,
    AgentInfo,
    ListAgentsOutput,
    AgentInvokeOutput,
)


class TestAgentInfo:
    """Test AgentInfo Pydantic model."""
    
    def test_agent_info_creation(self):
        """Test AgentInfo can be created with required fields."""
        agent_info = AgentInfo(name="test_agent", display_name="Test Agent")
        
        assert agent_info.name == "test_agent"
        assert agent_info.display_name == "Test Agent"
    
    def test_agent_info_dict(self):
        """Test AgentInfo can be converted to dict."""
        agent_info = AgentInfo(name="agent1", display_name="Agent One")
        data = agent_info.model_dump()
        
        assert data["name"] == "agent1"
        assert data["display_name"] == "Agent One"


class TestListAgentsOutput:
    """Test ListAgentsOutput Pydantic model."""
    
    def test_list_agents_output_success(self):
        """Test ListAgentsOutput with successful response."""
        agents = [
            AgentInfo(name="agent1", display_name="Agent 1"),
            AgentInfo(name="agent2", display_name="Agent 2")
        ]
        output = ListAgentsOutput(agents=agents)
        
        assert len(output.agents) == 2
        assert output.error is None
        assert output.agents[0].name == "agent1"
    
    def test_list_agents_output_with_error(self):
        """Test ListAgentsOutput with error."""
        output = ListAgentsOutput(agents=[], error="Test error")
        
        assert len(output.agents) == 0
        assert output.error == "Test error"
    
    def test_list_agents_output_empty(self):
        """Test ListAgentsOutput with empty agents list."""
        output = ListAgentsOutput(agents=[])
        
        assert len(output.agents) == 0
        assert output.error is None
    
    def test_list_agents_output_dict(self):
        """Test ListAgentsOutput can be converted to dict."""
        agents = [AgentInfo(name="a1", display_name="A1")]
        output = ListAgentsOutput(agents=agents)
        data = output.model_dump()
        
        assert "agents" in data
        assert len(data["agents"]) == 1


class TestAgentInvokeOutput:
    """Test AgentInvokeOutput Pydantic model."""
    
    def test_agent_invoke_output_success(self):
        """Test AgentInvokeOutput with successful response."""
        output = AgentInvokeOutput(
            response="Test response",
            agent_name="test_agent"
        )
        
        assert output.response == "Test response"
        assert output.agent_name == "test_agent"
        assert output.error is None
    
    def test_agent_invoke_output_with_error(self):
        """Test AgentInvokeOutput with error."""
        output = AgentInvokeOutput(
            response=None,
            agent_name="test_agent",
            error="Invocation failed"
        )
        
        assert output.response is None
        assert output.agent_name == "test_agent"
        assert output.error == "Invocation failed"
    
    def test_agent_invoke_output_both_response_and_error(self):
        """Test AgentInvokeOutput with both response and error."""
        output = AgentInvokeOutput(
            response="Partial response",
            agent_name="agent",
            error="Warning message"
        )
        
        assert output.response == "Partial response"
        assert output.error == "Warning message"
    
    def test_agent_invoke_output_dict(self):
        """Test AgentInvokeOutput can be converted to dict."""
        output = AgentInvokeOutput(
            response="Response",
            agent_name="agent1"
        )
        data = output.model_dump()
        
        assert data["response"] == "Response"
        assert data["agent_name"] == "agent1"


class TestRegisterFunctions:
    """Test register functions return callable."""
    
    def test_register_list_agents_returns_function(self):
        """Test register_list_agents returns a function."""
        mock_agent = Mock()
        
        # The decorator should be called
        result = register_list_agents(mock_agent)
        
        # Should have called agent.tool decorator
        mock_agent.tool.assert_called_once()
        assert callable(result)
    
    def test_register_invoke_agent_returns_function(self):
        """Test register_invoke_agent returns a function."""
        mock_agent = Mock()
        
        result = register_invoke_agent(mock_agent)
        
        # Should have called agent.tool decorator
        mock_agent.tool.assert_called_once()
        assert callable(result)


class TestModuleGlobals:
    """Test module-level globals."""
    
    def test_temp_agent_count_exists(self):
        """Test _temp_agent_count global exists."""
        import code_puppy.tools.agent_tools as agent_tools_module
        
        assert hasattr(agent_tools_module, '_temp_agent_count')
        assert isinstance(agent_tools_module._temp_agent_count, int)
    
    def test_temp_agent_count_can_be_modified(self):
        """Test _temp_agent_count can be incremented."""
        import code_puppy.tools.agent_tools as agent_tools_module
        
        initial = agent_tools_module._temp_agent_count
        agent_tools_module._temp_agent_count += 1
        
        assert agent_tools_module._temp_agent_count == initial + 1
        
        # Reset
        agent_tools_module._temp_agent_count = initial
