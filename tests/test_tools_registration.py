"""Tests for the tool registration system."""

from unittest.mock import MagicMock, patch

from code_puppy.tools import (
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


class TestExtendedThinkingReasoningToolSkip:
    """Test that agent_share_your_reasoning is dynamically skipped
    when Anthropic models have extended thinking enabled or adaptive."""

    def testhas_extended_thinking_active_none_model(self):
        """Returns False when model_name is None and global model is None."""
        with patch("code_puppy.config.get_global_model_name", return_value=None):
            assert has_extended_thinking_active(None) is False

    def testhas_extended_thinking_active_non_anthropic_model(self):
        """Returns False for non-Anthropic models."""
        assert has_extended_thinking_active("gpt-4o") is False
        assert has_extended_thinking_active("gemini-2.5-pro") is False
        assert has_extended_thinking_active("o3-mini") is False

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_claude_enabled(self, mock_settings):
        """Returns True for Claude models with extended_thinking='enabled'."""
        mock_settings.return_value = {"extended_thinking": "enabled"}
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is True

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_claude_adaptive(self, mock_settings):
        """Returns True for Claude models with extended_thinking='adaptive'."""
        mock_settings.return_value = {"extended_thinking": "adaptive"}
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is True

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_claude_off(self, mock_settings):
        """Returns False for Claude models with extended_thinking='off'."""
        mock_settings.return_value = {"extended_thinking": "off"}
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is False

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_legacy_bool_true(self, mock_settings):
        """Returns True for legacy boolean True (backwards compat)."""
        mock_settings.return_value = {"extended_thinking": True}
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is True

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_legacy_bool_false(self, mock_settings):
        """Returns False for legacy boolean False (backwards compat)."""
        mock_settings.return_value = {"extended_thinking": False}
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is False

    @patch("code_puppy.config.get_effective_model_settings")
    def testhas_extended_thinking_active_anthropic_prefix(self, mock_settings):
        """Also works for 'anthropic-' prefixed model names."""
        mock_settings.return_value = {"extended_thinking": "enabled"}
        assert has_extended_thinking_active("anthropic-claude-sonnet") is True

    @patch("code_puppy.config.get_effective_model_settings")
    def test_has_extended_thinking_default_is_enabled(self, mock_settings):
        """When no extended_thinking setting exists, defaults to 'enabled'."""
        mock_settings.return_value = {}  # No extended_thinking key
        assert has_extended_thinking_active("claude-sonnet-4-20250514") is True

    @patch("code_puppy.tools.has_extended_thinking_active", return_value=True)
    def test_reasoning_tool_skipped_when_thinking_active(self, mock_thinking):
        """agent_share_your_reasoning is NOT registered when thinking is active."""
        mock_agent = MagicMock()

        # Track which register functions are called
        called_tools = []
        TOOL_REGISTRY.copy()

        def make_tracker(name):
            def tracker(agent):
                called_tools.append(name)

            return tracker

        with patch.dict(
            "code_puppy.tools.TOOL_REGISTRY",
            {
                "list_files": make_tracker("list_files"),
                "agent_share_your_reasoning": make_tracker(
                    "agent_share_your_reasoning"
                ),
            },
            clear=True,
        ):
            register_tools_for_agent(
                mock_agent,
                ["list_files", "agent_share_your_reasoning"],
                model_name="claude-sonnet-4-20250514",
            )

        assert "list_files" in called_tools
        assert "agent_share_your_reasoning" not in called_tools

    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    def test_reasoning_tool_registered_when_thinking_off(self, mock_thinking):
        """agent_share_your_reasoning IS registered when thinking is off."""
        mock_agent = MagicMock()

        called_tools = []

        def make_tracker(name):
            def tracker(agent):
                called_tools.append(name)

            return tracker

        with patch.dict(
            "code_puppy.tools.TOOL_REGISTRY",
            {
                "list_files": make_tracker("list_files"),
                "agent_share_your_reasoning": make_tracker(
                    "agent_share_your_reasoning"
                ),
            },
            clear=True,
        ):
            register_tools_for_agent(
                mock_agent,
                ["list_files", "agent_share_your_reasoning"],
                model_name="gpt-4o",
            )

        assert "list_files" in called_tools
        assert "agent_share_your_reasoning" in called_tools

    @patch("code_puppy.tools.has_extended_thinking_active", return_value=False)
    def test_reasoning_tool_registered_for_non_anthropic(self, mock_thinking):
        """Non-Anthropic models always get the reasoning tool."""
        mock_agent = MagicMock()

        called_tools = []

        def make_tracker(name):
            def tracker(agent):
                called_tools.append(name)

            return tracker

        with patch.dict(
            "code_puppy.tools.TOOL_REGISTRY",
            {
                "agent_share_your_reasoning": make_tracker(
                    "agent_share_your_reasoning"
                ),
            },
            clear=True,
        ):
            register_tools_for_agent(
                mock_agent,
                ["agent_share_your_reasoning"],
                model_name="gemini-2.5-pro",
            )

        assert "agent_share_your_reasoning" in called_tools
