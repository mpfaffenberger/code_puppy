"""Tests for GUI-Cub agent functionality.

These tests are designed to be OS-agnostic and work on both Windows and macOS.
They focus on:
1. Tool registration and platform-specific behavior
2. Knowledge base file management
3. Agent configuration and metadata
4. System prompt semantic auditing and safety constraints
5. Deep tool presence verification across platforms
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents.agent_gui_cub import GUICubAgent
from code_puppy.agents.base_agent import BaseAgent


class TestGUICubAgent:
    """Test suite for GUI-Cub agent."""

    @pytest.fixture
    def agent(self):
        """Create a GUI-Cub agent instance for testing.

        Note: Clears message history after creation to ensure a clean slate,
        since GUI-Cub may auto-resume from a saved session on startup.
        """
        agent = GUICubAgent()
        # Clear any auto-loaded resume messages for predictable test state
        agent.clear_message_history()
        return agent

    # ========================================================================
    # TEST CASE 1: Tool Registration & Platform-Specific Tools
    # ========================================================================

    def test_agent_inherits_from_base_agent(self, agent):
        """Verify GUI-Cub properly inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)
        assert hasattr(agent, "get_available_tools")
        assert hasattr(agent, "get_system_prompt")

    def test_base_tools_always_available(self, agent):
        """Verify core tools are available on all platforms."""
        tools = agent.get_available_tools()

        # Core agent tools
        assert "agent_share_your_reasoning" in tools

        # File operations
        assert "read_file" in tools
        assert "edit_file" in tools
        assert "list_files" in tools
        assert "grep" in tools

        # Screen capture (should work on all platforms)
        # Note: desktop_screenshot is a representative name that registers multiple tools
        assert "desktop_screenshot" in tools

        # OCR tools (should work on all platforms)
        # Note: desktop_ocr is a representative name that registers multiple tools
        assert "desktop_ocr" in tools

        # Mouse control (should work on all platforms)
        # Note: desktop_mouse is a representative name that registers multiple tools
        assert "desktop_mouse" in tools

        # Keyboard control (should work on all platforms)
        # Note: desktop_keyboard and desktop_shortcuts are representative names
        assert "desktop_keyboard" in tools
        assert "desktop_shortcuts" in tools

    @patch("sys.platform", "darwin")
    def test_macos_specific_tools_on_darwin(self, agent):
        """Verify macOS-specific accessibility tools are available on macOS."""
        # Need to reload the agent to pick up the mocked platform
        agent = GUICubAgent()
        tools = agent.get_available_tools()

        # macOS-specific accessibility tools
        # Note: desktop_accessibility is a representative name that registers multiple tools
        assert "desktop_accessibility" in tools

        # Windows-specific tools should NOT be present
        assert "windows_automation" not in tools

    @patch("sys.platform", "win32")
    def test_windows_specific_tools_on_win32(self, agent):
        """Verify Windows-specific automation tools are available on Windows."""
        # Need to reload the agent to pick up the mocked platform
        agent = GUICubAgent()
        tools = agent.get_available_tools()

        # Windows-specific tools
        # Note: windows_automation is a representative name that registers multiple tools
        assert "windows_automation" in tools

        # macOS-specific tools should NOT be present
        assert "desktop_accessibility" not in tools

    def test_verification_and_debugging_tools_available(self, agent):
        """Verify verification and debugging tools are registered."""
        tools = agent.get_available_tools()

        # Grid calibration tools
        # Note: desktop_grid_calibration is a representative name
        assert "desktop_grid_calibration" in tools

        # Click debugging and verification
        # Note: desktop_click_debugging is a representative name
        assert "desktop_click_debugging" in tools

    # ========================================================================
    # TEST CASE 2: Knowledge Base Management
    # ========================================================================

    @pytest.fixture
    def kb_file(self):
        """Create a temporary knowledge base file for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_gui_cub_knowledge_base.md", delete=False
        ) as f:
            # Write initial KB structure with markers
            f.write("# GUI-Cub Knowledge Base\n\n")
            f.write("<!-- KB_START -->\n\n")
            f.write("<!-- KB_END -->\n")
            temp_path = f.name

        yield Path(temp_path)

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    def test_knowledge_base_marker_system(self, kb_file):
        """Verify KB file has proper marker structure for safe appending."""
        content = kb_file.read_text()

        # Verify markers exist
        assert "<!-- KB_START -->" in content
        assert "<!-- KB_END -->" in content

        # Verify KB_START comes before KB_END
        start_idx = content.index("<!-- KB_START -->")
        end_idx = content.index("<!-- KB_END -->")
        assert start_idx < end_idx

    def test_knowledge_base_appending_pattern(self, kb_file):
        """Verify that appending to KB using the marker pattern works correctly."""
        from datetime import datetime

        # Simulate the KB logging pattern from the system prompt
        kb_entry = f"""
