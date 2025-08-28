"""Tests for agent switching functionality."""

import pytest
from unittest.mock import patch

from code_puppy.agents import (
    get_available_agents,
    get_current_agent_config,
    set_current_agent,
    load_agent_config,
    clear_agent_cache,
)
from code_puppy.agents.agent_code_puppy import CodePuppyAgent


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
        """Test loading an invalid agent falls back to code-puppy."""
        # In our new system, invalid agents fall back to code-puppy
        result = load_agent_config("nonexistent")
        assert result.name == "code-puppy"


class TestAgentSwitching:
    """Test agent switching functionality."""

    def test_get_current_agent_config_default(self):
        """Test getting current agent config returns default."""
        # Clear any cached state
        clear_agent_cache()

        # Should return default agent - could be code-puppy or agent-creator depending on state
        agent = get_current_agent_config()
        assert agent.name in ["code-puppy", "agent-creator"]
        assert hasattr(agent, "name")
        assert hasattr(agent, "get_system_prompt")

    def test_set_current_agent_valid(self):
        """Test setting current agent to a valid agent."""
        # Try to set to code-puppy (should always be available)
        result = set_current_agent("code-puppy")

        assert result is True

        # Verify the agent was actually set
        current = get_current_agent_config()
        assert current.name == "code-puppy"

    def test_set_current_agent_invalid(self):
        """Test setting current agent to an invalid agent."""
        result = set_current_agent("nonexistent")

        assert result is False

    @patch("code_puppy.config.get_value")
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
        assert hasattr(agent, "name")
        assert hasattr(agent, "display_name")
        assert hasattr(agent, "description")

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
            "agent_share_your_reasoning",
        ]

        for tool in expected_tools:
            assert tool in tools, f"Tool {tool} should be available to CodePuppyAgent"

        # Ensure no extra tools
        assert len(tools) == len(expected_tools), (
            f"Expected {len(expected_tools)} tools, got {len(tools)}"
        )

    def test_json_agent_integration(self):
        """Test that JSON agents integrate properly with the agent system."""
        from code_puppy.agents import get_available_agents, clear_agent_cache

        # Clear cache to ensure fresh discovery
        clear_agent_cache()

        # Get available agents
        agents = get_available_agents()

        # Should include both Python and JSON agents
        assert "code-puppy" in agents  # Python agent
        # Note: We can't guarantee JSON agents in test environment
        # since they depend on user directory, but the system should work

        assert isinstance(agents, dict)
        assert len(agents) >= 1  # At least code-puppy should be available

    def test_system_prompt_includes_config(self):
        """Test that system prompt includes config values."""
        with patch(
            "code_puppy.agents.agent_code_puppy.get_puppy_name",
            return_value="TestPuppy",
        ):
            with patch(
                "code_puppy.agents.agent_code_puppy.get_owner_name",
                return_value="TestOwner",
            ):
                agent = CodePuppyAgent()
                prompt = agent.get_system_prompt()

                assert "TestPuppy" in prompt
                assert "TestOwner" in prompt


