"""Tests for the tool registration system."""

from unittest.mock import MagicMock

from code_puppy.tools import (
    TOOL_REGISTRY,
    get_available_tool_names,
    register_all_tools,
    register_tools_for_agent,
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
