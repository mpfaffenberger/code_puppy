"""Tests for GUI Cub agent functionality.

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
            assert tool in tools, (
                f"Tool '{tool}' mentioned in prompt but not in available tools"
            )

    def test_agent_tool_count_reasonable(self, agent):
        """Verify agent has a reasonable number of tools (not empty, not excessive)."""
        tools = agent.get_available_tools()

        # Should have a substantial toolkit (RPA needs many tools)
        assert len(tools) > 30, "GUI Cub should have 30+ tools"

        # But not an unreasonable amount (might indicate duplicates)
        assert len(tools) < 200, (
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
        expected = {
            "ui_list_windows",
            "ui_list_elements",
            "ui_find_element",
            "ui_click_element",
        }
        missing = expected - tools
        assert not missing, f"Missing unified UI tools: {sorted(missing)}"

    def test_keyboard_shortcut_tools_present(self, agent):
        """Verify keyboard shortcut tools are registered."""
        tools = set(agent.get_available_tools())
        expected = {
            "desktop_copy",
            "desktop_paste",
            "desktop_cut",
            "desktop_select_all",
            "desktop_save",
            "desktop_undo",
            "desktop_redo",
            "desktop_find",
            "desktop_new",
            "desktop_open",
            "desktop_close",
            "desktop_quit",
        }
        assert expected.issubset(tools)

    def test_window_and_utility_tools_present(self, agent):
        """Verify window and utility tools are registered."""
        tools = set(agent.get_available_tools())
        expected = {
            "desktop_sleep",
            "desktop_alert",
            "desktop_confirm",
            "desktop_prompt",
            "desktop_focus_window",
            "desktop_get_monitors",
            "desktop_check_pixel_color",
        }
        assert expected.issubset(tools)

    @patch("sys.platform", "linux")
    def test_linux_platform_has_no_macos_or_windows_specific_tools(self):
        """Verify Linux builds don't include platform-specific tools."""
        agent = GUICubAgent()
        tools = set(agent.get_available_tools())

        mac_specific = {
            "desktop_find_accessible_element",
            "desktop_list_accessible_elements",
            "desktop_click_accessible_element",
            "desktop_get_accessible_element_value",
            "desktop_list_accessible_tree",
        }
        win_specific = {
            "windows_focus_window",
            "windows_find_element",
            "windows_click_element",
            "windows_list_elements",
            "windows_list_windows",
        }

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
        expected = {
            "desktop_find_accessible_element",
            "desktop_list_accessible_elements",
            "desktop_click_accessible_element",
            "desktop_get_accessible_element_value",
            "desktop_list_accessible_tree",
        }
        missing = expected - tools
        assert not missing, f"Missing macOS tools: {sorted(missing)}"

    def test_critical_prompt_tools_are_available(self, agent):
        """Verify critical tools mentioned in prompt are actually registered."""
        tools = set(agent.get_available_tools())
        # Mentioned as NEW or critical in prompt
        expected = {
            "desktop_hover_and_verify",
            "desktop_click_smart",
            "desktop_click_element_smart",
            "desktop_find_and_hover",
            "desktop_find_and_click",
            "desktop_show_all_ocr_boxes",
        }
        missing = expected - tools
        assert not missing, (
            f"Prompt mentions tools missing from registry: {sorted(missing)}"
        )

    # ========================================================================
    # TEST CASE 5: System Prompt Deep Semantic Auditing
    # ========================================================================

    def test_prompt_includes_critical_mandatory_rules(self, agent):
        """Verify system prompt includes mandatory reporting and safety rules."""
        prompt = agent.get_system_prompt()
        # Mandatory reporting cadence
        assert "MANDATORY RULE" in prompt
        assert "every 2-3 actions" in prompt
        # Terminal prevention
        assert "TERMINAL/SHELL" in prompt or "terminal" in prompt.lower()
        assert "NEVER perform OCR on terminal" in prompt

    def test_prompt_includes_priority_order_and_tiers(self, agent):
        """Verify system prompt includes tier system for method selection."""
        p = agent.get_system_prompt()
        # Priority section and tier references
        assert "PRIORITY ORDER" in p
        for tier in ("TIER 1", "TIER 2", "TIER 3", "TIER 4", "TIER 5", "TIER 6"):
            assert tier in p

    def test_prompt_includes_yaml_element_tree_guidance(self, agent):
        """Verify system prompt includes YAML element tree documentation."""
        p = agent.get_system_prompt()
        assert "YAML Element Tree" in p
        assert "shorthand" in p.lower()
        assert "automation_id" in p or "auto_id" in p
        assert "success_indicator" in p
        assert "error_indicators" in p

    def test_prompt_includes_timing_guidelines(self, agent):
        """Verify system prompt includes timing and wait guidance."""
        p = agent.get_system_prompt()
        assert "Timing Guidelines" in p
        assert "Default wait times" in p
        assert "User-configurable waits" in p

    def test_prompt_includes_verification_checklist_and_wrapup(self, agent):
        """Verify system prompt includes verification and wrap-up protocols."""
        p = agent.get_system_prompt()
        assert "Verification & Self-Evaluation Checklist" in p
        assert "Wrap-Up Protocol" in p

    def test_prompt_includes_screenshot_ocr_vqa_gating(self, agent):
        """Verify system prompt includes success-conditional compaction info."""
        p = agent.get_system_prompt()
        # Check for success-conditional compaction documentation
        assert "Success-Conditional" in p or "success-conditional" in p
        assert "compact" in p.lower() or "compaction" in p.lower()
        assert "token" in p.lower()  # Should mention token savings

    def test_prompt_tool_reference_mentions_examples(self, agent):
        """Verify system prompt includes tool reference examples."""
        p = agent.get_system_prompt()
        assert "Tool Reference" in p
        # representative example code blocks referenced
        for snippet in (
            "desktop_click_accessible_element",
            "desktop_extract_text",
            "desktop_highlight_click_target",
        ):
            assert snippet in p

    def test_prompt_discourages_deprecated_recursive_vqa(self, agent):
        """Verify system prompt warns against deprecated VQA tools."""
        p = agent.get_system_prompt()
        assert "deprecated" in p.lower() or "unavailable" in p.lower()
        assert "desktop_find_element_recursive" in p

    def test_prompt_includes_prohibited_section(self, agent):
        """Verify system prompt includes operational guidelines."""
        p = agent.get_system_prompt()
        # Check for operational rules and guidelines
        assert "PROHIBITED" in p or "Critical Rules" in p or "ALWAYS" in p
        # Check for VQA usage guidance
        assert "VQA" in p or "desktop_screenshot_analyze" in p

    def test_prompt_platform_specific_nuance(self, agent):
        """Verify system prompt covers platform-specific nuances."""
        p = agent.get_system_prompt()
        assert "macOS" in p and "Windows" in p
        assert "Linux" in p
        assert "AXRole" in p or "UI Automation" in p or "control_type" in p

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


