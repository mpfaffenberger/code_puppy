"""Tests for GUI Cub agent functionality.

These tests are designed to be OS-agnostic and work on both Windows and macOS.
They focus on:
1. Tool registration and platform-specific behavior
2. Knowledge base file management
3. Agent configuration and metadata
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents.agent_gui_cub import GUICubAgent
from code_puppy.agents.base_agent import BaseAgent


class TestGUICubAgent:
    """Test suite for GUI Cub agent."""

    @pytest.fixture
    def agent(self):
        """Create a GUI Cub agent instance for testing."""
        return GUICubAgent()

    # ========================================================================
    # TEST CASE 1: Tool Registration & Platform-Specific Tools
    # ========================================================================

    def test_agent_inherits_from_base_agent(self, agent):
        """Verify GUI Cub properly inherits from BaseAgent."""
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
        assert "desktop_screenshot" in tools
        assert "desktop_screenshot_analyze" in tools
        assert "desktop_get_screen_size" in tools

        # OCR tools (should work on all platforms)
        assert "desktop_extract_text" in tools
        assert "desktop_find_text" in tools
        assert "desktop_verify_text" in tools

        # Mouse control (should work on all platforms)
        assert "desktop_mouse_move" in tools
        assert "desktop_mouse_click" in tools
        assert "desktop_mouse_drag" in tools

        # Keyboard control (should work on all platforms)
        assert "desktop_keyboard_type" in tools
        assert "desktop_keyboard_press" in tools
        assert "desktop_copy" in tools
        assert "desktop_paste" in tools

    @patch("sys.platform", "darwin")
    def test_macos_specific_tools_on_darwin(self, agent):
        """Verify macOS-specific accessibility tools are available on macOS."""
        # Need to reload the agent to pick up the mocked platform
        agent = GUICubAgent()
        tools = agent.get_available_tools()

        # macOS-specific accessibility tools
        assert "desktop_find_accessible_element" in tools
        assert "desktop_list_accessible_elements" in tools
        assert "desktop_click_accessible_element" in tools

        # Windows-specific tools should NOT be present
        assert "windows_focus_window" not in tools
        assert "windows_find_element" not in tools

    @patch("sys.platform", "win32")
    def test_windows_specific_tools_on_win32(self, agent):
        """Verify Windows-specific automation tools are available on Windows."""
        # Need to reload the agent to pick up the mocked platform
        agent = GUICubAgent()
        tools = agent.get_available_tools()

        # Windows-specific tools
        assert "windows_focus_window" in tools
        assert "windows_find_element" in tools
        assert "windows_click_element" in tools
        assert "windows_list_elements" in tools
        assert "windows_list_windows" in tools

        # macOS-specific tools should NOT be present
        assert "desktop_find_accessible_element" not in tools
        assert "desktop_list_accessible_elements" not in tools

    def test_verification_and_debugging_tools_available(self, agent):
        """Verify verification and debugging tools are registered."""
        tools = agent.get_available_tools()

        # Grid calibration tools
        assert "desktop_set_grid_density" in tools
        assert "desktop_show_grid_test_pattern" in tools
        assert "desktop_screenshot_with_confidence" in tools

        # Click debugging and verification
        assert "desktop_highlight_click_target" in tools
        assert "desktop_verify_coordinates" in tools
        assert "desktop_click_with_verification" in tools

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
            f.write("# GUI Cub Knowledge Base\n\n")
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
## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] Test Entry
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
        assert agent.display_name == "GUI Cub 🐻"
        assert "🐻" in agent.display_name  # Contains bear emoji
        assert "GUI" in agent.display_name

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

        # Check for key sections mentioned in the agent code
        assert "GUI Cub" in prompt
        assert "Knowledge Base" in prompt or "KB" in prompt
        assert "TIER" in prompt  # Method tier system
        assert "OCR" in prompt  # OCR tools mentioned
        assert "accessibility" in prompt.lower()  # Accessibility API
        assert "verification" in prompt.lower()  # Verification strategy

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
        assert "verify" in prompt.lower()
        assert "highlight" in prompt.lower() or "verification" in prompt.lower()

        # Should mention the PROHIBITED section
        assert "PROHIBITED" in prompt or "ALWAYS" in prompt

    def test_system_prompt_mentions_gui_cub(self, agent):
        """Verify system prompt identifies the agent as GUI Cub."""
        prompt = agent.get_system_prompt()

        # Should identify itself as GUI Cub (minimal personality - name is enough)
        assert "GUI Cub" in prompt, "System prompt should mention GUI Cub"

    def test_tools_config_consistency(self, agent):
        """Verify that tools mentioned in system prompt are actually available."""
        prompt = agent.get_system_prompt()
        tools = agent.get_available_tools()

        # Key tools that should be both mentioned and available
        critical_tools = [
            "desktop_screenshot",
            "desktop_find_text",
            "desktop_mouse_click",
            "desktop_keyboard_type",
            "desktop_click_with_verification",
            "desktop_highlight_click_target",
        ]

        for tool in critical_tools:
            # Tool should be available
            assert (
                tool in tools
            ), f"Tool '{tool}' mentioned in prompt but not in available tools"

    def test_agent_tool_count_reasonable(self, agent):
        """Verify agent has a reasonable number of tools (not empty, not excessive)."""
        tools = agent.get_available_tools()

        # Should have a substantial toolkit (RPA needs many tools)
        assert len(tools) > 30, "GUI Cub should have 30+ tools"

        # But not an unreasonable amount (might indicate duplicates)
        assert (
            len(tools) < 200
        ), "Tool count seems excessive, check for duplicates or errors"

        # All tools should be unique (no duplicates)
        assert len(tools) == len(set(tools)), "Duplicate tools detected in tool list"


    def test_system_prompt_stays_professional(self, agent):
        """Verify system prompt maintains professional tone without excessive bear puns."""
        prompt = agent.get_system_prompt()

        # Should NOT have excessive bear puns throughout
        bear_pun_terms = ["paw", "sniff", "hibernat", "forag", "ursine"]
        bear_pun_count = sum(prompt.lower().count(term) for term in bear_pun_terms)
        
        # Minimal personality = 0-2 bear references max, not constant puns
        assert bear_pun_count <= 2, f"Too many bear puns ({bear_pun_count}). Keep it minimal!"


class TestGUICubIntegration:
    """Integration tests for GUI Cub that test cross-component behavior."""

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
