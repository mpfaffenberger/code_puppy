"""Tests for the /uc slash command (Universal Constructor TUI menu).

Tests cover:
- Tool entry retrieval
- Toggle enabled/disabled
- Panel rendering
- Source code display
- TUI interaction
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.uc_menu import (
    PAGE_SIZE,
    _get_tool_entries,
    _render_menu_panel,
    _render_preview_panel,
    _sanitize_display_text,
    _show_source_code,
    _toggle_tool_enabled,
    handle_uc_command,
    interactive_uc_picker,
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
        source_path="/fake/path/weather_api.py",
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
        source_path="/fake/path/deprecated_tool.py",
        function_name="deprecated_tool",
        docstring=None,
    )


class TestSanitizeDisplayText:
    """Tests for the _sanitize_display_text function."""

    def test_keeps_alphanumeric(self):
        """Test that alphanumeric characters are preserved."""
        result = _sanitize_display_text("Hello World 123")
        assert result == "Hello World 123"

    def test_removes_emojis(self):
        """Test that emojis are removed."""
        result = _sanitize_display_text("Hello 🌍 World 🎉")
        assert "🌍" not in result
        assert "🎉" not in result
        assert "Hello" in result
        assert "World" in result

    def test_preserves_punctuation(self):
        """Test that punctuation is preserved."""
        result = _sanitize_display_text("test_function(arg1, arg2)")
        assert "(" in result
        assert ")" in result
        assert "_" in result


class TestGetToolEntries:
    """Tests for the _get_tool_entries function."""

    def test_empty_registry(self):
        """Test when no tools exist."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 0
        mock_registry.list_tools.return_value = []

        with patch(
            "code_puppy.command_line.uc_menu.get_registry",
            return_value=mock_registry,
        ):
            result = _get_tool_entries()

            assert result == []
            mock_registry.scan.assert_called_once()

    def test_returns_all_tools(self, mock_tool_enabled, mock_tool_disabled):
        """Test that all tools (including disabled) are returned."""
        mock_registry = MagicMock()
        mock_registry.scan.return_value = 2
        mock_registry.list_tools.return_value = [mock_tool_enabled, mock_tool_disabled]

        with patch(
            "code_puppy.command_line.uc_menu.get_registry",
            return_value=mock_registry,
        ):
            result = _get_tool_entries()

            assert len(result) == 2
            mock_registry.list_tools.assert_called_once_with(include_disabled=True)


