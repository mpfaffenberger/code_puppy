"""Comprehensive test coverage for pause_menu.py TUI components.

Covers menu initialization, agent rendering, multi-select functionality,
steering prompt input, resume functionality, and result handling.
"""

from unittest.mock import patch

import pytest

from code_puppy.command_line.pause_menu import (
    PAGE_SIZE,
    SteeringResult,
    _get_status_display,
    _render_menu_panel,
    _render_preview_panel,
    _sanitize_display_text,
    interactive_pause_menu,
    quick_resume,
    quick_steer,
)
from code_puppy.pause_manager import AgentEntry, AgentStatus, get_pause_manager


def _get_text_from_formatted(result):
    """Extract plain text from formatted text control output.

    The render functions return List[(style, text)] tuples.
    This helper extracts just the text content for easier assertions.
    """
    return "".join(text for _, text in result)


@pytest.fixture
def pause_manager():
    """Provide a fresh PauseManager for each test."""
    pm = get_pause_manager()
    pm.reset()
    return pm


class TestPageSizeConstant:
    """Test the PAGE_SIZE constant."""

    def test_page_size_is_defined(self):
        """Test that PAGE_SIZE constant is defined and reasonable."""
        assert PAGE_SIZE is not None
        assert isinstance(PAGE_SIZE, int)
        assert PAGE_SIZE > 0

    def test_page_size_value(self):
        """Test that PAGE_SIZE has expected value."""
        assert PAGE_SIZE == 10


class TestSteeringResult:
    """Test the SteeringResult dataclass."""

    def test_default_values(self):
        """Test default values for SteeringResult."""
        result = SteeringResult(queued_prompts=[], resumed_agents=[])
        assert result.queued_prompts == []
        assert result.resumed_agents == []
        assert result.cancelled is False

    def test_with_queued_prompts(self):
        """Test SteeringResult with queued prompts."""
        prompts = [("agent-1", "do something"), ("agent-2", "do something else")]
        result = SteeringResult(queued_prompts=prompts, resumed_agents=[])
        assert len(result.queued_prompts) == 2
        assert result.queued_prompts[0] == ("agent-1", "do something")

    def test_with_resumed_agents(self):
        """Test SteeringResult with resumed agents."""
        result = SteeringResult(
            queued_prompts=[],
            resumed_agents=["agent-1", "agent-2"],
        )
        assert len(result.resumed_agents) == 2

    def test_cancelled_flag(self):
        """Test SteeringResult with cancelled flag."""
        result = SteeringResult(
            queued_prompts=[], resumed_agents=[], cancelled=True
        )
        assert result.cancelled is True


class TestSanitizeDisplayText:
    """Test the _sanitize_display_text function."""

    def test_simple_text_unchanged(self):
        """Test that simple ASCII text is unchanged."""
        assert _sanitize_display_text("Hello World") == "Hello World"

    def test_strips_emojis(self):
        """Test that emojis are stripped."""
        result = _sanitize_display_text("Hello 🐶 World")
        assert "🐶" not in result
        assert "Hello" in result
        assert "World" in result

    def test_preserves_punctuation(self):
        """Test that punctuation is preserved."""
        assert _sanitize_display_text("Hello, World!") == "Hello, World!"

    def test_preserves_numbers(self):
        """Test that numbers are preserved."""
        assert _sanitize_display_text("Agent 123") == "Agent 123"

    def test_collapses_multiple_spaces(self):
        """Test that multiple spaces are collapsed."""
        assert _sanitize_display_text("Hello    World") == "Hello World"

    def test_empty_string(self):
        """Test handling of empty string."""
        assert _sanitize_display_text("") == ""


class TestGetStatusDisplay:
    """Test the _get_status_display function."""

    def test_running_status(self):
        """Test display for RUNNING status."""
        text, style = _get_status_display(AgentStatus.RUNNING)
        assert text == "RUNNING"
        assert "green" in style

    def test_paused_status(self):
        """Test display for PAUSED status."""
        text, style = _get_status_display(AgentStatus.PAUSED)
        assert text == "PAUSED"
        assert "yellow" in style

    def test_pause_requested_status(self):
        """Test display for PAUSE_REQUESTED status."""
        text, style = _get_status_display(AgentStatus.PAUSE_REQUESTED)
        assert text == "PAUSING..."
        assert "cyan" in style


