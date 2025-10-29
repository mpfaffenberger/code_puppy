"""Comprehensive tests for RPA tool wrapper utilities."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.rpa.tool_wrapper import (
    check_library_available,
    rpa_tool,
    TOOL_EMOJIS,
)


class TestCheckLibraryAvailable:
    """Test library availability checking."""

    def test_pyautogui_available(self):
        with patch('builtins.__import__'):
            available, error = check_library_available("pyautogui")
            # Result depends on whether pyautogui is actually installed
            if available:
                assert error is None
            else:
                assert "pyautogui" in error.lower()

    def test_unknown_library(self):
        available, error = check_library_available("nonexistent_library")
        assert available is False
        assert "Unknown library" in error

    def test_pillow_check(self):
        available, error = check_library_available("pillow")
        # May or may not be available
        if not available:
            assert error is not None

    def test_opencv_check(self):
        available, error = check_library_available("opencv")
        # OpenCV may not be installed
        if not available:
            assert "opencv" in error.lower() or "cv2" in error.lower()

    def test_atomacos_check(self):
        available, error = check_library_available("atomacos")
        # atomacos is macOS-only
        if not available:
            assert error is not None

    def test_windows_check(self):
        available, error = check_library_available("windows")
        # Windows libs only on Windows
        if not available:
            assert error is not None


class TestToolEmojis:
    """Test tool emoji mappings."""

    def test_mouse_operations_have_emojis(self):
        assert "MOUSE MOVE" in TOOL_EMOJIS
        assert "MOUSE CLICK" in TOOL_EMOJIS
        assert "MOUSE DRAG" in TOOL_EMOJIS
        assert "MOUSE SCROLL" in TOOL_EMOJIS

    def test_keyboard_operations_have_emojis(self):
        assert "KEYBOARD TYPE" in TOOL_EMOJIS
        assert "KEYBOARD PRESS" in TOOL_EMOJIS
        assert "KEYBOARD HOTKEY" in TOOL_EMOJIS

    def test_clipboard_operations_have_emojis(self):
        assert "COPY" in TOOL_EMOJIS
        assert "PASTE" in TOOL_EMOJIS
        assert "CUT" in TOOL_EMOJIS

    def test_screenshot_operations_have_emojis(self):
        assert "SCREENSHOT" in TOOL_EMOJIS

    def test_emojis_are_strings(self):
        for tool_name, emoji in TOOL_EMOJIS.items():
            assert isinstance(emoji, str)
            assert len(emoji) > 0


class TestRPAToolDecorator:
    """Test the rpa_tool decorator."""

    def test_decorator_basic_success(self):
        @rpa_tool("TEST TOOL")
        def test_function(context, value: int) -> dict:
            return {"success": True, "value": value}

        result = test_function(None, 42)
        assert result["success"] is True
        assert result["value"] == 42

    def test_decorator_with_required_library(self):
        with patch('code_puppy.tools.rpa.tool_wrapper.check_library_available') as mock_check:
            mock_check.return_value = (True, None)

            @rpa_tool("TEST TOOL", requires="pyautogui")
            def test_function(context) -> dict:
                return {"success": True}

            result = test_function(None)
            assert result["success"] is True
            mock_check.assert_called_with("pyautogui")

    def test_decorator_missing_required_library(self):
        with patch('code_puppy.tools.rpa.tool_wrapper.check_library_available') as mock_check:
            mock_check.return_value = (False, "Library not found")

            @rpa_tool("TEST TOOL", requires="pyautogui", emit_errors=False)
            def test_function(context) -> dict:
                return {"success": True}

            result = test_function(None)
            assert result["success"] is False
            assert "Library not found" in result["error"]

    def test_decorator_multiple_required_libraries(self):
        with patch('code_puppy.tools.rpa.tool_wrapper.check_library_available') as mock_check:
            mock_check.return_value = (True, None)

            @rpa_tool("TEST TOOL", requires=["pyautogui", "pillow"])
            def test_function(context) -> dict:
                return {"success": True}

            result = test_function(None)
            assert result["success"] is True
            assert mock_check.call_count == 2

    def test_decorator_exception_handling(self):
        @rpa_tool("TEST TOOL", emit_errors=False)
        def test_function(context) -> dict:
            raise ValueError("Test error")

        result = test_function(None)
        assert result["success"] is False
        assert "Test error" in result["error"]

    def test_decorator_failsafe_exception(self):
        # Create a mock FailSafeException
        class FailSafeException(Exception):
            pass

        @rpa_tool("TEST TOOL", emit_errors=False, emit_start=False)
        def test_function(context) -> dict:
            raise FailSafeException("Moved to corner")

        result = test_function(None)
        assert result["success"] is False
        assert "failsafe" in result["error"].lower() or "corner" in result["error"].lower()

    def test_decorator_preserves_function_metadata(self):
        @rpa_tool("TEST TOOL")
        def test_function(context, value: int) -> dict:
            """Test docstring."""
            return {"success": True}

        assert test_function.__name__ == "test_function"
        assert "Test docstring" in test_function.__doc__

    def test_decorator_handles_non_dict_result(self):
        @rpa_tool("TEST TOOL", emit_success=True, emit_start=False)
        def test_function(context) -> str:
            return "plain string result"

        result = test_function(None)
        assert result == "plain string result"

    def test_decorator_success_message_with_coordinates(self):
        @rpa_tool("TEST TOOL", emit_start=False, emit_success=True)
        def test_function(context) -> dict:
            return {"success": True, "x": 100, "y": 200}

        with patch('code_puppy.tools.rpa.tool_wrapper.emit_info'):
            result = test_function(None)
            assert result["success"] is True
            assert result["x"] == 100
            assert result["y"] == 200

    def test_decorator_success_message_with_element(self):
        @rpa_tool("TEST TOOL", emit_start=False, emit_success=True)
        def test_function(context) -> dict:
            return {"success": True, "element": "Button1"}

        with patch('code_puppy.tools.rpa.tool_wrapper.emit_info'):
            result = test_function(None)
            assert result["success"] is True

    def test_decorator_filters_context_param(self):
        @rpa_tool("TEST TOOL", emit_start=True)
        def test_function(context, value: int, _internal: str = "hidden") -> dict:
            return {"success": True}

        with patch('code_puppy.tools.rpa.tool_wrapper.emit_info'):
            result = test_function(None, value=42, _internal="secret")
            assert result["success"] is True


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    def test_real_tool_pattern(self):
        """Test a realistic RPA tool pattern."""
        with patch('code_puppy.tools.rpa.tool_wrapper.check_library_available') as mock_check:
            mock_check.return_value = (True, None)

            @rpa_tool("MOUSE CLICK", requires="pyautogui")
            def desktop_mouse_click(context, x: int, y: int, button: str = "left") -> dict:
                # Simulate pyautogui.click()
                return {
                    "success": True,
                    "x": x,
                    "y": y,
                    "button": button
                }

            result = desktop_mouse_click(None, x=500, y=300, button="left")
            assert result["success"] is True
            assert result["x"] == 500
            assert result["y"] == 300
            assert result["button"] == "left"

    def test_tool_with_multiple_dependencies(self):
        """Test tool requiring multiple libraries."""
        with patch('code_puppy.tools.rpa.tool_wrapper.check_library_available') as mock_check:
            mock_check.return_value = (True, None)

            @rpa_tool("SCREENSHOT ANALYZE", requires=["pyautogui", "pillow", "opencv"])
            def analyze_screenshot(context, region: tuple) -> dict:
                return {"success": True, "found": True}

            result = analyze_screenshot(None, region=(0, 0, 100, 100))
            assert result["success"] is True
            assert mock_check.call_count == 3

    def test_tool_with_error_recovery(self):
        """Test tool that handles errors gracefully."""
        @rpa_tool("TEST TOOL", emit_errors=False, emit_start=False)
        def risky_operation(context, value: int) -> dict:
            if value < 0:
                raise ValueError("Value must be positive")
            return {"success": True, "value": value}

        # Success case
        result = risky_operation(None, value=10)
        assert result["success"] is True

        # Error case
        result = risky_operation(None, value=-5)
        assert result["success"] is False
        assert "positive" in result["error"].lower()