class TestToggleToolEnabled:
    """Tests for the _toggle_tool_enabled function."""

    def test_toggle_enabled_to_disabled(self):
        """Test toggling an enabled tool to disabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                'TOOL_META = {\n    "name": "test",\n    "description": "Test",\n    "enabled": True\n}\n\ndef run():\n    pass'
            )
            temp_path = f.name

        try:
            tool = UCToolInfo(
                meta=ToolMeta(
                    name="test",
                    namespace="",
                    description="Test",
                    enabled=True,
                ),
                signature="run() -> None",
                source_path=temp_path,
                function_name="run",
            )

            with patch("code_puppy.command_line.uc_menu.emit_success"):
                result = _toggle_tool_enabled(tool)

            assert result is True
            content = Path(temp_path).read_text()
            assert "False" in content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_toggle_disabled_to_enabled(self):
        """Test toggling a disabled tool to enabled."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                'TOOL_META = {\n    "name": "test",\n    "description": "Test",\n    "enabled": False\n}\n\ndef run():\n    pass'
            )
            temp_path = f.name

        try:
            tool = UCToolInfo(
                meta=ToolMeta(
                    name="test",
                    namespace="",
                    description="Test",
                    enabled=False,
                ),
                signature="run() -> None",
                source_path=temp_path,
                function_name="run",
            )

            with patch("code_puppy.command_line.uc_menu.emit_success"):
                result = _toggle_tool_enabled(tool)

            assert result is True
            content = Path(temp_path).read_text()
            assert "True" in content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_toggle_handles_missing_enabled_field(self):
        """Test toggling when enabled field is missing (adds it)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                'TOOL_META = {\n    "name": "test",\n    "description": "Test"\n}\n\ndef run():\n    pass'
            )
            temp_path = f.name

        try:
            tool = UCToolInfo(
                meta=ToolMeta(
                    name="test",
                    namespace="",
                    description="Test",
                    enabled=True,  # Default is True when missing
                ),
                signature="run() -> None",
                source_path=temp_path,
                function_name="run",
            )

            with patch("code_puppy.command_line.uc_menu.emit_success"):
                result = _toggle_tool_enabled(tool)

            assert result is True
            content = Path(temp_path).read_text()
            # Should have added enabled field
            assert "enabled" in content
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_toggle_handles_file_error(self, mock_tool_enabled):
        """Test graceful handling of file errors."""
        mock_tool_enabled.source_path = "/nonexistent/path.py"

        with patch("code_puppy.command_line.uc_menu.emit_error"):
            result = _toggle_tool_enabled(mock_tool_enabled)

        assert result is False


class TestRenderMenuPanel:
    """Tests for the _render_menu_panel function."""

    def test_empty_tools_list(self):
        """Test rendering with no tools."""
        result = _render_menu_panel([], page=0, selected_idx=0)

        # Should contain "No UC tools found" somewhere in the output
        text_content = "".join(str(t[1]) for t in result)
        assert "No UC tools found" in text_content

    def test_renders_tool_name(self, mock_tool_enabled):
        """Test that tool names are rendered."""
        result = _render_menu_panel([mock_tool_enabled], page=0, selected_idx=0)

        text_content = "".join(str(t[1]) for t in result)
        assert "weather_api" in text_content or "api.weather_api" in text_content

    def test_shows_enabled_status(self, mock_tool_enabled, mock_tool_disabled):
        """Test that enabled/disabled status is shown."""
        tools = [mock_tool_enabled, mock_tool_disabled]
        result = _render_menu_panel(tools, page=0, selected_idx=0)

        text_content = "".join(str(t[1]) for t in result)
        assert "[on]" in text_content
        assert "[off]" in text_content

    def test_highlights_selected(self, mock_tool_enabled):
        """Test that selected tool is highlighted."""
        result = _render_menu_panel([mock_tool_enabled], page=0, selected_idx=0)

        # Should contain the selection indicator ">"
        text_content = "".join(str(t[1]) for t in result)
        assert ">" in text_content

    def test_pagination_info(self, mock_tool_enabled):
        """Test that pagination info is displayed."""
        result = _render_menu_panel([mock_tool_enabled], page=0, selected_idx=0)

        text_content = "".join(str(t[1]) for t in result)
        assert "Page 1/1" in text_content


class TestRenderPreviewPanel:
    """Tests for the _render_preview_panel function."""

    def test_no_tool_selected(self):
        """Test rendering with no tool selected."""
        result = _render_preview_panel(None)

        text_content = "".join(str(t[1]) for t in result)
        assert "No tool selected" in text_content

    def test_shows_tool_details(self, mock_tool_enabled):
        """Test that tool details are shown."""
        result = _render_preview_panel(mock_tool_enabled)

        text_content = "".join(str(t[1]) for t in result)
        assert "weather_api" in text_content
        assert "ENABLED" in text_content
        assert "1.0.0" in text_content

    def test_shows_author_if_present(self, mock_tool_enabled):
        """Test that author is shown if present."""
        result = _render_preview_panel(mock_tool_enabled)

        text_content = "".join(str(t[1]) for t in result)
        assert "Test Author" in text_content

    def test_shows_signature(self, mock_tool_enabled):
        """Test that function signature is shown."""
        result = _render_preview_panel(mock_tool_enabled)

        text_content = "".join(str(t[1]) for t in result)
        assert "location" in text_content or "str" in text_content

    def test_shows_docstring_preview(self, mock_tool_enabled):
        """Test that docstring is shown."""
        result = _render_preview_panel(mock_tool_enabled)

        text_content = "".join(str(t[1]) for t in result)
        assert "Fetch weather" in text_content


class TestShowSourceCode:
    """Tests for the _show_source_code function."""

    def test_shows_source_code(self):
        """Test that source code is displayed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('def test():\n    return "hello"')
            temp_path = f.name

        try:
            tool = UCToolInfo(
                meta=ToolMeta(
                    name="test",
                    namespace="",
                    description="Test",
                    enabled=True,
                ),
                signature="test() -> str",
                source_path=temp_path,
                function_name="test",
            )

            with patch("code_puppy.command_line.uc_menu.emit_info") as mock_emit:
                _show_source_code(tool)

            mock_emit.assert_called_once()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_handles_read_error(self, mock_tool_enabled):
        """Test graceful handling of read errors."""
        mock_tool_enabled.source_path = "/nonexistent/path.py"

        with patch("code_puppy.command_line.uc_menu.emit_error") as mock_error:
            _show_source_code(mock_tool_enabled)

        mock_error.assert_called_once()


class TestHandleUcCommand:
    """Tests for the main handle_uc_command function."""

    def test_launches_tui(self):
        """Test that /uc launches the TUI."""
        with patch(
            "code_puppy.command_line.uc_menu.interactive_uc_picker",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with patch("asyncio.run"):
                result = handle_uc_command("/uc")

            assert result is True

    def test_handles_tui_error(self):
        """Test graceful handling of TUI errors."""
        with patch(
            "asyncio.run",
            side_effect=Exception("TUI failed"),
        ):
            with patch(
                "asyncio.get_event_loop",
                return_value=MagicMock(is_running=lambda: False),
            ):
                with patch("code_puppy.command_line.uc_menu.emit_error"):
                    result = handle_uc_command("/uc")

            assert result is True  # Should still return True


class TestInteractiveUcPicker:
    """Tests for the interactive_uc_picker async function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_cancelled(self):
        """Test that cancellation returns None."""
        mock_app = MagicMock()
        mock_app.run_async = AsyncMock(return_value=None)

        with patch(
            "code_puppy.command_line.uc_menu._get_tool_entries",
            return_value=[],
        ):
            with patch(
                "code_puppy.command_line.uc_menu.Application",
                return_value=mock_app,
            ):
                with patch("code_puppy.command_line.uc_menu.set_awaiting_user_input"):
                    with patch("sys.stdout"):
                        with patch("time.sleep"):
                            result = await interactive_uc_picker()

        assert result is None


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


class TestPageSize:
    """Tests for pagination constants."""

    def test_page_size_is_reasonable(self):
        """Test that PAGE_SIZE is a reasonable number."""
        assert PAGE_SIZE > 0
        assert PAGE_SIZE <= 20  # Don't show too many at once
