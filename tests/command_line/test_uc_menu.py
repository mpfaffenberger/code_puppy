"""Tests for the /uc slash command (Universal Constructor menu).

Tests cover:
- Listing tools (including disabled)
- Showing tool info
- Error handling for unknown tools
- Edge cases
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.uc_menu import (
    _list_tools,
    _show_tool_info,
    handle_uc_command,
)
from code_puppy.plugins.universal_constructor.models import ToolMeta, UCToolInfo


@pytest.fixture
def mock_tool_enabled():
    """Create a mock enabled tool."""
    return UCToolInfo(
        meta=ToolMeta(
            name="weather_api",
            namespace="api",
            description="Get current weather for a location",
            enabled=True,
            version="1.0.0",
            author="Test Author",
        ),
        signature="weather_api(location: str) -> dict",
        source_path=Path("/fake/path/weather_api.py"),
        function_name="weather_api",
        docstring="Fetch weather data for a given location.",
    )


@pytest.fixture
def mock_tool_disabled():
    """Create a mock disabled tool."""
    return UCToolInfo(
        meta=ToolMeta(
            name="deprecated_tool",
            namespace="",
            description="An old tool that is disabled",
            enabled=False,
            version="0.1.0",
        ),
        signature="deprecated_tool() -> None",
        source_path=Path("/fake/path/deprecated_tool.py"),
        function_name="deprecated_tool",
        docstring=None,
    )


class TestListTools:
    """Tests for the _list_tools function."""

    def test_list_tools_empty(self):
        """Test listing when no tools are found."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 0
        mock_registry.list_tools.return_value = []

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_info") as mock_emit:
                result = _list_tools()

                assert result is True
                assert mock_emit.call_count >= 1
                # Check that "No UC tools found" message was emitted
                first_call = mock_emit.call_args_list[0]
                assert "No UC tools found" in str(first_call)

    def test_list_tools_with_tools(self, mock_tool_enabled, mock_tool_disabled):
        """Test listing with both enabled and disabled tools."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 2
        mock_registry.list_tools.return_value = [mock_tool_enabled, mock_tool_disabled]

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_info") as mock_emit:
                result = _list_tools()

                assert result is True
                # Should emit a Rich Table
                assert mock_emit.call_count >= 1
                mock_registry.list_tools.assert_called_once_with(include_disabled=True)

    def test_list_tools_forces_scan(self, mock_tool_enabled):
        """Test that list_tools forces a fresh scan."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 1
        mock_registry.list_tools.return_value = [mock_tool_enabled]

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_info"):
                _list_tools()

                # Verify scan was called
                mock_registry.scan.assert_called_once()


class TestShowToolInfo:
    """Tests for the _show_tool_info function."""

    def test_show_tool_info_found(self, mock_tool_enabled):
        """Test showing info for an existing tool."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 1
        mock_registry.get_tool.return_value = mock_tool_enabled

        # Mock the source_path.read_text() method
        mock_tool_enabled.source_path = MagicMock()
        mock_tool_enabled.source_path.read_text.return_value = 'TOOL_META = {"name": "weather_api"}\n\ndef weather_api(location):\n    pass'

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_info") as mock_emit:
                result = _show_tool_info("api.weather_api")

                assert result is True
                # Should have emitted panels
                assert mock_emit.call_count >= 1

    def test_show_tool_info_not_found(self):
        """Test showing info for a non-existent tool."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 0
        mock_registry.get_tool.return_value = None
        mock_registry.list_tools.return_value = []

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_error") as mock_error:
                with patch("code_puppy.command_line.uc_menu.emit_info"):
                    result = _show_tool_info("nonexistent_tool")

                    assert result is True
                    # Should emit error about tool not found
                    mock_error.assert_called_once()
                    assert "not found" in str(mock_error.call_args)

    def test_show_tool_info_partial_match(self, mock_tool_enabled):
        """Test showing info with partial match suggestions."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 1
        mock_registry.get_tool.return_value = None
        mock_registry.list_tools.return_value = [mock_tool_enabled]

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_error") as mock_error:
                with patch("code_puppy.command_line.uc_menu.emit_info") as mock_info:
                    result = _show_tool_info("weather")

                    assert result is True
                    mock_error.assert_called_once()
                    # Should suggest matching tools
                    assert mock_info.call_count >= 1

    def test_show_tool_info_source_code_error(self, mock_tool_enabled):
        """Test graceful handling when source code can't be read."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 1
        mock_registry.get_tool.return_value = mock_tool_enabled

        # Mock the source_path.read_text() to raise an error
        mock_tool_enabled.source_path = MagicMock()
        mock_tool_enabled.source_path.read_text.side_effect = PermissionError(
            "Access denied"
        )

        with patch(
            "code_puppy.plugins.universal_constructor.registry.get_registry",
            return_value=mock_registry,
        ):
            with patch("code_puppy.command_line.uc_menu.emit_info"):
                with patch("code_puppy.command_line.uc_menu.emit_warning") as mock_warn:
                    result = _show_tool_info("api.weather_api")

                    assert result is True
                    # Should emit warning about source code
                    mock_warn.assert_called_once()
                    assert "Could not read source code" in str(mock_warn.call_args)


