"""Comprehensive test coverage for agent_menu.py UI components.

Covers menu initialization, agent entry retrieval, rendering,
pagination, current agent marking, and preview panel display.
"""

from unittest.mock import patch

from code_puppy.command_line.agent_menu import (
    PAGE_SIZE,
    _get_agent_entries,
    _render_menu_panel,
    _render_preview_panel,
)


def _get_text_from_formatted(result):
    """Extract plain text from formatted text control output.

    The render functions return List[(style, text)] tuples.
    This helper extracts just the text content for easier assertions.
    """
    return "".join(text for _, text in result)


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


class TestGetAgentEntries:
    """Test the _get_agent_entries function."""

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_empty_list_when_no_agents(self, mock_available, mock_descriptions):
        """Test that empty list is returned when no agents are available."""
        mock_available.return_value = {}
        mock_descriptions.return_value = {}

        result = _get_agent_entries()

        assert result == []

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_single_agent(self, mock_available, mock_descriptions):
        """Test that single agent is returned correctly."""
        mock_available.return_value = {"code_puppy": "Code Puppy 🐶"}
        mock_descriptions.return_value = {"code_puppy": "A friendly coding assistant."}

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0] == (
            "code_puppy",
            "Code Puppy 🐶",
            "A friendly coding assistant.",
        )

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_multiple_agents_sorted(self, mock_available, mock_descriptions):
        """Test that multiple agents are returned sorted alphabetically."""
        mock_available.return_value = {
            "zebra_agent": "Zebra Agent",
            "alpha_agent": "Alpha Agent",
            "beta_agent": "Beta Agent",
        }
        mock_descriptions.return_value = {
            "zebra_agent": "Zebra description",
            "alpha_agent": "Alpha description",
            "beta_agent": "Beta description",
        }

        result = _get_agent_entries()

        assert len(result) == 3
        # Should be sorted alphabetically by name (case-insensitive)
        assert result[0][0] == "alpha_agent"
        assert result[1][0] == "beta_agent"
        assert result[2][0] == "zebra_agent"

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_handles_missing_description(self, mock_available, mock_descriptions):
        """Test that missing descriptions get default value."""
        mock_available.return_value = {"test_agent": "Test Agent"}
        mock_descriptions.return_value = {}  # No description for this agent

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0] == ("test_agent", "Test Agent", "No description available")

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_handles_extra_descriptions(self, mock_available, mock_descriptions):
        """Test that extra descriptions (without matching agents) are ignored."""
        mock_available.return_value = {"agent1": "Agent One"}
        mock_descriptions.return_value = {
            "agent1": "Description for agent1",
            "agent2": "Description for non-existent agent",
        }

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0][0] == "agent1"

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_sorts_case_insensitive(self, mock_available, mock_descriptions):
        """Test that sorting is case-insensitive."""
        mock_available.return_value = {
            "UPPER_AGENT": "Upper Agent",
            "lower_agent": "Lower Agent",
            "Mixed_Agent": "Mixed Agent",
        }
        mock_descriptions.return_value = {
            "UPPER_AGENT": "Upper desc",
            "lower_agent": "Lower desc",
            "Mixed_Agent": "Mixed desc",
        }

        result = _get_agent_entries()

        # Should be sorted: lower_agent, Mixed_Agent, UPPER_AGENT
        assert result[0][0] == "lower_agent"
        assert result[1][0] == "Mixed_Agent"
        assert result[2][0] == "UPPER_AGENT"

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_more_than_page_size(self, mock_available, mock_descriptions):
        """Test handling of more agents than PAGE_SIZE."""
        # Create 15 agents (more than PAGE_SIZE of 10)
        agents = {f"agent_{i:02d}": f"Agent {i:02d}" for i in range(15)}
        descriptions = {f"agent_{i:02d}": f"Description {i:02d}" for i in range(15)}

        mock_available.return_value = agents
        mock_descriptions.return_value = descriptions

        result = _get_agent_entries()

        assert len(result) == 15
        # All agents should be present
        agent_names = [entry[0] for entry in result]
        for i in range(15):
            assert f"agent_{i:02d}" in agent_names


