"""Tests for the safety_status plugin (P3-01)."""

from __future__ import annotations

from unittest.mock import patch


from code_puppy.plugins.safety_status.register_callbacks import (
    _custom_help,
    _get_status_lines,
    _handle_custom_command,
)


class TestSafetyStatusPlugin:
    """Test that /safety and /status produce a redacted status summary."""

    def test_custom_help_returns_entries(self):
        help_entries = _custom_help()
        names = [name for name, _ in help_entries]
        assert "safety" in names
        assert "status" in names

    def test_handle_safety_command_returns_true(self):
        with patch(
            "code_puppy.plugins.safety_status.register_callbacks.emit_info"
        ) as mock_emit:
            result = _handle_custom_command("/safety", "safety")
        assert result is True
        mock_emit.assert_called_once()

    def test_handle_status_command_returns_true(self):
        with patch(
            "code_puppy.plugins.safety_status.register_callbacks.emit_info"
        ) as mock_emit:
            result = _handle_custom_command("/status", "status")
        assert result is True
        mock_emit.assert_called_once()

    def test_handle_unknown_returns_none(self):
        result = _handle_custom_command("/foo", "foo")
        assert result is None

    def test_status_lines_include_expected_fields(self):
        lines = _get_status_lines()
        text = "\n".join(lines)
        assert "Yolo mode" in text
        assert "Shell safety" in text
        assert "Workspace" in text
        assert "Sensitive policy" in text
        assert "Hook trust" in text
        assert "Callbacks active" in text
        assert "UC enabled" in text
        assert "MCP disabled" in text

    def test_status_lines_redact_secrets(self):
        """Ensure status display does not embed secret values from config."""
        lines = _get_status_lines()
        text = "\n".join(lines)
        # Status should never expose actual keys or tokens
        assert "sk-" not in text
        assert "api_key" not in text.lower() or "<redacted>" in text
        # Confirm REDACTED token isn't accidentally injected into safe fields
        for line in lines:
            if "Workspace" in line:
                assert "<redacted>" not in line

    def test_status_panel_renderable(self):
        from code_puppy.plugins.safety_status.register_callbacks import _render_panel

        panel = _render_panel(["line1", "line2"])
        assert "line1" in panel.renderable
        assert "Safety Status" in str(panel.title)
