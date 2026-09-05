"""Tests for the tool registration system."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools import (
    REMOVED_LEGACY_TOOLS,
    TOOL_REGISTRY,
    get_available_tool_names,
    has_extended_thinking_active,
    register_all_tools,
    register_tools_for_agent,
    should_use_codex_patch,
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
            "list_agents",
            "invoke_agent",
            "invoke_agent_with_model",
            "list_available_models",
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
        assert "agent_share_your_reasoning" in tools

        for tool in tools:
            assert tool in TOOL_REGISTRY

    def test_register_tools_for_agent(self):
        """Test registering specific tools for an agent."""
        mock_agent = MagicMock()

        # Test registering file operations tools
        register_tools_for_agent(mock_agent, ["list_files", "read_file"])

        # Can't assert exact registration behavior (decorator-driven) — just that
        # nothing raised.
        assert True  # If we get here, no exception was raised

    @patch("code_puppy.tools._load_plugin_tools")
    @patch("code_puppy.tools.on_filter_agent_tools")
    @patch("code_puppy.tools.on_register_agent_tools")
    def test_filter_receives_complete_merged_tool_surface(
        self, mock_plugin_tools, mock_filter, _mock_load_plugin_tools
    ):
        """Policy filters run after plugin tools join the agent's base tools."""
        base_register = MagicMock()
        plugin_register = MagicMock()
        mock_plugin_tools.return_value = ["__plugin_tool"]
        mock_filter.return_value = ["__base_tool"]

        with patch.dict(
            TOOL_REGISTRY,
            {
                "__base_tool": base_register,
                "__plugin_tool": plugin_register,
            },
        ):
            register_tools_for_agent(
                MagicMock(), ["__base_tool"], agent_name="code-puppy"
            )

        mock_filter.assert_called_once_with(
            "code-puppy", ["__base_tool", "__plugin_tool"]
        )
        base_register.assert_called_once()
        plugin_register.assert_not_called()

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

    @pytest.mark.parametrize(
        "model_name, expected",
        [
            ("codex-gpt-5.4", True),
            ("chatgpt-gpt-5", True),
            ("gpt-5", True),
            ("claude-sonnet-4", False),
            ("gpt-4o", False),
        ],
    )
    def test_model_patch_capability(self, model_name, expected):
        assert should_use_codex_patch(model_name) is expected

    def test_codex_receives_only_apply_patch_for_file_mutations(self):
        class CapturingAgent:
            def __init__(self):
                self.names = []

            def tool(self, function):
                self.names.append(function.__name__)
                return function

        agent = CapturingAgent()
        register_tools_for_agent(
            agent,
            ["create_file", "replace_in_file", "delete_snippet", "delete_file"],
            model_name="codex-gpt-5.4",
        )

        assert "apply_patch" in agent.names
        assert not {
            "create_file",
            "edit",
            "replace_in_file",
            "delete_snippet",
            "delete_file",
        }.intersection(agent.names)

    def test_claude_receives_edit_alias_for_targeted_replacement(self):
        class CapturingAgent:
            def __init__(self):
                self.names = []

            def tool(self, function):
                self.names.append(function.__name__)
                return function

        agent = CapturingAgent()
        register_tools_for_agent(
            agent,
            ["replace_in_file"],
            model_name="claude-sonnet-4",
        )

        assert "edit" in agent.names
        assert "replace_in_file" not in agent.names


class TestRemovedReasoningToolBehavior:
    """Test that the retired reasoning tool is hidden from agent-facing use."""

    def testhas_extended_thinking_active_none_model(self):
        """Returns False when model_name is None and global model is None."""
        with patch("code_puppy.config.get_global_model_name", return_value=None):
            assert has_extended_thinking_active(None) is False

    def testhas_extended_thinking_active_non_anthropic_model(self):
        """Returns False for non-Anthropic models."""
        assert has_extended_thinking_active("gpt-4o") is False
        assert has_extended_thinking_active("gemini-2.5-pro") is False
        assert has_extended_thinking_active("o3-mini") is False

    @pytest.mark.parametrize(
        "model,setting,expected",
        [
            ("claude-sonnet-4-20250514", {"extended_thinking": "enabled"}, True),
            ("claude-sonnet-4-20250514", {"extended_thinking": "adaptive"}, True),
            ("claude-sonnet-4-20250514", {"extended_thinking": "off"}, False),
            ("claude-sonnet-4-20250514", {"extended_thinking": True}, True),
            ("claude-sonnet-4-20250514", {"extended_thinking": False}, False),
            ("anthropic-claude-sonnet", {"extended_thinking": "enabled"}, True),
            ("claude-sonnet-4-20250514", {}, True),
        ],
    )
    @patch("code_puppy.config.get_effective_model_settings")
    def test_has_extended_thinking_active(
        self, mock_settings, model, setting, expected
    ):
        """Claude extended_thinking resolves per setting; defaults to enabled."""
        mock_settings.return_value = setting
        assert has_extended_thinking_active(model) is expected

    def test_legacy_reasoning_tool_remains_in_registry_for_custom_agents(self):
        """Custom JSON agents can still request the legacy reasoning tool."""
        assert "agent_share_your_reasoning" in TOOL_REGISTRY
        assert "agent_share_your_reasoning" not in REMOVED_LEGACY_TOOLS

    @patch("code_puppy.tools.emit_warning")
    def test_legacy_reasoning_tool_can_be_registered_without_warning(
        self, mock_warning
    ):
        """Old custom agent configs should still register the legacy tool cleanly."""
        mock_agent = MagicMock()

        register_tools_for_agent(
            mock_agent,
            ["list_files", "agent_share_your_reasoning"],
            model_name="codex-gpt-5.4",
        )

        mock_warning.assert_not_called()