class TestAgentSwitchingIntegration:
    """Integration tests for complete agent switching workflow."""

    def test_complete_agent_switching_workflow(self):
        """Test the complete agent switching workflow end-to-end using agent-creator."""
        # Clear any cached state to start fresh
        clear_agent_cache()

        # Step 1: Get the current agent (should be default)
        original_agent = get_current_agent_config()
        original_name = original_agent.name

        # Step 2: Verify agent-creator is available
        available_agents = get_available_agents()
        target_agent_name = "agent-creator"

        if target_agent_name not in available_agents:
            pytest.skip(f"Agent '{target_agent_name}' not available for testing")

        # Step 3: Switch to the agent-creator agent
        switch_result = set_current_agent(target_agent_name)
        assert switch_result is True, f"Failed to switch to agent '{target_agent_name}'"

        # Step 4: Verify the switch was successful
        new_current_agent = get_current_agent_config()
        assert new_current_agent.name == target_agent_name, (
            f"Expected current agent to be '{target_agent_name}', but got '{new_current_agent.name}'"
        )

        # Step 5: Verify the agent is actually different from original
        if target_agent_name != original_name:
            assert new_current_agent.name != original_name, "Agent should have changed"
            # Verify it's not the same instance (cache was cleared)
            assert new_current_agent is not original_agent, (
                "Should be a new agent instance"
            )

        # Step 6: Verify agent-creator has expected properties
        assert "agent-creator" in new_current_agent.name
        assert hasattr(new_current_agent, "display_name")
        assert len(new_current_agent.get_system_prompt()) > 0
        tools = new_current_agent.get_available_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

        # Step 7: Switch back to original agent to clean up
        restore_result = set_current_agent(original_name)
        assert restore_result is True, (
            f"Failed to restore original agent '{original_name}'"
        )

        # Step 8: Verify restoration worked
        restored_agent = get_current_agent_config()
        assert restored_agent.name == original_name, (
            f"Failed to restore to original agent '{original_name}'"
        )

    def test_agent_creator_specific_functionality(self):
        """Test that agent-creator agent has expected functionality after switching."""
        clear_agent_cache()

        # Get available agents
        available_agents = get_available_agents()
        target_agent_name = "agent-creator"

        if target_agent_name not in available_agents:
            pytest.skip(f"Agent '{target_agent_name}' not available for testing")

        # Store original agent for cleanup
        original_agent = get_current_agent_config()
        original_name = original_agent.name

        try:
            # Switch to agent-creator
            switch_result = set_current_agent(target_agent_name)
            assert switch_result is True, (
                f"Failed to switch to agent '{target_agent_name}'"
            )

            # Get the agent-creator
            agent_creator = get_current_agent_config()

            # Verify it's the correct agent
            assert agent_creator.name == "agent-creator"

            # Verify agent-creator specific properties
            assert (
                "Agent Creator" in agent_creator.display_name
                or "agent-creator" in agent_creator.display_name
            )

            # Verify agent-creator has appropriate tools for its function
            tools = agent_creator.get_available_tools()
            assert "agent_share_your_reasoning" in tools, (
                "agent-creator should have reasoning capability"
            )

            # Agent-creator should have file operations for creating agent files
            expected_tools = ["list_files", "read_file", "edit_file"]
            for tool in expected_tools:
                assert tool in tools, (
                    f"agent-creator should have {tool} for creating agent files"
                )

            # Verify system prompt is appropriate for agent creation
            system_prompt = agent_creator.get_system_prompt()
            assert len(system_prompt) > 100, (
                "agent-creator should have a substantial system prompt"
            )

            # Check that the prompt mentions agent creation (case insensitive)
            prompt_lower = system_prompt.lower()
            agent_keywords = ["agent", "create", "json", "configuration"]
            found_keywords = [kw for kw in agent_keywords if kw in prompt_lower]
            assert len(found_keywords) >= 2, (
                f"agent-creator prompt should mention agent creation concepts, found: {found_keywords}"
            )

        finally:
            # Always restore original agent
            set_current_agent(original_name)

    def test_agent_properties_persist_after_switch(self):
        """Test that agent properties are correct after switching to specific agents."""
        clear_agent_cache()

        # Test with specific agents we know should exist
        agents_to_test = ["code-puppy", "agent-creator"]
        available_agents = get_available_agents()

        for agent_name in agents_to_test:
            if agent_name not in available_agents:
                # Skip if agent not available, but don't fail the test
                continue

            # Switch to this agent
            switch_result = set_current_agent(agent_name)
            assert switch_result is True, f"Failed to switch to agent '{agent_name}'"

            # Get the agent and verify its properties
            current_agent = get_current_agent_config()

            # Verify basic properties
            assert current_agent.name == agent_name
            assert hasattr(current_agent, "display_name")
            assert hasattr(current_agent, "description")
            assert len(current_agent.get_system_prompt()) > 0
            assert isinstance(current_agent.get_available_tools(), list)
            assert len(current_agent.get_available_tools()) > 0

            # Verify the agent is functional
            tools = current_agent.get_available_tools()
            for tool in tools:
                assert isinstance(tool, str), (
                    f"Tool names should be strings, got {type(tool)}"
                )
                assert len(tool) > 0, "Tool names should not be empty"

            # Agent-specific validations
            if agent_name == "agent-creator":
                # Agent-creator should have specific tools for creating agents
                assert "agent_share_your_reasoning" in tools, (
                    "agent-creator should have reasoning tool"
                )
            elif agent_name == "code-puppy":
                # Code-puppy should have file manipulation tools
                assert "edit_file" in tools, "code-puppy should have file editing tools"

    def test_invalid_agent_switch_preserves_current(self):
        """Test that switching to invalid agent preserves current agent."""
        clear_agent_cache()

        # Get current agent
        original_agent = get_current_agent_config()
        original_name = original_agent.name

        # Try to switch to invalid agent
        switch_result = set_current_agent("definitely-not-a-real-agent-name-12345")
        assert switch_result is False, "Switch to invalid agent should fail"

        # Verify current agent is unchanged
        current_agent = get_current_agent_config()
        assert current_agent.name == original_name, (
            "Current agent should be unchanged after failed switch"
        )
