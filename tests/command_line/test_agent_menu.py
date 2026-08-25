"""Comprehensive test coverage for agent_menu.py UI components.

Covers menu initialization, agent entry retrieval, rendering,
pagination, current agent marking, and preview panel display.
"""

from unittest.mock import patch

import pytest

from code_puppy.command_line.agent_menu import (
    PAGE_SIZE,
    _agent_items,
    _get_agent_entries,
    _render_agent_details,
    build_agent_menu,
)


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


class TestAgentItems:
    """Test the _agent_items row builder."""

    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_labels_and_markers(self, mock_pinned):
        mock_pinned.return_value = None
        entries = [
            ("agent1", "Agent One", "First"),
            ("agent2", "Agent Two", "Second"),
        ]
        items = _agent_items(entries, current_agent_name="agent2")

        assert [it.value for it in items] == ["agent1", "agent2"]
        assert items[0].label == "Agent One"
        assert items[0].description == ""
        assert "(current)" in items[1].description

    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_pinned_model_marker(self, mock_pinned):
        mock_pinned.return_value = "gpt-5"
        items = _agent_items([("a", "A", "desc")], current_agent_name="")
        assert "-> gpt-5" in items[0].description

    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_display_names_are_sanitized(self, mock_pinned):
        mock_pinned.return_value = None
        items = _agent_items([("a", "Agent \U0001f436 One", "d")], "")
        assert items[0].label == "Agent One"


class TestRenderAgentDetails:
    """Test the ANSI preview pane."""

    @patch("code_puppy.command_line.agent_menu.get_bound_servers")
    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_renders_core_fields(self, mock_pinned, mock_bound):
        mock_pinned.return_value = None
        mock_bound.return_value = {}
        details = _render_agent_details(("a1", "Agent One", "Does things."), "a1")

        assert "AGENT DETAILS" in details
        assert "a1" in details
        assert "Agent One" in details
        assert "default" in details  # unpinned model
        assert "none bound (strict opt-in)" in details
        assert "Does things." in details
        assert "Currently Active" in details

    @patch("code_puppy.command_line.agent_menu.get_bound_servers")
    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_renders_pinned_and_bindings(self, mock_pinned, mock_bound):
        mock_pinned.return_value = "gpt-5"
        mock_bound.return_value = {
            "srv1": {"auto_start": True},
            "srv2": {},
        }
        details = _render_agent_details(("a1", "Agent One", "d"), "other")

        assert "gpt-5" in details
        assert "2 bound (1 auto-start)" in details
        assert "Not active" in details

    @patch("code_puppy.command_line.agent_menu.get_bound_servers")
    @patch("code_puppy.command_line.agent_menu._get_pinned_model")
    def test_long_description_is_wrapped(self, mock_pinned, mock_bound):
        mock_pinned.return_value = None
        mock_bound.return_value = {}
        long_desc = "word " * 40
        details = _render_agent_details(("a1", "A", long_desc), "")
        assert all(len(line) <= 60 for line in details.splitlines() if "word" in line)


class TestBuildAgentMenu:
    """Drive the termflow menu headlessly with scripted keys."""

    def _drive(self, keys, entries, current="", initial=0):
        from io import StringIO

        script = iter(keys)
        out = StringIO()
        pending = {"action": None}
        with (
            patch(
                "code_puppy.command_line.agent_menu._get_pinned_model",
                return_value=None,
            ),
            patch(
                "code_puppy.command_line.agent_menu.get_bound_servers",
                return_value={},
            ),
        ):
            menu = build_agent_menu(
                entries,
                current,
                pending,
                initial,
                key_source=lambda: next(script),
                output=out,
                size=lambda: (120, 40),
                alt_screen=False,
            )
            result = menu.run()
        return result, pending, out.getvalue()

    ENTRIES = [
        ("agent1", "Agent One", "First agent"),
        ("agent2", "Agent Two", "Second agent"),
        ("agent3", "Agent Three", "Third agent"),
    ]

    def test_enter_selects_highlighted(self):
        result, pending, _ = self._drive(["down", "enter"], self.ENTRIES)
        assert result.item.value == "agent2"
        assert pending["action"] is None

    def test_escape_cancels(self):
        result, _, _ = self._drive(["escape"], self.ENTRIES)
        assert result.cancelled

    def test_initial_index_preselects(self):
        result, _, _ = self._drive(["enter"], self.ENTRIES, initial=2)
        assert result.item.value == "agent3"

    @pytest.mark.parametrize(
        "key,action", [("p", "pin"), ("b", "bind"), ("c", "clone"), ("d", "delete")]
    )
    def test_action_keys_exit_with_pending_action(self, key, action):
        result, pending, _ = self._drive([key], self.ENTRIES)
        assert pending["action"] == action
        assert result.item.value == "agent1"

    def test_current_agent_marked(self):
        _, _, screen = self._drive(["escape"], self.ENTRIES, current="agent2")
        assert "(current)" in screen

    def test_pagination_hides_offpage_agents(self):
        entries = [(f"agent{i:02d}", f"Agent {i:02d}", "d") for i in range(25)]
        _, _, screen = self._drive(["escape"], entries)
        from termflow.ansi.utils import visible

        text = visible(screen)
        assert "Agent 00" in text
        assert "Agent 15" not in text
