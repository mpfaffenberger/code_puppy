"""Additional agent_menu.py tests: JSON-agent pinning, edge cases, styling.

Split from test_agent_menu.py to keep files under 600 lines.
"""

from unittest.mock import patch

import pytest

from code_puppy.command_line.agent_menu import (
    PAGE_SIZE,
    _apply_pinned_model,
    _get_agent_entries,
    _get_pinned_model,
    _render_menu_panel,
    _render_preview_panel,
)


def _get_text_from_formatted(result):
    """Extract plain text from formatted text control output."""
    return "".join(text for _, text in result)


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



class TestMenuPanelStyling:
    """Test styling aspects of the menu panel."""

    @pytest.mark.parametrize(
        ("current", "style"),
        [("", "class:tui.selected"), ("agent1", "class:tui.success")],
        ids=["selection_uses_semantic_style", "current_marker_uses_semantic_success_style"],
    )
    def test_semantic_styles(self, current, style):
        """Test that selection and current markers use shared semantic roles."""
        entries = [("agent1", "Agent One", "Description")]

        result = _render_menu_panel(
            entries, page=0, selected_idx=0, current_agent_name=current
        )

        styles = [style for style, _ in result]
        assert style in styles


class TestPreviewPanelStyling:
    """Test styling aspects of the preview panel."""

    @pytest.mark.parametrize(
        ("current", "style"),
        [("agent1", "class:tui.success"), ("other_agent", "class:tui.muted")],
        ids=["styling_for_active_status", "styling_for_inactive_status"],
    )
    def test_status_styling(self, current, style):
        """Test that active/inactive status uses semantic roles."""
        entry = ("agent1", "Agent One", "Description")

        result = _render_preview_panel(entry, current_agent_name=current)

        styles = [style for style, _ in result]
        assert style in styles


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
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_pins_builtin_agent(self, mock_json_agents, mock_emit, mock_set_pin):
        """Test that built-in agents use config functions."""
        from code_puppy.command_line.agent_menu import consume_pending_pin_reloads

        consume_pending_pin_reloads()
        mock_json_agents.return_value = {}

        _apply_pinned_model("code_puppy", "gpt-4")

        mock_set_pin.assert_called_once_with("code_puppy", "gpt-4")
        # Reload is now deferred --- the request lands on the pending queue
        assert consume_pending_pin_reloads() == [("code_puppy", "gpt-4")]

    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_pins_json_agent(self, mock_json_agents, mock_emit):
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

        # Clean up
        import os

        os.unlink(json_file)

    @patch("code_puppy.command_line.agent_menu.clear_agent_pinned_model")
    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_unpins_builtin_agent(self, mock_json_agents, mock_emit, mock_clear_pin):
        """Test that built-in agents have pin cleared via config."""
        from code_puppy.command_line.agent_menu import consume_pending_pin_reloads

        consume_pending_pin_reloads()
        mock_json_agents.return_value = {}

        _apply_pinned_model("code_puppy", "(unpin)")

        mock_clear_pin.assert_called_once_with("code_puppy")
        assert consume_pending_pin_reloads() == [("code_puppy", None)]

    @patch("code_puppy.command_line.agent_menu.emit_success")
    @patch("code_puppy.agents.json_agent.discover_json_agents")
    def test_unpins_json_agent(self, mock_json_agents, mock_emit):
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