## [{datetime.now().strftime("%Y-%m-%d %H:%M")}] Test Entry
- Location: (100, 200) via OCR
- Method: desktop_find_text_in_window()
- App: TestApp
- Confidence: 0.85
- Notes: This is a test entry
"""

        # Read original content
        original_content = kb_file.read_text()

        # Simulate edit_file replacement (the pattern used in system prompt)
        new_content = original_content.replace(
            "<!-- KB_END -->", f"{kb_entry}<!-- KB_END -->"
        )

        # Write back
        kb_file.write_text(new_content)

        # Verify entry was added
        final_content = kb_file.read_text()
        assert "Test Entry" in final_content
        assert "Location: (100, 200) via OCR" in final_content
        assert "<!-- KB_END -->" in final_content  # Marker still exists

        # Verify KB_END is still at the end (after the entry)
        assert final_content.rstrip().endswith("<!-- KB_END -->")

    def test_knowledge_base_multiple_entries(self, kb_file):
        """Verify multiple entries can be appended without breaking markers."""
        entries = [
            "\n## Entry 1\n- Data: Test 1\n",
            "\n## Entry 2\n- Data: Test 2\n",
            "\n## Entry 3\n- Data: Test 3\n",
        ]

        content = kb_file.read_text()

        # Add multiple entries
        for entry in entries:
            content = content.replace("<!-- KB_END -->", f"{entry}<!-- KB_END -->")

        kb_file.write_text(content)

        # Verify all entries present and in order
        final_content = kb_file.read_text()
        assert "Entry 1" in final_content
        assert "Entry 2" in final_content
        assert "Entry 3" in final_content

        # Verify order is maintained
        entry1_idx = final_content.index("Entry 1")
        entry2_idx = final_content.index("Entry 2")
        entry3_idx = final_content.index("Entry 3")
        assert entry1_idx < entry2_idx < entry3_idx

        # Marker should still be at the end
        assert final_content.rstrip().endswith("<!-- KB_END -->")

    # ========================================================================
    # TEST CASE 3: Agent Configuration & Metadata
    # ========================================================================

    def test_agent_name_property(self, agent):
        """Verify agent name is correctly set."""
        assert agent.name == "gui-cub"
        assert isinstance(agent.name, str)

    def test_agent_display_name_property(self, agent):
        """Verify agent display name includes emoji and proper formatting."""
        assert agent.display_name == "Desktop Automation Cub 🐻"
        assert "🐻" in agent.display_name  # Contains bear emoji
        assert "Cub" in agent.display_name

    def test_agent_description_property(self, agent):
        """Verify agent description covers main capabilities."""
        description = agent.description
        assert isinstance(description, str)
        assert len(description) > 0

        # Should mention key capabilities
        assert "automation" in description.lower() or "rpa" in description.lower()

    def test_system_prompt_is_comprehensive(self, agent):
        """Verify system prompt contains critical sections and guidelines."""
        prompt = agent.get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 1000  # Should be comprehensive

        # Check for key content
        assert "GUI-Cub" in prompt
        assert "Knowledge Base" in prompt or "append_to_knowledge_base" in prompt
        assert "Tier" in prompt or "tier" in prompt  # Method tier system
        assert "OCR" in prompt  # OCR tools mentioned
        assert (
            "accessibility" in prompt.lower() or "Accessibility" in prompt
        )  # Accessibility API
        assert "verify" in prompt.lower() or "Verify" in prompt  # Verification strategy

    def test_system_prompt_includes_platform_awareness(self, agent):
        """Verify system prompt includes platform-specific guidance."""
        prompt = agent.get_system_prompt()

        # Should mention both platforms
        assert "macOS" in prompt or "darwin" in prompt.lower()
        assert "Windows" in prompt or "win32" in prompt.lower()

        # Should mention platform detection
        assert "platform" in prompt.lower()

    def test_system_prompt_includes_safety_guidelines(self, agent):
        """Verify system prompt includes critical safety and verification rules."""
        prompt = agent.get_system_prompt()

        # Safety features
        assert "verify" in prompt.lower() or "Verify" in prompt
        assert "highlight" in prompt.lower() or "validation" in prompt.lower()

        # Should mention rules
        assert "Critical Rules" in prompt or "NEVER" in prompt or "Rules" in prompt

    def test_system_prompt_mentions_gui_cub(self, agent):
        """Verify system prompt identifies the agent as GUI-Cub."""
        prompt = agent.get_system_prompt()

        # Should identify itself as GUI-Cub (minimal personality - name is enough)
        assert "GUI-Cub" in prompt, "System prompt should mention GUI-Cub"

    def test_tools_config_consistency(self, agent):
        """Verify that tools mentioned in system prompt are actually available."""
        tools = agent.get_available_tools()

        # Key representative tool groups that should be available
        critical_tools = [
            "desktop_screenshot",
            "desktop_ocr",
            "desktop_mouse",
            "desktop_keyboard",
            "desktop_click_debugging",
        ]

        for tool in critical_tools:
            # Tool group should be available
            assert tool in tools, (
                f"Tool group '{tool}' mentioned in prompt but not in available tools"
            )

    def test_agent_tool_count_reasonable(self, agent):
        """Verify agent has a reasonable number of tools (not empty, not excessive)."""
        tools = agent.get_available_tools()

        # With representative names, we should have ~20-30 tool groups
        assert len(tools) >= 15, "GUI-Cub should have at least 15 tool groups"

        # But not an unreasonable amount (might indicate duplicates)
        assert len(tools) < 50, (
            "Tool count seems excessive, check for duplicates or errors"
        )

        # All tools should be unique (no duplicates)
        assert len(tools) == len(set(tools)), "Duplicate tools detected in tool list"

    def test_system_prompt_stays_professional(self, agent):
        """Verify system prompt maintains professional tone without excessive bear puns."""
        prompt = agent.get_system_prompt()

        # Should NOT have excessive bear puns throughout
        bear_pun_terms = ["paw", "sniff", "hibernat", "forag", "ursine"]
        bear_pun_count = sum(prompt.lower().count(term) for term in bear_pun_terms)

        # Minimal personality = 0-2 bear references max, not constant puns
        assert bear_pun_count <= 2, (
            f"Too many bear puns ({bear_pun_count}). Keep it minimal!"
        )

    # ========================================================================
    # TEST CASE 4: Extended Tool Presence Verification
    # ========================================================================

    def test_unified_ui_tools_present(self, agent):
        """Verify unified UI tools are registered."""
        tools = set(agent.get_available_tools())
        # ui_automation is a representative name that registers multiple tools
        assert "ui_automation" in tools, "Missing ui_automation tool group"

    def test_keyboard_shortcut_tools_present(self, agent):
        """Verify keyboard shortcut tools are registered."""
        tools = set(agent.get_available_tools())
        # desktop_shortcuts is a representative name that registers multiple tools
        assert "desktop_shortcuts" in tools, "Missing desktop_shortcuts tool group"

    def test_window_and_utility_tools_present(self, agent):
        """Verify window and utility tools are registered."""
        tools = set(agent.get_available_tools())
        # desktop_window_control is a representative name that registers multiple tools
        assert "desktop_window_control" in tools, (
            "Missing desktop_window_control tool group"
        )

    @patch("sys.platform", "linux")
    def test_linux_platform_has_no_macos_or_windows_specific_tools(self):
        """Verify Linux builds don't include platform-specific tools."""
        agent = GUICubAgent()
        tools = set(agent.get_available_tools())

        # Representative names for platform-specific tools
        mac_specific = {"desktop_accessibility"}
        win_specific = {"windows_automation"}

        assert tools.isdisjoint(mac_specific), (
            "Linux should not include macOS-only tools"
        )
        assert tools.isdisjoint(win_specific), (
            "Linux should not include Windows-only tools"
        )

    @patch("sys.platform", "darwin")
    def test_macos_specific_full_set_present(self):
        """Verify complete macOS accessibility toolset is registered."""
        agent = GUICubAgent()
        tools = set(agent.get_available_tools())
        # desktop_accessibility is a representative name for macOS tools
        assert "desktop_accessibility" in tools, (
            "Missing desktop_accessibility tool group"
        )

    def test_critical_prompt_tools_are_available(self, agent):
        """Verify critical tools mentioned in prompt are actually registered."""
        tools = set(agent.get_available_tools())
        # Individual tools that don't belong to groups
        expected = {
            "desktop_click_element_smart",
        }
        # Representative tool groups that register multiple tools
        expected_groups = {
            "desktop_click_debugging",  # includes hover_and_verify, click_smart
            "desktop_vqa",  # includes find_and_hover, find_and_click
            "desktop_ocr",  # includes show_all_ocr_boxes
        }
        missing = expected - tools
        missing_groups = expected_groups - tools
        assert not missing, (
            f"Prompt mentions individual tools missing from registry: {sorted(missing)}"
        )
        assert not missing_groups, (
            f"Prompt mentions tool groups missing from registry: {sorted(missing_groups)}"
        )

    # ========================================================================
    # TEST CASE 5: System Prompt Deep Semantic Auditing
    # ========================================================================

    def test_prompt_includes_critical_mandatory_rules(self, agent):
        """Verify system prompt includes reporting and safety rules."""
        prompt = agent.get_system_prompt()
        # Reporting cadence
        assert "2-3 actions" in prompt or "frequently" in prompt.lower()
        assert "agent_share_your_reasoning" in prompt
        # Critical rules section
        assert "Critical Rules" in prompt or "NEVER" in prompt

    def test_prompt_includes_priority_order_and_tiers(self, agent):
        """Verify system prompt includes method selection strategy."""
        p = agent.get_system_prompt()
        # Tier system with fallback
        assert "Tier" in p or "tier" in p
        # Should mention keyboard, accessibility, OCR, VQA hierarchy
        assert "Keyboard" in p or "keyboard" in p
        assert "Accessibility" in p or "accessibility" in p.lower()
        assert "fallback" in p.lower() or "LAST RESORT" in p

    def test_prompt_includes_yaml_element_tree_guidance(self, agent):
        """Verify system prompt mentions YAML workflows."""
        p = agent.get_system_prompt()
        # YAML workflows should be mentioned
        assert "YAML" in p or "workflow" in p.lower()
        # Should reference workflow files
        assert ".yaml" in p or "workflows" in p.lower()

    def test_prompt_includes_timing_guidelines(self, agent):
        """Verify system prompt includes timing guidance."""
        p = agent.get_system_prompt()
        # Should mention timing/sleep
        assert "sleep" in p.lower() or "desktop_sleep" in p
        assert "delay" in p.lower() or "0.3s" in p  # Example timing

    def test_prompt_includes_verification_checklist_and_wrapup(self, agent):
        """Verify system prompt includes verification guidance."""
        p = agent.get_system_prompt()
        # Should mention verification and validation
        assert "verify" in p.lower() or "Verify" in p
        assert "Validate" in p or "check" in p.lower()

    def test_prompt_includes_screenshot_ocr_vqa_gating(self, agent):
        """Verify system prompt includes success-conditional output documentation."""
        p = agent.get_system_prompt()
        # Check for success-conditional output documentation
        assert "IMPORTANT:" in p or "automatically adjust" in p
        assert "Success-Conditional" in p or "success" in p.lower()
        assert "COMPACT" in p or "compact" in p.lower()
        assert "token" in p.lower()  # Should mention token efficiency

    def test_prompt_tool_reference_mentions_examples(self, agent):
        """Verify system prompt includes tool examples."""
        p = agent.get_system_prompt()
        assert "Example" in p or "example" in p.lower()
        # representative example code blocks
        assert "```" in p  # Code blocks present
        # Should have some tool names in examples
        assert "ui_" in p or "desktop_" in p

    def test_prompt_discourages_deprecated_recursive_vqa(self, agent):
        """Verify system prompt includes VQA guidance."""
        p = agent.get_system_prompt()
        # VQA should be mentioned as last resort
        assert "VQA" in p or "desktop_find_and_click" in p
        assert "last resort" in p.lower() or "LAST RESORT" in p

    def test_prompt_includes_prohibited_section(self, agent):
        """Verify system prompt includes operational guidelines."""
        p = agent.get_system_prompt()
        # Check for rules
        assert "Critical Rules" in p or "NEVER" in p or "Rules" in p
        # Check for VQA guidance
        assert "VQA" in p

    def test_prompt_platform_specific_nuance(self, agent):
        """Verify system prompt covers platform info."""
        p = agent.get_system_prompt()
        # Should mention platforms and cross-platform approach
        assert "platform" in p.lower() or "cross-platform" in p.lower()
        assert "macOS" in p or "Windows" in p

    def test_prompt_discourages_vqa_for_coordinates(self, agent):
        """Verify system prompt warns against using VQA for coordinates."""
        p = agent.get_system_prompt()
        # The prompt explicitly says not to use VQA for coordinates and mentions offset problems
        assert "VQA" in p
        assert (
            "not for coordinates" in p
            or "Do not use VQA for coordinates" in p
            or "50-100px offset" in p
        )

    def test_prompt_includes_knowledge_base_path(self, agent):
        """Verify system prompt includes knowledge base path and management guidance."""
        p = agent.get_system_prompt()
        assert "~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md" in p
        assert "Knowledge Base Management" in p or "KB" in p


class TestGUICubIntegration:
    """Integration tests for GUI-Cub that test cross-component behavior."""

    def test_agent_can_be_instantiated_without_errors(self):
        """Verify agent can be created without raising exceptions."""
        agent = GUICubAgent()
        assert agent is not None

    def test_agent_properties_are_consistent(self):
        """Verify agent properties don't change between accesses."""
        agent = GUICubAgent()

        # Properties should be stable
        assert agent.name == agent.name
        assert agent.display_name == agent.display_name
        assert agent.description == agent.description

    def test_tools_list_is_stable(self):
        """Verify tool list doesn't change between calls."""
        agent = GUICubAgent()

        tools1 = agent.get_available_tools()
        tools2 = agent.get_available_tools()

        # Should return the same tools (order might differ, so compare sets)
        assert set(tools1) == set(tools2)

    def test_system_prompt_is_stable(self):
        """Verify system prompt doesn't change between calls."""
        agent = GUICubAgent()

        prompt1 = agent.get_system_prompt()
        prompt2 = agent.get_system_prompt()

        assert prompt1 == prompt2