class TestGUICubTokenMonitoring:
    """Test suite for TIER 4 token monitoring functionality."""

    @pytest.fixture
    def agent(self):
        """Create a GUI Cub agent instance for testing."""
        return GUICubAgent()

    def test_token_monitor_initialized(self, agent):
        """Verify token monitor is initialized on agent creation."""
        assert hasattr(agent, "token_monitor")
        assert agent.token_monitor is not None
        assert agent.token_monitor.context_limit == 128000

    def test_token_monitor_thresholds_configured(self, agent):
        """Verify token thresholds are set correctly."""
        monitor = agent.token_monitor
        assert monitor.warning_threshold == 0.70
        assert monitor.checkpoint_threshold == 0.85
        assert monitor.emergency_threshold == 0.95

    def test_warning_threshold_triggers_at_70_percent(self, agent):
        """Verify warning triggers at 70% usage."""
        monitor = agent.token_monitor

        # Set to 69% - should not trigger
        result = monitor.update(int(128000 * 0.69))
        assert result is None
        assert not monitor.warning_fired

        # Set to 71% - should trigger warning
        result = monitor.update(int(128000 * 0.71))
        assert result == "warning"
        assert monitor.warning_fired

    def test_checkpoint_threshold_triggers_at_85_percent(self, agent):
        """Verify checkpoint triggers at 85% usage."""
        monitor = agent.token_monitor

        # Set to 84% - should not trigger checkpoint (but warning already fired)
        result = monitor.update(int(128000 * 0.84))
        # Should only return warning since it's the first threshold crossed
        assert result == "warning"

        # Set to 86% - should trigger checkpoint
        result = monitor.update(int(128000 * 0.86))
        assert result == "checkpoint"
        assert monitor.checkpoint_fired

    def test_emergency_threshold_triggers_at_95_percent(self, agent):
        """Verify emergency triggers at 95% usage."""
        monitor = agent.token_monitor

        # Jump straight to 96% - should trigger emergency (highest threshold)
        result = monitor.update(int(128000 * 0.96))
        # When jumping to 96%, emergency threshold (95%) is hit first
        assert result == "emergency"
        assert monitor.emergency_fired

        # Reset and test gradual increase
        monitor.reset_threshold_flags()

        # Gradually increase: 71% -> warning
        result = monitor.update(int(128000 * 0.71))
        assert result == "warning"

        # 86% -> checkpoint
        result = monitor.update(int(128000 * 0.86))
        assert result == "checkpoint"

        # 96% -> emergency
        result = monitor.update(int(128000 * 0.96))
        assert result == "emergency"
        assert monitor.emergency_fired

    def test_threshold_flags_reset(self, agent):
        """Verify threshold flags can be reset."""
        monitor = agent.token_monitor

        # Trigger all thresholds
        monitor.update(int(128000 * 0.71))
        monitor.update(int(128000 * 0.86))
        monitor.update(int(128000 * 0.96))

        assert monitor.warning_fired
        assert monitor.checkpoint_fired
        assert monitor.emergency_fired

        # Reset
        monitor.reset_threshold_flags()

        assert not monitor.warning_fired
        assert not monitor.checkpoint_fired
        assert not monitor.emergency_fired

    def test_get_percentage_calculation(self, agent):
        """Verify percentage calculation is accurate."""
        monitor = agent.token_monitor

        monitor.current_tokens = 64000  # 50% of 128000
        assert monitor.get_percentage() == 50.0

        monitor.current_tokens = 96000  # 75% of 128000
        assert monitor.get_percentage() == 75.0

    def test_get_remaining_calculation(self, agent):
        """Verify remaining tokens calculation is accurate."""
        monitor = agent.token_monitor

        monitor.current_tokens = 64000
        assert monitor.get_remaining() == 64000

        monitor.current_tokens = 120000
        assert monitor.get_remaining() == 8000

    def test_metrics_tracking(self, agent):
        """Verify metrics are tracked correctly."""
        monitor = agent.token_monitor

        # Initially zero
        metrics = monitor.get_metrics()
        assert metrics.warnings_fired == 0
        assert metrics.checkpoints_created == 0
        assert metrics.emergencies_fired == 0

        # Trigger warning
        monitor.update(int(128000 * 0.71))
        metrics = monitor.get_metrics()
        assert metrics.warnings_fired == 1

        # Trigger checkpoint
        monitor.update(int(128000 * 0.86))
        metrics = monitor.get_metrics()
        assert metrics.checkpoints_created == 1

        # Trigger emergency
        monitor.update(int(128000 * 0.96))
        metrics = monitor.get_metrics()
        assert metrics.emergencies_fired == 1

    def test_get_status_display_returns_string(self, agent):
        """Verify status display returns formatted string."""
        status = agent.get_token_status()
        assert isinstance(status, str)
        assert "Context Usage:" in status

    def test_check_token_usage_with_mock_history(self, agent):
        """Verify check_token_usage calculates from message history."""
        # Mock message history to simulate high token usage
        mock_messages = [
            {"role": "user", "content": "test" * 10000},  # Lots of tokens
            {"role": "assistant", "content": "response" * 10000},
        ]

        with patch.object(agent, "get_message_history", return_value=mock_messages):
            with patch.object(agent, "estimate_tokens_for_message", return_value=50000):
                # This should trigger warning (100K tokens)
                agent.check_token_usage()
                assert agent.token_monitor.warning_fired


