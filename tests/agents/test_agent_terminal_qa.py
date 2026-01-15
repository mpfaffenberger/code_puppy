"""Tests for the Terminal QA Agent.

Terminal QA Agent specializes in testing terminal and TUI applications
using Code Puppy's API server with visual analysis capabilities.
"""

import pytest

from code_puppy.agents.base_agent import BaseAgent

# =============================================================================
# Import Tests
# =============================================================================


class TestTerminalQAImports:
    """Test that Terminal QA Agent can be imported."""

    def test_import_terminal_qa_agent(self):
        """Test Terminal QA Agent can be imported."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        assert TerminalQAAgent is not None


# =============================================================================
# Agent Properties Tests
# =============================================================================


class TestTerminalQAAgentProperties:
    """Test Terminal QA Agent properties and configuration."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_inherits_base_agent(self, agent):
        """Test Terminal QA Agent inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)

    def test_name(self, agent):
        """Test Terminal QA Agent has correct name."""
        assert agent.name == "terminal-qa"

    def test_display_name(self, agent):
        """Test Terminal QA Agent has correct display name."""
        assert agent.display_name == "Terminal QA Agent 🖥️"

    def test_description(self, agent):
        """Test Terminal QA Agent has a meaningful description."""
        assert agent.description is not None
        assert len(agent.description) > 0
        assert "terminal" in agent.description.lower()
        assert (
            "visual" in agent.description.lower() or "tui" in agent.description.lower()
        )


# =============================================================================
# Terminal Tools Tests
# =============================================================================


class TestTerminalQAToolsTerminal:
    """Test Terminal QA Agent has terminal-specific tools."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_tools_include_terminal_check_server(self, agent):
        """Test agent has terminal_check_server tool."""
        tools = agent.get_available_tools()
        assert "terminal_check_server" in tools

    def test_tools_include_terminal_open(self, agent):
        """Test agent has terminal_open tool."""
        tools = agent.get_available_tools()
        assert "terminal_open" in tools

    def test_tools_include_terminal_close(self, agent):
        """Test agent has terminal_close tool."""
        tools = agent.get_available_tools()
        assert "terminal_close" in tools

    def test_tools_include_terminal_run_command(self, agent):
        """Test agent has terminal_run_command tool."""
        tools = agent.get_available_tools()
        assert "terminal_run_command" in tools

    def test_tools_include_terminal_send_keys(self, agent):
        """Test agent has terminal_send_keys tool."""
        tools = agent.get_available_tools()
        assert "terminal_send_keys" in tools

    def test_tools_include_terminal_wait_output(self, agent):
        """Test agent has terminal_wait_output tool."""
        tools = agent.get_available_tools()
        assert "terminal_wait_output" in tools

    def test_tools_include_terminal_screenshot_analyze(self, agent):
        """Test agent has terminal_screenshot_analyze tool."""
        tools = agent.get_available_tools()
        assert "terminal_screenshot_analyze" in tools

    def test_tools_include_terminal_read_output(self, agent):
        """Test agent has terminal_read_output tool."""
        tools = agent.get_available_tools()
        assert "terminal_read_output" in tools

    def test_tools_include_terminal_compare_mockup(self, agent):
        """Test agent has terminal_compare_mockup tool."""
        tools = agent.get_available_tools()
        assert "terminal_compare_mockup" in tools

    def test_tools_include_load_image_for_analysis(self, agent):
        """Test agent has load_image_for_analysis tool."""
        tools = agent.get_available_tools()
        assert "load_image_for_analysis" in tools


# =============================================================================
# Browser Tools Excluded Tests
# =============================================================================


