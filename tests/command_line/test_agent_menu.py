"""Comprehensive test coverage for agent_menu.py UI components.

Covers menu initialization, agent entry retrieval, rendering,
pagination, current agent marking, and preview panel display.
"""

from unittest.mock import patch

from code_puppy.command_line.agent_menu import (
    PAGE_SIZE,
    _apply_pinned_model,
    _get_agent_entries,
    _get_pinned_model,
    _render_menu_panel,
    _render_preview_panel,
    _select_clone_location,
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

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_single_agent(self, mock_available, mock_descriptions, _mock_path):
        """Test that single agent is returned correctly."""
        mock_available.return_value = {"code_puppy": "Code Puppy 🐶"}
        mock_descriptions.return_value = {"code_puppy": "A friendly coding assistant."}

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0] == (
            "code_puppy",
            "Code Puppy 🐶",
            "A friendly coding assistant.",
            None,
            None,
        )

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_multiple_agents_sorted(self, mock_available, mock_descriptions, _mock_path):
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

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_handles_missing_description(self, mock_available, mock_descriptions, _mock_path):
        """Test that missing descriptions get default value."""
        mock_available.return_value = {"test_agent": "Test Agent"}
        mock_descriptions.return_value = {}  # No description for this agent

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0] == ("test_agent", "Test Agent", "No description available", None, None)

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_handles_extra_descriptions(self, mock_available, mock_descriptions, _mock_path):
        """Test that extra descriptions (without matching agents) are ignored."""
        mock_available.return_value = {"agent1": "Agent One"}
        mock_descriptions.return_value = {
            "agent1": "Description for agent1",
            "agent2": "Description for non-existent agent",
        }

        result = _get_agent_entries()

        assert len(result) == 1
        assert result[0][0] == "agent1"

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_sorts_case_insensitive(self, mock_available, mock_descriptions, _mock_path):
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

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_returns_more_than_page_size(self, mock_available, mock_descriptions, _mock_path):
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
        entries = [("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)]

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
            ("agent1", "Agent One", "Description 1", None, None),
            ("agent2", "Agent Two", "Description 2", None, None),
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
            ("agent1", "Agent One", "Description 1", None, None),
            ("agent2", "Agent Two", "Description 2", None, None),
        ]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name="agent2"
        )

        text = _get_text_from_formatted(result)
        assert "current" in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_shows_pinned_model_marker(self, mock_pinned_model):
        """Test that pinned models are displayed in the menu."""
        mock_pinned_model.return_value = "gpt-4"
        entries = [("agent1", "Agent One", "Description 1", None, None)]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        text = _get_text_from_formatted(result)
        assert "gpt-4" in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_unpinned_model_shows_no_marker(self, mock_pinned_model):
        """Test that unpinned agents show no pinned model marker."""
        mock_pinned_model.return_value = None
        entries = [("agent1", "Agent One", "Description 1", None, None)]

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

    def test_pagination_page_zero(self):
        """Test pagination shows correct info for page 0."""
        # Create 25 agents for multiple pages
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None) for i in range(25)
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
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None) for i in range(25)
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
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None) for i in range(25)
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

    def test_selected_agent_on_second_page(self):
        """Test selection highlighting works on second page."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None) for i in range(15)
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
            ("agent1", "Agent One", "Description 1", None, None),
            ("agent2", "Agent Two", "Description 2", None, None),
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
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Name:" in text
        assert "code_puppy" in text

    def test_renders_display_name(self):
        """Test that display name is shown.

        Note: Emojis are stripped from display names for clean terminal rendering.
        """
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Display Name:" in text
        # Emojis are sanitized for clean terminal rendering
        assert "Code Puppy" in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_renders_pinned_model(self, mock_pinned_model):
        """Test that pinned model is shown in the preview panel."""
        mock_pinned_model.return_value = "gpt-4"
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Pinned Model:" in text
        assert "gpt-4" in text

    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_renders_unpinned_model_shows_default(self, mock_pinned_model):
        """Test that unpinned model shows 'default' in preview."""
        mock_pinned_model.return_value = None
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Pinned Model:" in text
        assert "default" in text

    def test_renders_description(self):
        """Test that description is displayed."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly coding assistant dog.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Description:" in text
        assert "friendly" in text

    def test_renders_status_not_active(self):
        """Test that status shows 'Not active' for non-current agent."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="other_agent")

        text = _get_text_from_formatted(result)
        assert "Status:" in text
        assert "Not active" in text

    def test_renders_status_currently_active(self):
        """Test that status shows active for current agent."""
        entry = ("code_puppy", "Code Puppy 🐶", "A friendly assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="code_puppy")

        text = _get_text_from_formatted(result)
        assert "Status:" in text
        assert "Currently Active" in text
        assert "✓" in text

    def test_renders_header(self):
        """Test that AGENT DETAILS header is displayed."""
        entry = ("agent1", "Agent One", "Description", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "AGENT DETAILS" in text

    def test_handles_multiline_description(self):
        """Test handling of descriptions with multiple lines."""
        entry = (
            "test_agent",
            "Test Agent",
            "First line of description.\nSecond line of description.\nThird line.",
            None,
            None,
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
        entry = ("test_agent", "Test Agent", long_description, None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        # Should contain parts of the description
        assert "very long description" in text
        assert "wrapped" in text

    def test_handles_empty_description(self):
        """Test handling of empty description."""
        entry = ("test_agent", "Test Agent", "", None, None)

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
            None,
            None,
        )

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Emoji Agent" in text


class TestGetAgentEntriesIntegration:
    """Integration-style tests for _get_agent_entries behavior."""

    @patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_agent_descriptions")
    @patch("code_puppy.command_line.agent_menu.get_available_agents")
    def test_typical_usage_scenario(self, mock_available, mock_descriptions, _mock_path):
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
            None,
            None,
        )


class TestRenderPanelEdgeCases:
    """Test edge cases for rendering functions."""

    def test_menu_panel_with_exact_page_size_entries(self):
        """Test menu panel when entries exactly match PAGE_SIZE."""
        entries = [
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None)
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
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None)
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
            (f"agent_{i:02d}", f"Agent {i:02d}", f"Desc {i:02d}", None, None) for i in range(15)
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
        entry = ("minimal_agent", "Minimal Agent", "No description available", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "No description available" in text


class TestMenuPanelStyling:
    """Test styling aspects of the menu panel."""

    def test_styling_includes_green_for_selection(self):
        """Test that selection styling uses green color."""
        entries = [("agent1", "Agent One", "Description", None, None)]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=""
        )

        # Check that green styling is applied somewhere
        styles = [style for style, _ in result]
        has_green = any("green" in str(style).lower() for style in styles)
        assert has_green, "Selection should use green styling"

    def test_styling_includes_cyan_for_current(self):
        """Test that current agent marker uses cyan color."""
        entries = [("agent1", "Agent One", "Description", None, None)]

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
        entry = ("agent1", "Agent One", "Description", None, None)

        result = _render_preview_panel(entry, current_agent_name="agent1")

        # Check for green styling on active status
        styles = [style for style, _ in result]
        has_green = any("green" in str(style).lower() for style in styles)
        assert has_green, "Active status should use green styling"

    def test_styling_for_inactive_status(self):
        """Test that inactive status uses dimmed styling."""
        entry = ("agent1", "Agent One", "Description", None, None)

        result = _render_preview_panel(entry, current_agent_name="other_agent")

        # Check for dimmed/bright black styling
        styles = [style for style, _ in result]
        has_dim = any("bright" in str(style).lower() for style in styles)
        assert has_dim, "Inactive status should use dimmed styling"


class TestGetPinnedModelWithJSONAgents:
    """Test _get_pinned_model function with JSON agents."""

    @patch("code_puppy.agents.json_agent.discover_json_agents")
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_returns_builtin_agent_pinned_model(self, mock_builtin, mock_json_agents):
        """Test that built-in agent pinned model is returned."""
        mock_builtin.return_value = "gpt-4"
        mock_json_agents.return_value = {}

        result = _get_pinned_model("code_puppy")

        assert result == "gpt-4"

    @patch("code_puppy.agents.json_agent.discover_json_agents")
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_returns_json_agent_pinned_model(self, mock_builtin, mock_json_agents):
        """Test that JSON agent pinned model is returned."""
        import json
        import tempfile

        mock_builtin.return_value = None

        # Create a temporary JSON agent file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test_agent", "model": "claude-3-opus"}, f)
            json_file = f.name

        mock_json_agents.return_value = {"test_agent": json_file}

        result = _get_pinned_model("test_agent")

        assert result == "claude-3-opus"

        # Clean up
        import os

        os.unlink(json_file)

    @patch("code_puppy.agents.json_agent.discover_json_agents")
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_returns_none_for_unpinned_json_agent(self, mock_builtin, mock_json_agents):
        """Test that None is returned for JSON agent without pinned model."""
        import json
        import tempfile

        mock_builtin.return_value = None

        # Create a temporary JSON agent file without model key
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test_agent"}, f)
            json_file = f.name

        mock_json_agents.return_value = {"test_agent": json_file}

        result = _get_pinned_model("test_agent")

        assert result is None

        # Clean up
        import os

        os.unlink(json_file)

    @patch("code_puppy.agents.json_agent.discover_json_agents")
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_handles_json_agent_read_error(self, mock_builtin, mock_json_agents):
        """Test that read errors are handled gracefully."""
        mock_builtin.return_value = None
        mock_json_agents.return_value = {"test_agent": "/nonexistent/file.json"}

        result = _get_pinned_model("test_agent")

        assert result is None

    @patch("code_puppy.agents.json_agent.discover_json_agents")
    @patch("code_puppy.command_line.agent_menu.get_agent_pinned_model")
    def test_builtin_takes_precedence_over_json(self, mock_builtin, mock_json_agents):
        """Test that built-in pinned model takes precedence."""
        import json
        import tempfile

        mock_builtin.return_value = "gpt-4"

        # Create a temporary JSON agent file with different model
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "code_puppy", "model": "claude-3-opus"}, f)
            json_file = f.name

        mock_json_agents.return_value = {"code_puppy": json_file}

        result = _get_pinned_model("code_puppy")

        # Built-in should take precedence
        assert result == "gpt-4"

        # Clean up
        import os

        os.unlink(json_file)


class TestApplyPinnedModelWithJSONAgents:
    """Test _apply_pinned_model function with JSON agents."""

    @patch("code_puppy.command_line.agent_menu.set_agent_pinned_model")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_pins_builtin_agent(
        self, mock_json_agents, mock_reload, mock_emit, mock_set_pin
    ):
        """Test that built-in agents use config functions."""
        mock_json_agents.return_value = {}

        _apply_pinned_model("code_puppy", "gpt-4")

        mock_set_pin.assert_called_once_with("code_puppy", "gpt-4")
        mock_reload.assert_called_once_with("code_puppy", "gpt-4")

    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_pins_json_agent(self, mock_json_agents, mock_reload, mock_emit):
        """Test that JSON agents have model written to file."""
        import json
        import tempfile

        # Create a temporary JSON agent file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test_agent"}, f)
            json_file = f.name

        mock_json_agents.return_value = {"test_agent": json_file}

        _apply_pinned_model("test_agent", "claude-3-opus")

        # Verify the file was updated
        with open(json_file, "r") as f:
            agent_config = json.load(f)

        assert agent_config.get("model") == "claude-3-opus"
        mock_reload.assert_called_once_with("test_agent", "claude-3-opus")

        # Clean up
        import os

        os.unlink(json_file)

    @patch("code_puppy.command_line.agent_menu.clear_agent_pinned_model")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_unpins_builtin_agent(
        self, mock_json_agents, mock_reload, mock_emit, mock_clear_pin
    ):
        """Test that built-in agents have pin cleared via config."""
        mock_json_agents.return_value = {}

        _apply_pinned_model("code_puppy", "(unpin)")

        mock_clear_pin.assert_called_once_with("code_puppy")
        mock_reload.assert_called_once_with("code_puppy", None)

    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu._reload_agent_if_current")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_unpins_json_agent(self, mock_json_agents, mock_reload, mock_emit):
        """Test that JSON agents have model key removed."""
        import json
        import tempfile

        # Create a temporary JSON agent file with model key
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test_agent", "model": "claude-3-opus"}, f)
            json_file = f.name

        mock_json_agents.return_value = {"test_agent": json_file}

        _apply_pinned_model("test_agent", "(unpin)")

        # Verify the model key was removed
        with open(json_file, "r") as f:
            agent_config = json.load(f)

        assert "model" not in agent_config
        mock_reload.assert_called_once_with("test_agent", None)

        # Clean up
        import os

        os.unlink(json_file)

    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.command_line.agent_menu.emit_warning")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_handles_json_agent_write_error(
        self, mock_json_agents, mock_emit_warning, mock_emit_success
    ):
        """Test that write errors are handled gracefully."""
        # Use a directory path instead of a file path to cause an error
        mock_json_agents.return_value = {"test_agent": "/"}

        _apply_pinned_model("test_agent", "claude-3-opus")

        # Should emit a warning instead of crashing
        assert mock_emit_warning.called


class TestRenderPreviewPanelPath:
    """Test that the preview panel shows the agent source path."""

    def test_shows_path_field_for_json_agent(self):
        """Test that Path: field is displayed for JSON agents."""
        entry = ("my-agent", "My Agent", "Does things.", "/home/user/.code_puppy/agents/my-agent.json", None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Path:" in text
        assert "/home/user/.code_puppy/agents/my-agent.json" in text

    def test_shows_builtin_for_python_agent(self):
        """Test that 'built-in' is shown when source path is None."""
        entry = ("code-puppy", "Code Puppy", "General assistant.", None, None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "Path:" in text
        assert "built-in" in text

    def test_path_field_between_display_name_and_pinned_model(self):
        """Test that Path: appears after Display Name and before Pinned Model."""
        entry = ("my-agent", "My Agent", "Does things.", "/some/path/my-agent.json", None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        display_pos = text.index("Display Name:")
        path_pos = text.index("Path:")
        pinned_pos = text.index("Pinned Model:")
        assert display_pos < path_pos < pinned_pos

    def test_path_uses_project_dir(self):
        """Test that a project-level agent path is shown correctly."""
        entry = (
            "team-agent",
            "Team Agent",
            "Shared agent.",
            "/project/.code_puppy/agents/team-agent.json",
            None,
        )

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "/project/.code_puppy/agents/team-agent.json" in text

    def test_shows_shadowed_path_when_project_overrides_user(self):
        """Test that both paths and a warning are shown when a project agent shadows a user agent."""
        user_path = "/home/user/.code_puppy/agents/readme-writer.json"
        project_path = "/project/.code_puppy/agents/readme-writer.json"
        entry = ("readme-writer", "Readme Writer", "Writes readmes.", project_path, user_path)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert project_path in text
        assert user_path in text
        assert "overrides" in text
        assert "shadows" in text

    def test_no_shadow_warning_when_no_conflict(self):
        """Test that no shadow warning appears when there is no override."""
        entry = ("my-agent", "My Agent", "Does things.", "/home/user/.code_puppy/agents/my-agent.json", None)

        result = _render_preview_panel(entry, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "overrides" not in text
        assert "shadows" not in text

    def test_menu_row_no_warning_badge_for_shadowed_agent(self):
        """Test that the menu row does NOT show a warning badge (warning is details-only)."""
        entries = [
            ("readme-writer", "Readme Writer", "desc",
             "/project/.code_puppy/agents/readme-writer.json",
             "/home/user/.code_puppy/agents/readme-writer.json"),
        ]

        result = _render_menu_panel(entries, page=0, selected_idx=0, current_agent_name="")

        text = _get_text_from_formatted(result)
        assert "overrides" not in text

    def test_get_agent_entries_includes_path_for_json_agent(self):
        """Test that _get_agent_entries includes the source path from get_agent_source_path."""
        fake_path = "/home/user/.code_puppy/agents/custom.json"

        with (
            patch("code_puppy.command_line.agent_menu.get_available_agents", return_value={"custom": "Custom Agent"}),
            patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={"custom": "A custom agent."}),
            patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=fake_path),
            patch("code_puppy.command_line.agent_menu.get_agent_shadowed_path", return_value=None),
        ):
            result = _get_agent_entries()

        assert len(result) == 1
        assert result[0] == ("custom", "Custom Agent", "A custom agent.", fake_path, None)

    def test_get_agent_entries_path_is_none_for_python_agent(self):
        """Test that _get_agent_entries returns None path for built-in Python agents."""
        with (
            patch("code_puppy.command_line.agent_menu.get_available_agents", return_value={"code-puppy": "Code Puppy"}),
            patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={"code-puppy": "Default agent."}),
            patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=None),
        ):
            result = _get_agent_entries()

        assert len(result) == 1
        assert result[0][3] is None
        assert result[0][4] is None

    def test_get_agent_entries_includes_shadowed_path(self):
        """Test that _get_agent_entries propagates the shadowed path."""
        project_path = "/project/.code_puppy/agents/my-agent.json"
        user_path = "/home/user/.code_puppy/agents/my-agent.json"

        with (
            patch("code_puppy.command_line.agent_menu.get_available_agents", return_value={"my-agent": "My Agent"}),
            patch("code_puppy.command_line.agent_menu.get_agent_descriptions", return_value={"my-agent": "An agent."}),
            patch("code_puppy.command_line.agent_menu.get_agent_source_path", return_value=project_path),
            patch("code_puppy.command_line.agent_menu.get_agent_shadowed_path", return_value=user_path),
        ):
            result = _get_agent_entries()

        assert len(result) == 1
        assert result[0][3] == project_path
        assert result[0][4] == user_path


class TestSelectCloneLocation:
    """Test the _select_clone_location async function."""

    @patch("code_puppy.command_line.agent_menu.arrow_select_async")
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value=None)
    async def test_returns_user_dir_when_selected(self, _mock_proj, _mock_user, mock_arrow):
        """Test that user directory Path is returned when user selects it."""
        mock_arrow.return_value = "User directory (~/.code_puppy/agents/)"

        result = await _select_clone_location()

        from pathlib import Path
        assert result == Path("/home/user/.code_puppy/agents")

    @patch("code_puppy.command_line.agent_menu.arrow_select_async")
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value="/project/.code_puppy/agents")
    async def test_returns_project_dir_when_selected(self, _mock_proj, _mock_user, mock_arrow):
        """Test that project directory Path is returned when user selects it."""
        mock_arrow.return_value = "Project directory (.code_puppy/agents/)"

        result = await _select_clone_location()

        from pathlib import Path
        assert result == Path("/project/.code_puppy/agents")

    @patch("code_puppy.command_line.agent_menu.arrow_select_async")
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value=None)
    async def test_only_user_dir_offered_without_project_dir(self, _mock_proj, _mock_user, mock_arrow):
        """Test that project directory option is not offered when project dir doesn't exist."""
        mock_arrow.return_value = "User directory (~/.code_puppy/agents/)"

        await _select_clone_location()

        _call_args = mock_arrow.call_args
        choices_passed = _call_args[0][1]
        assert len(choices_passed) == 1
        assert not any("Project" in c for c in choices_passed)

    @patch("code_puppy.command_line.agent_menu.arrow_select_async")
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value="/project/.code_puppy/agents")
    async def test_both_options_offered_with_project_dir(self, _mock_proj, _mock_user, mock_arrow):
        """Test that both options are offered when project dir exists."""
        mock_arrow.return_value = "User directory (~/.code_puppy/agents/)"

        await _select_clone_location()

        _call_args = mock_arrow.call_args
        choices_passed = _call_args[0][1]
        assert len(choices_passed) == 2
        assert any("User" in c for c in choices_passed)
        assert any("Project" in c for c in choices_passed)

    @patch("code_puppy.command_line.agent_menu.emit_info")
    @patch("code_puppy.command_line.agent_menu.arrow_select_async", side_effect=KeyboardInterrupt)
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value=None)
    async def test_returns_none_on_keyboard_interrupt(self, _mock_proj, _mock_user, _mock_arrow, mock_emit):
        """Test that None is returned and info emitted when user cancels with Ctrl+C."""
        result = await _select_clone_location()

        assert result is None
        mock_emit.assert_called_once()

    @patch("code_puppy.command_line.agent_menu.arrow_select_async", return_value=None)
    @patch("code_puppy.command_line.agent_menu.get_user_agents_directory", return_value="/home/user/.code_puppy/agents")
    @patch("code_puppy.command_line.agent_menu.get_project_agents_directory", return_value=None)
    async def test_returns_none_when_no_choice_made(self, _mock_proj, _mock_user, _mock_arrow):
        """Test that None is returned when arrow_select_async returns None."""
        result = await _select_clone_location()

        assert result is None