class TestGUICubAutoResume:
    """Test suite for TIER 4.5 autonomous context self-management."""

    @pytest.fixture
    def agent(self):
        """Create a GUI Cub agent instance for testing."""
        return GUICubAgent()

    def test_generate_resume_prompt(self, agent):
        """Verify resume prompt generation captures context."""
        from code_puppy.agents.gui_cub_monitoring import generate_resume_prompt

        # Set up some message history
        agent.append_to_message_history(
            {"role": "user", "content": "Click the login button"}
        )
        agent.append_to_message_history(
            {
                "role": "assistant",
                "content": "Clicking login button with accessibility API",
            }
        )

        # Generate resume prompt
        resume_prompt = generate_resume_prompt(agent, "Test automation task")

        # Verify it contains key sections
        assert "GUI Cub Context Resume" in resume_prompt
        assert "Session Continuation" in resume_prompt
        assert "Test automation task" in resume_prompt
        assert "Recent User Requests" in resume_prompt
        assert "knowledge base" in resume_prompt.lower()

    def test_auto_save_and_resume_clears_history(self, agent):
        """Verify auto-resume clears message history."""
        from code_puppy.agents.gui_cub_monitoring import auto_save_and_resume

        # Add some messages
        for i in range(10):
            agent.append_to_message_history({"role": "user", "content": f"Message {i}"})

        # Should have 10 messages
        assert len(agent.get_message_history()) == 10

        # Auto-resume
        success, msg = auto_save_and_resume(agent)

        # Should succeed
        assert success

        # History should be cleared and replaced with resume prompt
        history = agent.get_message_history()
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert "GUI Cub Context Resume" in history[0]["content"]

    def test_auto_save_and_resume_resets_thresholds(self, agent):
        """Verify auto-resume resets threshold flags."""
        from code_puppy.agents.gui_cub_monitoring import auto_save_and_resume

        # Trigger thresholds
        agent.token_monitor.update(int(128000 * 0.71))
        agent.token_monitor.update(int(128000 * 0.86))

        assert agent.token_monitor.warning_fired
        assert agent.token_monitor.checkpoint_fired

        # Auto-resume should reset flags
        success, msg = auto_save_and_resume(agent)

        assert success
        assert not agent.token_monitor.warning_fired
        assert not agent.token_monitor.checkpoint_fired
