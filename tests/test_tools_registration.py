"""Tests for the tool registration system."""

from unittest.mock import MagicMock

from code_puppy.tools import (
    TOOL_REGISTRY,
    get_available_tool_names,
    register_tools_for_agent,
    register_all_tools,
)


class TestToolRegistration:
    """Test tool registration functionality."""

    def test_tool_registry_structure(self):
        """Test that the tool registry has the expected structure."""
        expected_tools = [
            "list_files",
            "read_file",
            "grep",
            "edit_file",
            "delete_file",
            "agent_run_shell_command",
            "agent_share_your_reasoning",
            "list_agents",
            "invoke_agent",
        ]

        assert isinstance(TOOL_REGISTRY, dict)

        # Check all expected tools are present
        for tool in expected_tools:
            assert tool in TOOL_REGISTRY, f"Tool {tool} missing from registry"

        # Check structure of registry entries
        for tool_name, reg_func in TOOL_REGISTRY.items():
            assert callable(reg_func), (
                f"Registration function for {tool_name} is not callable"
            )

    def test_get_available_tool_names(self):
        """Test that get_available_tool_names returns the correct tools."""
        tools = get_available_tool_names()

        assert isinstance(tools, list)
        assert len(tools) == len(TOOL_REGISTRY)

        for tool in tools:
            assert tool in TOOL_REGISTRY

    def test_register_tools_for_agent(self):
        """Test registering specific tools for an agent."""
        mock_agent = MagicMock()

        # Test registering file operations tools
        register_tools_for_agent(mock_agent, ["list_files", "read_file"])

        # The mock agent should have had registration functions called
        # (We can't easily test the exact behavior since it depends on decorators)
        # But we can test that no exceptions were raised
        assert True  # If we get here, no exception was raised

    def test_register_tools_invalid_tool(self):
        """Test that registering an invalid tool prints warning and continues."""
        mock_agent = MagicMock()

        # This should not raise an error, just print a warning and continue
        register_tools_for_agent(mock_agent, ["invalid_tool"])

        # Verify agent was not called for the invalid tool
        assert mock_agent.call_count == 0 or not any(
            "invalid_tool" in str(call) for call in mock_agent.call_args_list
        )

    def test_register_all_tools(self):
        """Test registering all available tools."""
        mock_agent = MagicMock()

        # This should register all tools without error
        register_all_tools(mock_agent)

        # Test passed if no exception was raised
        assert True

    def test_json_agent_can_use_new_tools(self):
        """Test that a JSON agent can use our new list_agents and invoke_agent tools."""
        from code_puppy.agents.json_agent import JSONAgent
        
        # Create a temporary JSON agent config
        import tempfile
        import json
        
        agent_config = {
            "id": "test-agent-id",
            "name": "test-agent",
            "display_name": "Test Agent 🧪",
            "description": "A test agent that uses our new tools",
            "system_prompt": "You are a test agent.",
            "tools": ["list_agents", "invoke_agent"],
            "user_prompt": "What can I help you test?"
        }
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(agent_config, f, indent=2)
            temp_file_path = f.name
        
        try:
            # Load agent
            agent = JSONAgent(temp_file_path)
            
            # Verify agent properties
            assert agent.name == "test-agent"
            assert agent.display_name == "Test Agent 🧪"
            assert agent.description == "A test agent that uses our new tools"
            
            # Verify tools are in available tool list
            available_tools = agent.get_available_tools()
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
            # Should not include tools that don't exist
            agent_config["tools"].append("nonexistent_tool")
            with open(temp_file_path, 'w') as f:
                json.dump(agent_config, f, indent=2)
            
            # Reload agent
            agent = JSONAgent(temp_file_path)
            available_tools = agent.get_available_tools()
            
            # Should have filtered out the nonexistent tool
            assert "nonexistent_tool" not in available_tools
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
        finally:
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
        
        # Test passed if no exception was raised
        assert True

    def test_list_agents_and_invoke_agent_tools_registered(self):
        """Test that list_agents and invoke_agent tools are properly registered."""
        # Verify both tools are in the registry
        assert "list_agents" in TOOL_REGISTRY
        assert "invoke_agent" in TOOL_REGISTRY
        
        # Verify their registration functions are callable
        assert callable(TOOL_REGISTRY["list_agents"])
        assert callable(TOOL_REGISTRY["invoke_agent"])
        
        # Verify they appear in the available tools list
        available_tools = get_available_tool_names()
        assert "list_agents" in available_tools
        assert "invoke_agent" in available_tools
        
        # Verify they can be registered to an agent
        mock_agent = MagicMock()
        register_tools_for_agent(mock_agent, ["list_agents", "invoke_agent"])
        
        # Test passed if no exception was raised
        assert True

    def test_json_agent_can_use_new_tools(self):
        """Test that a JSON agent can use our new list_agents and invoke_agent tools."""
        from code_puppy.agents.json_agent import JSONAgent
        
        # Create a temporary JSON agent config
        import tempfile
        import json
        
        agent_config = {
            "id": "test-agent-id",
            "name": "test-agent",
            "display_name": "Test Agent 🧪",
            "description": "A test agent that uses our new tools",
            "system_prompt": "You are a test agent.",
            "tools": ["list_agents", "invoke_agent"],
            "user_prompt": "What can I help you test?"
        }
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(agent_config, f, indent=2)
            temp_file_path = f.name
        
        try:
            # Load agent
            agent = JSONAgent(temp_file_path)
            
            # Verify agent properties
            assert agent.name == "test-agent"
            assert agent.display_name == "Test Agent 🧪"
            assert agent.description == "A test agent that uses our new tools"
            
            # Verify tools are in available tool list
            available_tools = agent.get_available_tools()
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
            # Should not include tools that don't exist
            agent_config["tools"].append("nonexistent_tool")
            with open(temp_file_path, 'w') as f:
                json.dump(agent_config, f, indent=2)
            
            # Reload agent
            agent = JSONAgent(temp_file_path)
            available_tools = agent.get_available_tools()
            
            # Should have filtered out the nonexistent tool
            assert "nonexistent_tool" not in available_tools
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
        finally:
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
        
        # Test passed if no exception was raised
        assert True

    def test_register_tools_by_category(self):
        """Test that tools from different categories can be registered."""
        mock_agent = MagicMock()

        # Test file operations
        register_tools_for_agent(mock_agent, ["list_files"])

        # Test file modifications
        register_tools_for_agent(mock_agent, ["edit_file"])

        # Test command runner
        register_tools_for_agent(mock_agent, ["agent_run_shell_command"])

        # Test mixed categories
        register_tools_for_agent(
            mock_agent, ["read_file", "delete_file", "agent_share_your_reasoning"]
        )

        # Test passed if no exception was raised
        assert True

    def test_json_agent_can_use_new_tools(self):
        """Test that a JSON agent can use our new list_agents and invoke_agent tools."""
        from code_puppy.agents.json_agent import JSONAgent
        
        # Create a temporary JSON agent config
        import tempfile
        import json
        
        agent_config = {
            "id": "test-agent-id",
            "name": "test-agent",
            "display_name": "Test Agent 🧪",
            "description": "A test agent that uses our new tools",
            "system_prompt": "You are a test agent.",
            "tools": ["list_agents", "invoke_agent"],
            "user_prompt": "What can I help you test?"
        }
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(agent_config, f, indent=2)
            temp_file_path = f.name
        
        try:
            # Load agent
            agent = JSONAgent(temp_file_path)
            
            # Verify agent properties
            assert agent.name == "test-agent"
            assert agent.display_name == "Test Agent 🧪"
            assert agent.description == "A test agent that uses our new tools"
            
            # Verify tools are in available tool list
            available_tools = agent.get_available_tools()
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
            # Should not include tools that don't exist
            agent_config["tools"].append("nonexistent_tool")
            with open(temp_file_path, 'w') as f:
                json.dump(agent_config, f, indent=2)
            
            # Reload agent
            agent = JSONAgent(temp_file_path)
            available_tools = agent.get_available_tools()
            
            # Should have filtered out the nonexistent tool
            assert "nonexistent_tool" not in available_tools
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
        finally:
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
        
        # Test passed if no exception was raised
        assert True

    def test_list_agents_and_invoke_agent_tools_registered(self):
        """Test that list_agents and invoke_agent tools are properly registered."""
        # Verify both tools are in the registry
        assert "list_agents" in TOOL_REGISTRY
        assert "invoke_agent" in TOOL_REGISTRY
        
        # Verify their registration functions are callable
        assert callable(TOOL_REGISTRY["list_agents"])
        assert callable(TOOL_REGISTRY["invoke_agent"])
        
        # Verify they appear in the available tools list
        available_tools = get_available_tool_names()
        assert "list_agents" in available_tools
        assert "invoke_agent" in available_tools
        
        # Verify they can be registered to an agent
        mock_agent = MagicMock()
        register_tools_for_agent(mock_agent, ["list_agents", "invoke_agent"])
        
        # Test passed if no exception was raised
        assert True

    def test_json_agent_can_use_new_tools(self):
        """Test that a JSON agent can use our new list_agents and invoke_agent tools."""
        from code_puppy.agents.json_agent import JSONAgent
        
        # Create a temporary JSON agent config
        import tempfile
        import json
        
        agent_config = {
            "id": "test-agent-id",
            "name": "test-agent",
            "display_name": "Test Agent 🧪",
            "description": "A test agent that uses our new tools",
            "system_prompt": "You are a test agent.",
            "tools": ["list_agents", "invoke_agent"],
            "user_prompt": "What can I help you test?"
        }
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(agent_config, f, indent=2)
            temp_file_path = f.name
        
        try:
            # Load agent
            agent = JSONAgent(temp_file_path)
            
            # Verify agent properties
            assert agent.name == "test-agent"
            assert agent.display_name == "Test Agent 🧪"
            assert agent.description == "A test agent that uses our new tools"
            
            # Verify tools are in available tool list
            available_tools = agent.get_available_tools()
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
            # Should not include tools that don't exist
            agent_config["tools"].append("nonexistent_tool")
            with open(temp_file_path, 'w') as f:
                json.dump(agent_config, f, indent=2)
            
            # Reload agent
            agent = JSONAgent(temp_file_path)
            available_tools = agent.get_available_tools()
            
            # Should have filtered out the nonexistent tool
            assert "nonexistent_tool" not in available_tools
            assert "list_agents" in available_tools
            assert "invoke_agent" in available_tools
            
        finally:
            # Clean up temp file
            import os
            os.unlink(temp_file_path)
        
        # Test passed if no exception was raised
        assert True
