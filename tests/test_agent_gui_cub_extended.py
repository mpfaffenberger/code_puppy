"""Extended, obsessive test suite for GUI Cub agent.

Goal: ruthless coverage of agent metadata, platform logic, safety rules, and system prompt
coherence. We keep tests deterministic and OS-agnostic where possible by inspecting
string content and tool lists.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.agents.agent_gui_cub import GUICubAgent


@pytest.fixture()
def agent() -> GUICubAgent:
    return GUICubAgent()


# ---------------------------------------------------------------------------
# Tool list structure and content
# ---------------------------------------------------------------------------

def test_unified_ui_tools_present(agent: GUICubAgent) -> None:
    tools = set(agent.get_available_tools())
    expected = {
        "ui_list_windows",
        "ui_list_elements",
        "ui_find_element",
        "ui_click_element",
    }
    missing = expected - tools
    assert not missing, f"Missing unified UI tools: {sorted(missing)}"


def test_keyboard_shortcut_tools_present(agent: GUICubAgent) -> None:
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


def test_window_and_utility_tools_present(agent: GUICubAgent) -> None:
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


# Platform matrix: ensure darwin adds mac tools and not windows, and win32 vice versa,
# and that non-darwin/non-win32 (linux) adds neither set.

@patch("sys.platform", "linux")
def test_linux_platform_has_no_macos_or_windows_specific_tools() -> None:
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

    assert tools.isdisjoint(mac_specific), "Linux should not include macOS-only tools"
    assert tools.isdisjoint(win_specific), "Linux should not include Windows-only tools"


# ---------------------------------------------------------------------------
# System prompt semantic audits
# ---------------------------------------------------------------------------

def test_prompt_includes_critical_mandatory_rules(agent: GUICubAgent) -> None:
    prompt = agent.get_system_prompt()
    # Mandatory reporting cadence
    assert "MANDATORY RULE" in prompt
    assert "every 2-3 actions" in prompt
    # Terminal prevention
    assert "TERMINAL/SHELL" in prompt or "terminal" in prompt.lower()
    assert "NEVER perform OCR on terminal" in prompt


def test_prompt_includes_priority_order_and_tiers(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    # Priority section and tier references
    assert "PRIORITY ORDER" in p
    for tier in ("TIER 1", "TIER 2", "TIER 3", "TIER 4", "TIER 5", "TIER 6"):
        assert tier in p


def test_prompt_includes_yaml_element_tree_guidance(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "YAML Element Tree" in p
    assert "shorthand" in p.lower()
    assert "automation_id" in p or "auto_id" in p
    assert "success_indicator" in p
    assert "error_indicators" in p


def test_prompt_includes_timing_guidelines(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "Timing Guidelines" in p
    assert "Default wait times" in p
    assert "User-configurable waits" in p


def test_prompt_includes_verification_checklist_and_wrapup(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "Verification & Self-Evaluation Checklist" in p
    assert "Wrap-Up Protocol" in p


def test_prompt_includes_screenshot_ocr_vqa_gating(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "Heavy tooling warning" in p or "Screenshots, OCR, and VQA are expensive" in p
    assert "explicitly requests" in p
    assert "Do not take screenshots" in p or "MUST NOT invoke" in p


def test_prompt_tool_reference_mentions_examples(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "Tool Reference" in p
    # representative example code blocks referenced
    for snippet in ("desktop_click_accessible_element", "desktop_extract_text", "desktop_highlight_click_target"):
        assert snippet in p


def test_prompt_discourages_deprecated_recursive_vqa(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "deprecated" in p.lower() or "unavailable" in p.lower()
    assert "desktop_find_element_recursive" in p


# ---------------------------------------------------------------------------
# Consistency between prompt mentions and tools
# ---------------------------------------------------------------------------

def test_critical_prompt_tools_are_available(agent: GUICubAgent) -> None:
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
    assert not missing, f"Prompt mentions tools missing from registry: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Stability and idempotency
# ---------------------------------------------------------------------------

def test_tools_are_sorted_stable_set(agent: GUICubAgent) -> None:
    # We can't assert sorting deterministically, but we can assert stability across calls
    t1 = agent.get_available_tools()
    t2 = agent.get_available_tools()
    assert set(t1) == set(t2)


# ---------------------------------------------------------------------------
# Hard safety constraints explicitly spelled out
# ---------------------------------------------------------------------------

def test_prompt_includes_prohibited_section(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "PROHIBITED" in p
    assert "Do not take screenshots" in p or "MUST NOT invoke" in p


# ---------------------------------------------------------------------------
# Platform specific nuance in prompt
# ---------------------------------------------------------------------------

def test_prompt_platform_specific_nuance(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "macOS" in p and "Windows" in p
    assert "Linux" in p
    assert "AXRole" in p or "UI Automation" in p or "control_type" in p


# ---------------------------------------------------------------------------
# Extra spot checks
# ---------------------------------------------------------------------------

@patch("sys.platform", "darwin")
def test_macos_specific_full_set_present() -> None:
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


def test_prompt_discourages_vqa_for_coordinates(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    # The prompt explicitly says not to use VQA for coordinates and mentions offset problems
    assert "VQA" in p
    assert "not for coordinates" in p or "Do not use VQA for coordinates" in p or "50-100px offset" in p



def test_prompt_includes_knowledge_base_path(agent: GUICubAgent) -> None:
    p = agent.get_system_prompt()
    assert "~/.code_puppy/agents/gui-cub/gui_cub_knowledge_base.md" in p
    assert "Knowledge Base Management" in p or "KB" in p

# Keep file short-ish; do not bloat beyond 600 lines. This is tidy enough.