class TestRenderMenuPanel:
    """Test the _render_menu_panel function."""

    def test_renders_empty_list(self):
        """Test rendering when no agents are available."""
        result = _render_menu_panel([], page=0, selected_idx=0, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "No agents found" in text
        # Should show page 1 of 1 even for empty list
        assert "Page 1/1" in text

    def test_renders_single_agent(self):
        """Test rendering a single agent.

        Note: Emojis are stripped from display names for clean terminal rendering.
        """
        entries = [("code_puppy", "Code Puppy 🐶", "A friendly assistant.")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Emojis are sanitized for clean terminal rendering
        assert "Code Puppy" in text
        assert "Page 1/1" in text

    def test_highlights_selected_agent(self):
        """Test that selected agent is highlighted with indicator."""
        entries = [
            ("agent1", "Agent One", "Description 1"),
            ("agent2", "Agent Two", "Description 2"),
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should have selection indicator
        assert "▶" in text

    def test_marks_current_agent(self):
        """Test that current agent is marked."""
        entries = [
            ("agent1", "Agent One", "Description 1"),
            ("agent2", "Agent Two", "Description 2"),
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name="agent2"
        )

        text = _get_text_from_formatted(result)
        assert "current" in text

    def test_pagination_page_zero(self):
        """Test pagination shows correct info for page 0."""
        # Create 25 agents for multiple pages
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}") for i in range(25)
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should show page 1 of 3 (25 agents / 10 per page = 3 pages)
        assert "Page 1/3" in text
        # First agent should be visible
        assert "Agent 00" in text

    def test_pagination_page_one(self):
        """Test pagination shows correct info for page 1."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}") for i in range(25)
        ]

        result = _render_menu_panel(
            entries, page=1, selected_idx=10, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should show page 2 of 3
        assert "Page 2/3" in text
        # Agent from page 2 should be visible
        assert "Agent 10" in text

    def test_pagination_last_page(self):
        """Test pagination shows correct info for last page."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}") for i in range(25)
        ]

        result = _render_menu_panel(
            entries, page=2, selected_idx=20, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should show page 3 of 3
        assert "Page 3/3" in text

    def test_shows_navigation_hints(self):
        """Test that navigation hints are displayed."""
        result = _render_menu_panel([], page=0, selected_idx=0, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "↑↓" in text
        assert "←→" in text
        assert "Enter" in text
        assert "Ctrl+C" in text
        assert "Navigate" in text
        assert "Page" in text
        assert "Select" in text
        assert "Cancel" in text

    def test_shows_agents_header(self):
        """Test that Agents header is displayed."""
        result = _render_menu_panel([], page=0, selected_idx=0, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Agents" in text

    def test_selected_agent_on_second_page(self):
        """Test selection highlighting works on second page."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}") for i in range(15)
        ]

        # Select agent 12 on page 1 (indices 10-14)
        result = _render_menu_panel(
            entries, page=1, selected_idx=12, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        assert "▶" in text
        assert "Agent 12" in text

    def test_current_agent_indicator_with_selection(self):
        """Test that both selection and current markers can appear."""
        entries = [
            ("agent1", "Agent One", "Description 1"),
            ("agent2", "Agent Two", "Description 2"),
        ]

        # Select agent2 which is also the current agent
        result = _render_menu_panel(
            entries, page=0, selected_idx=1, current_agent_name="agent2"
        )

        text = _get_text_from_formatted(result)
        assert "▶" in text  # Selection
        assert "current" in text  # Current marker


class TestRenderPreviewPanel:
    """Test the _render_preview_panel function."""

    def test_renders_no_selection(self):
        """Test rendering when no agent is selected."""
        result = _render_preview_panel(entry=None, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "No agent selected" in text
        assert "AGENT DETAILS" in text

    def test_renders_agent_name(self):
        """Test that agent name is displayed."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Name:" in text
        assert "code_puppy" in text

    def test_renders_display_name(self):
        """Test that display name is shown.

        Note: Emojis are stripped from display names for clean terminal rendering.
        """
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Display Name:" in text
        # Emojis are sanitized for clean terminal rendering
        assert "Code Puppy" in text

    def test_renders_description(self):
        """Test that description is displayed."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly coding assistant dog.")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Description:" in text
        assert "friendly" in text

    def test_renders_status_not_active(self):
        """Test that status shows 'Not active' for non-current agent."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.")

        result = _render_preview_panel(entry, current_agent_name="other_agent")

        text = _get_text_from_formatted(result)
        assert "Status:" in text
        assert "Not active" in text

    def test_renders_status_currently_active(self):
        """Test that status shows active for current agent."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.")

        result = _render_preview_panel(entry, current_agent_name="code_puppy")

        text = _get_text_from_formatted(result)
        assert "Status:" in text
        assert "Currently Active" in text
        assert "✓" in text

    def test_renders_header(self):
        """Test that AGENT DETAILS header is displayed."""
        entry = ("agent1", "Agent One", "Description")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "AGENT DETAILS" in text

    def test_handles_multiline_description(self):
        """Test handling of descriptions with multiple lines."""
        entry = (
            "test_agent",
            "Test Agent",
            "First line of description.\nSecond line of description.\nThird line.",
        )

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "First line" in text
        assert "Second line" in text
        assert "Third line" in text

    def test_handles_long_description(self):
        """Test handling of very long descriptions that need word wrapping."""
        long_description = (
            "This is a very long description that should be wrapped appropriately "
            "to fit within the preview panel boundaries without causing display issues."
        )
        entry = ("test_agent", "Test Agent", long_description)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        # Should contain parts of the description
        assert "very long description" in text
        assert "wrapped" in text

    def test_handles_empty_description(self):
        """Test handling of empty description."""
        entry = ("test_agent", "Test Agent", "")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        # Should still render other fields
        assert "Name:" in text
        assert "test_agent" in text
        assert "Display Name:" in text

    def test_handles_description_with_special_characters(self):
        """Test handling of descriptions with emojis and special chars."""
        entry = (
            "emoji_agent",
            "Emoji Agent 🎉",
            "An agent with emojis 🐶🐱 and special chars: <>&",
        )

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Emoji Agent" in text


class TestGetAgentEntriesIntegration:
    """Integration-style tests for _get_agent_entries behavior."""

    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_typical_usage_scenario(self, mock_available, mock_descriptions):
        """Test a typical usage scenario with realistic agent data."""
        mock_available.return_value = {
            "code_puppy": "Code Puppy 🐶",
            "pack_leader": "Pack Leader 🦮",
            "code_reviewer": "Code Reviewer 🔍",
        }
        mock_descriptions.return_value = {
            "code_puppy": "A friendly AI coding assistant.",
            "pack_leader": "Coordinates the pack of specialized agents.",
            "code_reviewer": "Reviews code for quality and best practices.",
        }

        result = _get_agent_entries()

        assert len(result) == 3
        # Should be sorted alphabetically
        assert result[0][0] == "code_puppy"
        assert result[1][0] == "code_reviewer"
        assert result[2][0] == "pack_leader"

        # Check full tuple structure
        assert result[0] == (
            "code_puppy",
            "Code Puppy 🐶",
            "A friendly AI coding assistant.",
        )


class TestRenderPanelEdgeCases:
    """Test edge cases for rendering functions."""

    def test_menu_panel_with_exact_page_size_entries(self):
        """Test menu panel when entries exactly match PAGE_SIZE."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}")
            for i in range(PAGE_SIZE)
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should show page 1 of 1
        assert "Page 1/1" in text

    def test_menu_panel_with_page_size_plus_one(self):
        """Test menu panel when entries are PAGE_SIZE + 1."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}")
            for i in range(PAGE_SIZE + 1)
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should show page 1 of 2
        assert "Page 1/2" in text

    def test_menu_panel_last_item_on_page_selected(self):
        """Test selection of last item on a page."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}") for i in range(15)
        ]

        # Select the last item on page 0 (index 9)
        result = _render_menu_panel(
            entries, page=0, selected_idx=9, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        assert "▶" in text
        assert "Agent 09" in text

    def test_preview_panel_with_no_description_default(self):
        """Test preview panel shows default description."""
        entry = ("minimal_agent", "Minimal Agent", "No description available")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "No description available" in text


class TestMenuPanelStyling:
    """Test styling aspects of the menu panel."""

    def test_styling_includes_green_for_selection(self):
        """Test that selection styling uses green color."""
        entries = [("agent1", "Agent One", "Description")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        # Check that green styling is applied somewhere
        styles = [style for style, _ in result]
        has_green = any("green" in str(style).lower() for style in styles)
        assert has_green, "Selection should use green styling"

    def test_styling_includes_cyan_for_current(self):
        """Test that current agent marker uses cyan color."""
        entries = [("agent1", "Agent One", "Description")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name="agent1"
        )

        # Check that cyan styling is used for current marker
        styles = [style for style, _ in result]
        has_cyan = any("cyan" in str(style).lower() for style in styles)
        assert has_cyan, "Current marker should use cyan styling"


class TestPreviewPanelStyling:
    """Test styling aspects of the preview panel."""

    def test_styling_for_active_status(self):
        """Test that active status uses appropriate styling."""
        entry = ("agent1", "Agent One", "Description")

        result = _render_preview_panel(entry, current_agent_name="agent1")

        # Check for green styling on active status
        styles = [style for style, _ in result]
        has_green = any("green" in str(style).lower() for style in styles)
        assert has_green, "Active status should use green styling"

    def test_styling_for_inactive_status(self):
        """Test that inactive status uses dimmed styling."""
        entry = ("agent1", "Agent One", "Description")

        result = _render_preview_panel(entry, current_agent_name="other_agent")

        # Check for dimmed/bright black styling
        styles = [style for style, _ in result]
        has_dim = any("bright" in str(style).lower() for style in styles)
        assert has_dim, "Inactive status should use dimmed styling"
