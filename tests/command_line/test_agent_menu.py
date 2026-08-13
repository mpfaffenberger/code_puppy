"""Comprehensive test coverage for agent_menu.py UI components.

Covers menu initialization, agent entry retrieval, rendering,
pagination, current agent marking, and preview panel display.
"""

from unittest.mock import patch

import pytest

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

    @pytest.mark.parametrize(
        ("current", "frag"),
        [("", "▶"), ("agent2", "current")],
        ids=["highlights_selected_agent", "marks_current_agent"],
    )
    def test_selection_and_current_marker(self, current, frag):
        """Test that the selected agent is highlighted and current agent marked."""
        entries = [
            ("agent1", "Agent One", "Description 1"),
            ("agent2", "Agent Two", "Description 2"),
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=current
        )

        text = _get_text_from_formatted(result)
        assert frag in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_shows_pinned_model_marker(self, mock_pinned_model):
        """Test that pinned models are displayed in the menu."""
        mock_pinned_model.return_value = "gpt-4"
        entries = [("agent1", "Agent One", "Description 1")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        assert "gpt-4" in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_unpinned_model_shows_no_marker(self, mock_pinned_model):
        """Test that unpinned agents show no pinned model marker."""
        mock_pinned_model.return_value = None
        entries = [("agent1", "Agent One", "Description 1")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        # Should not show any model name after the agent name
        assert "Agent One\n" in text or result[-3][1] == "Agent One"
        # Verify no arrow/pinned indicator
        lines = text.split("\n")
        agent_line = [line for line in lines if "Agent One" in line]
        assert len(agent_line) == 1
        assert "→" not in agent_line[0]

    @pytest.mark.parametrize(
        ("n_entries", "page", "selected_idx", "frag1", "frag2"),
        [
            (25, 0, 0, "Page 1/3", "Agent 00"),
            (25, 1, 10, "Page 2/3", "Agent 10"),
            (15, 1, 12, "▶", "Agent 12"),
            (15, 0, 9, "▶", "Agent 09"),
        ],
        ids=[
            "pagination_page_zero",
            "pagination_page_one",
            "selected_agent_on_second_page",
            "menu_panel_last_item_on_page_selected",
        ],
    )
    def test_pagination(self, n_entries, page, selected_idx, frag1, frag2):
        """Test pagination info and selection highlighting."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}")
            for i in range(n_entries)
        ]

        result = _render_menu_panel(
            entries, page=page, selected_idx=selected_idx, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        assert frag1 in text
        assert frag2 in text

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
        assert "P" in text
        assert "Pin model" in text
        assert "C" in text
        assert "Clone" in text
        assert "D" in text
        assert "Delete clone" in text
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

    @pytest.mark.parametrize(
        ("entry", "current", "frag1", "frag2"),
        [
            (
                ("code_puppy", "Code Puppy ", "A friendly assistant."),
                "",
                "Name:",
                "code_puppy",
            ),
            (
                ("code_puppy", "Code Puppy ", "A friendly assistant."),
                "",
                "Display Name:",
                "Code Puppy",
            ),
            (
                ("code_puppy", "Code Puppy ", "A friendly coding assistant dog."),
                "",
                "Description:",
                "friendly",
            ),
            (
                ("code_puppy", "Code Puppy ", "A friendly assistant."),
                "other_agent",
                "Status:",
                "Not active",
            ),
        ],
        ids=[
            "renders_agent_name",
            "renders_display_name",
            "renders_description",
            "renders_status_not_active",
        ],
    )
    def test_renders_preview_fields(self, entry, current, frag1, frag2):
        """Test that core preview fields are displayed."""
        result = _render_preview_panel(entry, current_agent_name=current)

        text = _get_text_from_formatted(result)
        assert frag1 in text
        assert frag2 in text

    @pytest.mark.parametrize(
        ("pinned", "frag"),
        [("gpt-4", "gpt-4"), (None, "default")],
        ids=["renders_pinned_model", "renders_unpinned_model_shows_default"],
    )
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_renders_pinned_model(self, mock_pinned_model, pinned, frag):
        """Test that pinned model (or default) is shown in the preview panel."""
        mock_pinned_model.return_value = pinned
        entry = ("code_puppy", "Code Puppy ", "A friendly assistant.")

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Pinned Model:" in text
        assert frag in text

    @pytest.mark.parametrize(
        ("entry", "current", "frag1", "frag2", "frag3"),
        [
            (
                ("code_puppy", "Code Puppy ", "A friendly assistant."),
                "code_puppy",
                "Status:",
                "Currently Active",
                "",
            ),
            (
                (
                    "test_agent",
                    "Test Agent",
                    "First line of description.\nSecond line of description.\nThird line.",
                ),
                "",
                "First line",
                "Second line",
                "Third line",
            ),
            (
                ("test_agent", "Test Agent", ""),
                "",
                "Name:",
                "test_agent",
                "Display Name:",
            ),
        ],
        ids=[
            "renders_status_currently_active",
            "handles_multiline_description",
            "handles_empty_description",
        ],
    )
    def test_renders_status_and_description(self, entry, current, frag1, frag2, frag3):
        """Test status marker and multi-line/empty description rendering."""
        result = _render_preview_panel(entry, current_agent_name=current)

        text = _get_text_from_formatted(result)
        assert frag1 in text
        assert frag2 in text
        assert frag3 in text

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

    @pytest.mark.parametrize(
        ("entry", "frag"),
        [
            (("agent1", "Agent One", "Description"), "AGENT DETAILS"),
            (
                (
                    "emoji_agent",
                    "Emoji Agent ",
                    "An agent with emojis  and special chars: <>&",
                ),
                "Emoji Agent",
            ),
            (
                ("minimal_agent", "Minimal Agent", "No description available"),
                "No description available",
            ),
        ],
        ids=[
            "renders_header",
            "handles_description_with_special_characters",
            "preview_panel_with_no_description_default",
        ],
    )
    def test_renders_preview_fragment(self, entry, frag):
        """Test assorted preview panel fragments render correctly."""
        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert frag in text
