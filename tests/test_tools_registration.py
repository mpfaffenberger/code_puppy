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

    def test_register_tools_invalid_tool(self):
        """Test that registering an invalid tool prints warning and continues."""
        mock_agent = MagicMock()

        # This should not raise an error, just print a warning and continue
        register_tools_for_agent(mock_agent, ["invalid_tool"])

        # Verify agent was not called for the invalid tool
        assert mock_agent.call_count == 0 or not any(
            "invalid_tool" in str(call) for call in mock_agent.call_args_list
        )

    def test_explicitly_requesting_native_editor_by_name_is_still_capability_gated(
        self,
    ):
        """Regression: the swap block in register_tools_for_agent only ever
        ADDS str_replace_based_edit_tool -- it never blocks a caller (a JSON
        agent config, or a plugin's register_agent_tools extra) that names
        the tool directly. Since it's an ordinary TOOL_REGISTRY entry, the
        generic registration loop used to register it for ANY model
        regardless of the feature flag or the direct-Anthropic-route
        requirement, defeating the least-privilege gate documented in
        model_capabilities.py. Must be blocked at the point of registration
        too, not just at swap time."""
        mock_agent = MagicMock()

        register_tools_for_agent(
            mock_agent, ["str_replace_based_edit_tool"], model_name="gpt-5"
        )

        registered_names = {
            getattr(call.args[0], "__name__", None)
            for call in mock_agent.tool.call_args_list
        }
        assert "str_replace_based_edit_tool" not in registered_names

    def test_native_editor_registers_when_capability_actually_supported(self):
        """Sanity counterpart to the regression above: the gate must not be
        so strict it blocks a genuinely-eligible direct-Anthropic model."""
        mock_agent = MagicMock()

        with patch(
            "code_puppy.tools.supports_anthropic_native_editor", return_value=True
        ):
            register_tools_for_agent(
                mock_agent,
                ["str_replace_based_edit_tool"],
                model_name="claude-5-sonnet",
            )

        registered_names = {
            getattr(call.args[0], "__name__", None)
            for call in mock_agent.tool.call_args_list
        }
        assert "str_replace_based_edit_tool" in registered_names

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