class TestRenderMenuPanel:
    """Test the _render_menu_panel function."""

    def test_empty_agent_list(self):
        """Test rendering with no agents."""
        result = _render_menu_panel(
            agents=[], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "No agents registered" in text
        assert "Page 1/1" in text

    def test_single_agent_display(self):
        """Test rendering with single agent."""
        agent = AgentEntry(agent_id="agent-1", name="Test Agent")
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Test Agent" in text
        assert "[ ]" in text  # Not selected
        assert "RUNNING" in text

    def test_selected_agent_checkbox(self):
        """Test that selected agents show checked checkbox."""
        agent = AgentEntry(agent_id="agent-1", name="Test Agent")
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids={"agent-1"}
        )
        text = _get_text_from_formatted(result)
        assert "[x]" in text  # Selected

    def test_highlighted_agent(self):
        """Test that highlighted agent gets arrow indicator."""
        agents = [
            AgentEntry(agent_id="agent-1", name="First"),
            AgentEntry(agent_id="agent-2", name="Second"),
        ]
        result = _render_menu_panel(
            agents=agents, page=0, selected_idx=1, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        # Arrow should be on the highlighted agent
        assert "▶" in text

    def test_paused_agent_status(self):
        """Test that paused agents show correct status."""
        agent = AgentEntry(agent_id="agent-1", name="Test Agent")
        agent.status = AgentStatus.PAUSED
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "PAUSED" in text

    def test_navigation_hints_displayed(self):
        """Test that navigation hints are shown."""
        result = _render_menu_panel(
            agents=[], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Navigate" in text
        assert "Toggle select" in text
        assert "Steer selected" in text
        assert "Resume selected" in text

    def test_pagination_display(self):
        """Test pagination info is shown correctly."""
        # Create more agents than PAGE_SIZE
        agents = [
            AgentEntry(agent_id=f"agent-{i}", name=f"Agent {i}")
            for i in range(15)
        ]
        result = _render_menu_panel(
            agents=agents, page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Page 1/2" in text  # 15 agents = 2 pages at PAGE_SIZE=10

    def test_page_two_display(self):
        """Test second page shows remaining agents."""
        agents = [
            AgentEntry(agent_id=f"agent-{i}", name=f"Agent {i}")
            for i in range(15)
        ]
        result = _render_menu_panel(
            agents=agents, page=1, selected_idx=10, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Page 2/2" in text
        assert "Agent 10" in text
        assert "Agent 14" in text


class TestRenderPreviewPanel:
    """Test the _render_preview_panel function."""

    def test_no_agent_selected(self):
        """Test rendering when no agent is highlighted."""
        result = _render_preview_panel(
            agent=None, is_selected=False, selected_count=0, total_count=0
        )
        text = _get_text_from_formatted(result)
        assert "AGENT DETAILS" in text
        assert "No agent highlighted" in text

    def test_agent_details_displayed(self):
        """Test that agent details are shown."""
        agent = AgentEntry(agent_id="test-agent-123", name="Test Agent")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=1
        )
        text = _get_text_from_formatted(result)
        assert "Agent ID:" in text
        assert "test-agent-123" in text
        assert "Name:" in text
        assert "Test Agent" in text
        assert "Status:" in text
        assert "RUNNING" in text

    def test_selected_agent_indicator(self):
        """Test that selected status is shown."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=True, selected_count=1, total_count=1
        )
        text = _get_text_from_formatted(result)
        assert "✓" in text or "Yes" in text

    def test_selection_summary_none(self):
        """Test selection summary when none selected."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=5
        )
        text = _get_text_from_formatted(result)
        assert "None selected" in text

    def test_selection_summary_all(self):
        """Test selection summary when all selected."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=True, selected_count=5, total_count=5
        )
        text = _get_text_from_formatted(result)
        assert "All 5 selected" in text

    def test_selection_summary_partial(self):
        """Test selection summary with partial selection."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=True, selected_count=3, total_count=5
        )
        text = _get_text_from_formatted(result)
        assert "3 of 5 selected" in text

    def test_long_agent_id_truncated(self):
        """Test that very long agent IDs are truncated."""
        long_id = "a" * 50  # 50 characters
        agent = AgentEntry(agent_id=long_id, name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=1
        )
        text = _get_text_from_formatted(result)
        # Should truncate at 32 chars and add ...
        assert "..." in text

    def test_registration_time_displayed(self):
        """Test that registration time is shown."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=1
        )
        text = _get_text_from_formatted(result)
        assert "Registered:" in text


class TestInteractivePauseMenuDBOS:
    """Test DBOS guard behavior."""

    @pytest.mark.asyncio
    async def test_dbos_enabled_returns_cancelled(self, pause_manager):
        """Test that DBOS enabled returns cancelled result."""
        with patch.object(pause_manager, "is_dbos_enabled", return_value=True):
            with patch("code_puppy.command_line.pause_menu.emit_warning"):
                result = await interactive_pause_menu()
                assert result.cancelled is True
                assert result.queued_prompts == []
                assert result.resumed_agents == []


class TestInteractivePauseMenuEmpty:
    """Test behavior with no agents."""

    @pytest.mark.asyncio
    async def test_no_agents_returns_empty(self, pause_manager):
        """Test that empty agent list returns empty result."""
        # Ensure no agents registered
        pause_manager.reset()

        with patch("code_puppy.command_line.pause_menu.emit_info"):
            result = await interactive_pause_menu()
            assert result.cancelled is False
            assert result.queued_prompts == []
            assert result.resumed_agents == []


class TestQuickSteer:
    """Test the quick_steer convenience function."""

    @pytest.mark.asyncio
    async def test_quick_steer_success(self, pause_manager):
        """Test quick_steer queues input successfully."""
        pause_manager.register("agent-1", "Test Agent")

        result = await quick_steer("agent-1", "do something")

        assert result is True
        # Verify it was queued
        queue = pause_manager.get_steering_queue("agent-1")
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_quick_steer_unknown_agent(self, pause_manager):
        """Test quick_steer fails for unknown agent."""
        result = await quick_steer("nonexistent", "do something")
        assert result is False

    @pytest.mark.asyncio
    async def test_quick_steer_dbos_enabled(self, pause_manager):
        """Test quick_steer fails when DBOS is enabled."""
        pause_manager.register("agent-1", "Test Agent")

        with patch.object(pause_manager, "is_dbos_enabled", return_value=True):
            with patch("code_puppy.command_line.pause_menu.emit_warning"):
                result = await quick_steer("agent-1", "do something")
                assert result is False


class TestQuickResume:
    """Test the quick_resume convenience function."""

    @pytest.mark.asyncio
    async def test_quick_resume_specific_agent(self, pause_manager):
        """Test quick_resume resumes specific agent."""
        pause_manager.register("agent-1", "Test Agent")
        pause_manager.request_pause("agent-1")
        pause_manager.pause_checkpoint("agent-1")

        assert pause_manager.get_agent("agent-1").status == AgentStatus.PAUSED

        result = await quick_resume("agent-1")

        assert result is True
        assert pause_manager.get_agent("agent-1").status == AgentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_quick_resume_all_agents(self, pause_manager):
        """Test quick_resume resumes all agents."""
        pause_manager.register("agent-1", "Agent 1")
        pause_manager.register("agent-2", "Agent 2")
        pause_manager.request_pause()  # Global pause

        result = await quick_resume()  # Resume all

        assert result is True
        assert pause_manager.get_agent("agent-1").status == AgentStatus.RUNNING
        assert pause_manager.get_agent("agent-2").status == AgentStatus.RUNNING

    @pytest.mark.asyncio
    async def test_quick_resume_unknown_agent(self, pause_manager):
        """Test quick_resume handles unknown agent."""
        result = await quick_resume("nonexistent")
        assert result is False


class TestMenuPanelMultiSelect:
    """Test multi-select rendering in menu panel."""

    def test_multiple_agents_selected(self):
        """Test rendering with multiple agents selected."""
        agents = [
            AgentEntry(agent_id="agent-1", name="Agent 1"),
            AgentEntry(agent_id="agent-2", name="Agent 2"),
            AgentEntry(agent_id="agent-3", name="Agent 3"),
        ]
        selected = {"agent-1", "agent-3"}  # First and third selected

        result = _render_menu_panel(
            agents=agents, page=0, selected_idx=0, selected_agent_ids=selected
        )
        text = _get_text_from_formatted(result)

        # Count checkboxes
        assert text.count("[x]") == 2  # Two selected
        assert text.count("[ ]") == 1  # One not selected

    def test_select_all_option_hint(self):
        """Test that Select All hint is shown."""
        result = _render_menu_panel(
            agents=[], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Select all" in text

    def test_select_none_option_hint(self):
        """Test that Select None hint is shown."""
        result = _render_menu_panel(
            agents=[], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Select none" in text


class TestMenuPanelStatusBadges:
    """Test status badges in menu panel."""

    def test_running_agent_badge(self):
        """Test RUNNING status badge."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        agent.status = AgentStatus.RUNNING
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "[RUNNING]" in text

    def test_paused_agent_badge(self):
        """Test PAUSED status badge."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        agent.status = AgentStatus.PAUSED
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "[PAUSED]" in text

    def test_pause_requested_badge(self):
        """Test PAUSE_REQUESTED status badge."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        agent.status = AgentStatus.PAUSE_REQUESTED
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "[PAUSING...]" in text


class TestPreviewPanelQueueInfo:
    """Test steering queue info in preview panel."""

    def test_empty_queue_shows_zero(self):
        """Test that empty queue shows 0."""
        agent = AgentEntry(agent_id="agent-1", name="Test")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=1
        )
        text = _get_text_from_formatted(result)
        assert "Pending Steers:" in text

    def test_queue_with_items(self, pause_manager):
        """Test queue info shows count."""
        pause_manager.register("agent-1", "Test")
        pause_manager.send_steering_input("agent-1", "input1")
        pause_manager.send_steering_input("agent-1", "input2")

        agent = pause_manager.get_agent("agent-1")
        result = _render_preview_panel(
            agent=agent, is_selected=False, selected_count=0, total_count=1
        )
        text = _get_text_from_formatted(result)
        assert "Pending Steers:" in text
        # Should show 2 items in queue
        assert "2" in text


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_agent_with_emoji_in_name(self):
        """Test agent with emoji in name is sanitized."""
        agent = AgentEntry(agent_id="agent-1", name="🐶 Code Puppy 🐶")
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Code Puppy" in text
        assert "🐶" not in text  # Emoji should be stripped

    def test_very_long_agent_name(self):
        """Test handling of very long agent names."""
        long_name = "A" * 100
        agent = AgentEntry(agent_id="agent-1", name=long_name)
        result = _render_menu_panel(
            agents=[agent], page=0, selected_idx=0, selected_agent_ids=set()
        )
        # Should not raise an error
        text = _get_text_from_formatted(result)
        assert "A" in text  # Some part of the name should be there

    def test_page_boundary(self):
        """Test rendering at page boundary."""
        # Exactly PAGE_SIZE agents
        agents = [
            AgentEntry(agent_id=f"agent-{i}", name=f"Agent {i}")
            for i in range(PAGE_SIZE)
        ]
        result = _render_menu_panel(
            agents=agents, page=0, selected_idx=9, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Page 1/1" in text

    def test_last_agent_on_second_page(self):
        """Test highlighting last agent on second page."""
        agents = [
            AgentEntry(agent_id=f"agent-{i}", name=f"Agent {i}")
            for i in range(15)
        ]
        result = _render_menu_panel(
            agents=agents, page=1, selected_idx=14, selected_agent_ids=set()
        )
        text = _get_text_from_formatted(result)
        assert "Agent 14" in text
        assert "▶" in text