class TestTerminalQAToolsBrowserExcluded:
    """Test Terminal QA Agent does NOT have browser tools.

    Browser tools use CamoufoxManager (a separate web browser) and are
    designed for HTML DOM interaction - NOT for terminal/TUI apps!
    Terminal apps use keyboard input via terminal_send_keys.
    """

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_tools_exclude_browser_click(self, agent):
        """Test agent does NOT have browser_click tool."""
        tools = agent.get_available_tools()
        assert "browser_click" not in tools

    def test_tools_exclude_browser_double_click(self, agent):
        """Test agent does NOT have browser_double_click tool."""
        tools = agent.get_available_tools()
        assert "browser_double_click" not in tools

    def test_tools_exclude_browser_hover(self, agent):
        """Test agent does NOT have browser_hover tool."""
        tools = agent.get_available_tools()
        assert "browser_hover" not in tools

    def test_tools_exclude_browser_find_by_role(self, agent):
        """Test agent does NOT have browser_find_by_role tool."""
        tools = agent.get_available_tools()
        assert "browser_find_by_role" not in tools

    def test_tools_exclude_browser_find_by_text(self, agent):
        """Test agent does NOT have browser_find_by_text tool."""
        tools = agent.get_available_tools()
        assert "browser_find_by_text" not in tools

    def test_tools_exclude_browser_find_by_label(self, agent):
        """Test agent does NOT have browser_find_by_label tool."""
        tools = agent.get_available_tools()
        assert "browser_find_by_label" not in tools

    def test_tools_exclude_browser_find_buttons(self, agent):
        """Test agent does NOT have browser_find_buttons tool."""
        tools = agent.get_available_tools()
        assert "browser_find_buttons" not in tools

    def test_tools_exclude_browser_find_links(self, agent):
        """Test agent does NOT have browser_find_links tool."""
        tools = agent.get_available_tools()
        assert "browser_find_links" not in tools

    def test_tools_exclude_browser_xpath_query(self, agent):
        """Test agent does NOT have browser_xpath_query tool."""
        tools = agent.get_available_tools()
        assert "browser_xpath_query" not in tools

    def test_tools_exclude_browser_execute_js(self, agent):
        """Test agent does NOT have browser_execute_js tool."""
        tools = agent.get_available_tools()
        assert "browser_execute_js" not in tools

    def test_tools_exclude_browser_scroll(self, agent):
        """Test agent does NOT have browser_scroll tool."""
        tools = agent.get_available_tools()
        assert "browser_scroll" not in tools

    def test_tools_exclude_browser_wait_for_element(self, agent):
        """Test agent does NOT have browser_wait_for_element tool."""
        tools = agent.get_available_tools()
        assert "browser_wait_for_element" not in tools

    def test_tools_exclude_browser_highlight_element(self, agent):
        """Test agent does NOT have browser_highlight_element tool."""
        tools = agent.get_available_tools()
        assert "browser_highlight_element" not in tools

    def test_tools_exclude_browser_clear_highlights(self, agent):
        """Test agent does NOT have browser_clear_highlights tool."""
        tools = agent.get_available_tools()
        assert "browser_clear_highlights" not in tools


# =============================================================================
# Excluded Tools Tests
# =============================================================================


class TestTerminalQAToolsExcluded:
    """Test Terminal QA Agent does NOT include navigation tools that would break terminal."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_tools_exclude_browser_navigate(self, agent):
        """Test agent does NOT have browser_navigate tool."""
        tools = agent.get_available_tools()
        assert "browser_navigate" not in tools

    def test_tools_exclude_browser_go_back(self, agent):
        """Test agent does NOT have browser_go_back tool."""
        tools = agent.get_available_tools()
        assert "browser_go_back" not in tools

    def test_tools_exclude_browser_go_forward(self, agent):
        """Test agent does NOT have browser_go_forward tool."""
        tools = agent.get_available_tools()
        assert "browser_go_forward" not in tools

    def test_tools_exclude_browser_reload(self, agent):
        """Test agent does NOT have browser_reload tool."""
        tools = agent.get_available_tools()
        assert "browser_reload" not in tools


# =============================================================================
# Core Tools Tests
# =============================================================================


class TestTerminalQAToolsCore:
    """Test Terminal QA Agent has core agent tools."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_tools_include_reasoning(self, agent):
        """Test agent has agent_share_your_reasoning tool."""
        tools = agent.get_available_tools()
        assert "agent_share_your_reasoning" in tools


# =============================================================================
# System Prompt Tests
# =============================================================================