class TestHandleUcCommand:
    """Tests for the main handle_uc_command function."""

    def test_uc_no_args_lists_tools(self):
        """Test /uc with no args lists tools."""
        with patch(
            "code_puppy.command_line.uc_menu._list_tools", return_value=True
        ) as mock_list:
            result = handle_uc_command("/uc")

            assert result is True
            mock_list.assert_called_once()

    def test_uc_list_subcommand(self):
        """Test /uc list lists tools."""
        with patch(
            "code_puppy.command_line.uc_menu._list_tools", return_value=True
        ) as mock_list:
            result = handle_uc_command("/uc list")

            assert result is True
            mock_list.assert_called_once()

    def test_uc_info_subcommand(self):
        """Test /uc info <name> shows tool info."""
        with patch(
            "code_puppy.command_line.uc_menu._show_tool_info", return_value=True
        ) as mock_info:
            result = handle_uc_command("/uc info weather_api")

            assert result is True
            mock_info.assert_called_once_with("weather_api")

    def test_uc_info_missing_name(self):
        """Test /uc info without tool name shows error."""
        with patch("code_puppy.command_line.uc_menu.emit_error") as mock_error:
            with patch("code_puppy.command_line.uc_menu.emit_info"):
                result = handle_uc_command("/uc info")

                assert result is True
                mock_error.assert_called_once()
                assert "Usage" in str(mock_error.call_args)

    def test_uc_unknown_subcommand(self):
        """Test /uc with unknown subcommand shows help."""
        with patch("code_puppy.command_line.uc_menu.emit_warning") as mock_warn:
            with patch("code_puppy.command_line.uc_menu.emit_info"):
                result = handle_uc_command("/uc unknown")

                assert result is True
                mock_warn.assert_called_once()
                assert "Unknown subcommand" in str(mock_warn.call_args)

    def test_uc_case_insensitive_subcommands(self):
        """Test that subcommands are case-insensitive."""
        with patch(
            "code_puppy.command_line.uc_menu._list_tools", return_value=True
        ) as mock_list:
            result = handle_uc_command("/uc LIST")

            assert result is True
            mock_list.assert_called_once()

    def test_uc_info_with_namespace(self):
        """Test /uc info with namespaced tool name."""
        with patch(
            "code_puppy.command_line.uc_menu._show_tool_info", return_value=True
        ) as mock_info:
            result = handle_uc_command("/uc info api.weather")

            assert result is True
            mock_info.assert_called_once_with("api.weather")


class TestCommandRegistration:
    """Tests to verify command is properly registered."""

    def test_uc_command_is_registered(self):
        """Test that /uc command is registered in the registry."""
        from code_puppy.command_line.command_registry import get_command

        cmd_info = get_command("uc")

        assert cmd_info is not None
        assert cmd_info.name == "uc"
        assert cmd_info.category == "tools"
        assert "Universal Constructor" in cmd_info.description
        assert cmd_info.handler == handle_uc_command
