"""Tests for the tool registration system."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import Agent

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
            "shell",
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

    def test_only_read_tools_are_marked_speculatable(self):
        """Speculation is opt-in on the actual registered tool definitions."""
        agent = Agent("test")
        register_tools_for_agent(
            agent,
            [
                "list_files",
                "read_file",
                "grep",
                "load_image_for_analysis",
                "list_available_models",
                "list_agents",
                "create_file",
            ],
        )
        from code_puppy.tools.skills_tools import (
            register_activate_skill,
            register_list_or_search_skills,
        )

        register_activate_skill(agent)
        register_list_or_search_skills(agent)
        tools = agent._function_toolset.tools

        for name in (
            "list_files",
            "read_file",
            "grep",
            "load_image_for_analysis",
            "list_available_models",
            "list_agents",
            "activate_skill",
            "list_or_search_skills",
        ):
            assert tools[name].metadata["speculatable"] is True
        assert not (tools["create_file"].metadata or {}).get("speculatable", False)

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
        register_tools_for_agent(mock_agent, ["shell"])

        # Test mixed categories
        register_tools_for_agent(
            mock_agent, ["read_file", "delete_file", "agent_share_your_reasoning"]
        )

        # Test passed if no exception was raised
        assert True


_FILE_TOOL_NAMES = {
    "create_file",
    "replace_in_file",
    "delete_snippet",
    "delete_file",
    "edit",
    "apply_patch",
}


class _CapturingAgent:
    """Minimal stand-in recording the tool names pydantic-ai would see."""

    def __init__(self):
        self.names: list[str] = []

    def tool(self, fn=None, **_kwargs):
        if fn is None:
            return lambda f: self.tool(f)
        self.names.append(fn.__name__)
        return fn

    @property
    def file_tools(self) -> list[str]:
        """Only the file-editing surface; plugin ``register_agent_tools``
        hooks left behind by other tests may add unrelated names."""
        return [n for n in self.names if n in _FILE_TOOL_NAMES]


class TestRetiredProviderEditors:
    """``edit`` / ``apply_patch`` are gone; every model gets the granular tools."""

    @pytest.mark.parametrize(
        "model_name",
        ["codex-gpt-5.4", "chatgpt-gpt-5", "claude-code-claude-opus-4-7", "qwen-q4"],
    )
    def test_every_model_gets_the_same_file_tools(self, model_name):
        agent = _CapturingAgent()
        register_tools_for_agent(
            agent, ["create_file", "replace_in_file"], model_name=model_name
        )
        # Plugin hooks left behind by other tests may add unrelated tools;
        # only the file-editing surface matters here.
        file_tools = [
            n
            for n in agent.names
            if n in {"create_file", "replace_in_file", "edit", "apply_patch"}
        ]
        assert file_tools == ["create_file", "replace_in_file"]

    def test_retired_names_are_not_registrable(self):
        assert "edit" not in TOOL_REGISTRY
        assert "apply_patch" not in TOOL_REGISTRY

    def test_retired_names_alias_to_granular_tools(self):
        """Agent configs written during the provider-editor era keep working."""
        agent = _CapturingAgent()
        register_tools_for_agent(agent, ["edit", "apply_patch"], model_name="qwen-q4")
        assert agent.file_tools == [
            "replace_in_file",
            "create_file",
            "delete_snippet",
            "delete_file",
        ]


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