class TestTerminalQASystemPrompt:
    """Test Terminal QA Agent system prompt content."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_system_prompt_not_empty(self, agent):
        """Test Terminal QA Agent has a system prompt."""
        prompt = agent.get_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_system_prompt_mentions_terminal(self, agent):
        """Test system prompt mentions terminal testing."""
        prompt = agent.get_system_prompt().lower()
        assert "terminal" in prompt

    def test_system_prompt_mentions_server_check(self, agent):
        """Test system prompt mentions checking the server."""
        prompt = agent.get_system_prompt().lower()
        assert "check" in prompt and "server" in prompt

    def test_system_prompt_mentions_terminal_open(self, agent):
        """Test system prompt mentions opening terminal."""
        prompt = agent.get_system_prompt().lower()
        assert "terminal_open" in prompt or "open" in prompt

    def test_system_prompt_mentions_screenshots(self, agent):
        """Test system prompt mentions screenshot capabilities."""
        prompt = agent.get_system_prompt().lower()
        assert "screenshot" in prompt

    def test_system_prompt_mentions_mockup_comparison(self, agent):
        """Test system prompt mentions mockup comparison."""
        prompt = agent.get_system_prompt().lower()
        assert "mockup" in prompt

    def test_system_prompt_mentions_visual_analysis(self, agent):
        """Test system prompt mentions visual analysis."""
        prompt = agent.get_system_prompt().lower()
        assert "visual" in prompt or "vqa" in prompt

    def test_system_prompt_mentions_xterm(self, agent):
        """Test system prompt mentions xterm.js."""
        prompt = agent.get_system_prompt().lower()
        assert "xterm" in prompt

    def test_system_prompt_mentions_workflow(self, agent):
        """Test system prompt describes a workflow."""
        prompt = agent.get_system_prompt().lower()
        assert "workflow" in prompt

    def test_system_prompt_warns_about_navigation(self, agent):
        """Test system prompt warns about not using navigation tools."""
        prompt = agent.get_system_prompt().lower()
        # Should mention not navigating or warn about breaking terminal context
        assert "navigate" in prompt or "navigation" in prompt


# =============================================================================
# Discovery Tests
# =============================================================================


class TestTerminalQADiscovery:
    """Test that Terminal QA Agent is discoverable via agent_manager."""

    def test_terminal_qa_discoverable(self):
        """Test Terminal QA Agent is discoverable."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        assert "terminal-qa" in agents

    def test_terminal_qa_loadable(self):
        """Test Terminal QA Agent can be loaded via load_agent."""
        from code_puppy.agents import load_agent

        agent = load_agent("terminal-qa")
        assert agent is not None
        assert agent.name == "terminal-qa"
        assert isinstance(agent, BaseAgent)

    def test_terminal_qa_display_name_in_registry(self):
        """Test Terminal QA Agent display name is in registry."""
        from code_puppy.agents import get_available_agents

        agents = get_available_agents()
        display_name = agents.get("terminal-qa")
        assert display_name is not None
        assert "Terminal QA" in display_name
        assert "🖥️" in display_name


# =============================================================================
# Integration Tests
# =============================================================================


class TestTerminalQAIntegration:
    """Test Terminal QA Agent integration with the rest of the system."""

    @pytest.fixture
    def agent(self):
        """Create a Terminal QA Agent instance."""
        from code_puppy.agents.agent_terminal_qa import TerminalQAAgent

        return TerminalQAAgent()

    def test_all_terminal_tools_present(self, agent):
        """Test all required terminal tools are present."""
        tools = agent.get_available_tools()

        terminal_tools = [
            "terminal_check_server",
            "terminal_open",
            "terminal_close",
            "terminal_run_command",
            "terminal_send_keys",
            "terminal_wait_output",
            "terminal_screenshot_analyze",
            "terminal_read_output",
            "terminal_compare_mockup",
            "load_image_for_analysis",
        ]

        for tool in terminal_tools:
            assert tool in tools, f"Missing terminal tool: {tool}"

    def test_no_browser_interaction_tools(self, agent):
        """Test browser interaction tools are NOT present (they use wrong browser)."""
        tools = agent.get_available_tools()

        # Browser tools use CamoufoxManager, not ChromiumTerminalManager
        # They're for web pages, not terminal/TUI apps!
        browser_tools = [
            "browser_click",
            "browser_double_click",
            "browser_hover",
            "browser_find_by_role",
            "browser_find_by_text",
            "browser_find_by_label",
            "browser_find_buttons",
            "browser_find_links",
            "browser_xpath_query",
            "browser_execute_js",
            "browser_scroll",
            "browser_wait_for_element",
            "browser_highlight_element",
            "browser_clear_highlights",
        ]

        for tool in browser_tools:
            assert tool not in tools, f"Browser tool should NOT be present: {tool}"

    def test_no_dangerous_navigation_tools(self, agent):
        """Test that dangerous navigation tools are excluded."""
        tools = agent.get_available_tools()

        excluded_tools = [
            "browser_navigate",
            "browser_go_back",
            "browser_go_forward",
            "browser_reload",
        ]

        for tool in excluded_tools:
            assert tool not in tools, f"Dangerous tool present: {tool}"

    def test_tool_count_reasonable(self, agent):
        """Test agent has a reasonable number of tools."""
        tools = agent.get_available_tools()
        # Should have ~11 terminal-focused tools (no browser tools)
        assert len(tools) >= 10, "Too few tools"
        assert len(tools) <= 20, "Too many tools"
