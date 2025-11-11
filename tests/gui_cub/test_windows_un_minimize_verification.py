"""Tests for Windows un-minimize window verification.

These tests ensure that windows_un_minimize_window properly verifies
that a window was successfully restored instead of blindly reporting success.

Regression test for: GUI-Cub agent failing to restore minimized Calculator,
tool reporting success when window was still hidden.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# Skip all tests if not on Windows
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-specific un-minimize verification tests"
)


class TestWindowsUnMinimizeVerification:
    """Test suite for windows_un_minimize_window verification behavior."""

    @pytest.fixture
    def mock_win32(self):
        """Mock win32gui and win32con modules."""
        with patch("code_puppy.tools.gui_cub.windows_automation.tools.win32gui") as mock_gui, \n             patch("code_puppy.tools.gui_cub.windows_automation.tools.win32con") as mock_con, \n             patch("code_puppy.tools.gui_cub.windows_automation.tools.WINDOWS_AUTOMATION_AVAILABLE", True):
            
            mock_con.SW_RESTORE = 9  # Standard Windows constant
            yield {
                "gui": mock_gui,
                "con": mock_con
            }

    def test_un_minimize_verifies_window_is_restored(self, mock_win32):
        """Verify that un-minimize checks if window is actually restored."""
        from code_puppy.tools.gui_cub.windows_automation.tools import register_windows_tools
        from code_puppy.agents.base_agent import BaseAgent
        
        # Create agent and register tools
        agent = BaseAgent()
        register_windows_tools(agent)
        
        # Mock: Window is found but stays minimized (simulates focus-steal prevention)
        hwnd = 12345
        mock_win32["gui"].FindWindow.return_value = hwnd
        mock_win32["gui"].IsIconic.return_value = True  # Still minimized after restore attempt
        mock_win32["gui"].GetForegroundWindow.return_value = 99999  # Different window
        
        # Mock RunContext
        mock_context = MagicMock()
        
        # Call the tool
        tool_func = None
        for tool in agent._tools:
            if tool.name == "windows_un_minimize_window":
                tool_func = tool.func
                break
        
        assert tool_func is not None, "windows_un_minimize_window tool not found"
        
        result = tool_func(mock_context, window_title="Calculator")
        
        # Should return FAILURE because window is still minimized
        assert result.success is False
        assert "restore" in result.error.lower() or "minimize" in result.error.lower()
        
    def test_un_minimize_succeeds_when_window_actually_restored(self, mock_win32):
        """Verify that un-minimize returns success when window is truly restored."""
        from code_puppy.tools.gui_cub.windows_automation.tools import register_windows_tools
        from code_puppy.agents.base_agent import BaseAgent
        
        # Create agent and register tools
        agent = BaseAgent()
        register_windows_tools(agent)
        
        # Mock: Window is found and successfully restored
        hwnd = 12345
        mock_win32["gui"].FindWindow.return_value = hwnd
        mock_win32["gui"].IsIconic.return_value = False  # Successfully restored
        mock_win32["gui"].GetForegroundWindow.return_value = hwnd  # Is foreground
        
        # Mock RunContext
        mock_context = MagicMock()
        
        # Call the tool
        tool_func = None
        for tool in agent._tools:
            if tool.name == "windows_un_minimize_window":
                tool_func = tool.func
                break
        
        assert tool_func is not None, "windows_un_minimize_window tool not found"
        
        result = tool_func(mock_context, window_title="Calculator")
        
        # Should return SUCCESS
        assert result.success is True
        
    def test_un_minimize_partial_success_not_foreground(self, mock_win32):
        """Verify partial success case: restored but not foreground."""
        from code_puppy.tools.gui_cub.windows_automation.tools import register_windows_tools
        from code_puppy.agents.base_agent import BaseAgent
        
        # Create agent and register tools
        agent = BaseAgent()
        register_windows_tools(agent)
        
        # Mock: Window restored but not in foreground (focus steal prevention)
        hwnd = 12345
        mock_win32["gui"].FindWindow.return_value = hwnd
        mock_win32["gui"].IsIconic.return_value = False  # Restored
        mock_win32["gui"].GetForegroundWindow.return_value = 99999  # Different window in foreground
        
        # Mock RunContext
        mock_context = MagicMock()
        
        # Call the tool
        tool_func = None
        for tool in agent._tools:
            if tool.name == "windows_un_minimize_window":
                tool_func = tool.func
                break
        
        assert tool_func is not None, "windows_un_minimize_window tool not found"
        
        result = tool_func(mock_context, window_title="Calculator")
        
        # Should return FAILURE with helpful message
        assert result.success is False
        assert "foreground" in result.error.lower() or "focus" in result.message.lower()
        assert "windows_click_taskbar_app" in result.message  # Suggests alternative
        
    def test_un_minimize_window_not_found(self, mock_win32):
        """Verify proper error when window doesn't exist."""
        from code_puppy.tools.gui_cub.windows_automation.tools import register_windows_tools
        from code_puppy.agents.base_agent import BaseAgent
        
        # Create agent and register tools
        agent = BaseAgent()
        register_windows_tools(agent)
        
        # Mock: Window not found
        mock_win32["gui"].FindWindow.return_value = None
        
        # Mock list_windows to return empty
        with patch("code_puppy.tools.gui_cub.windows_automation.tools.list_windows") as mock_list:
            mock_list.return_value = []
            
            # Mock RunContext
            mock_context = MagicMock()
            
            # Call the tool
            tool_func = None
            for tool in agent._tools:
                if tool.name == "windows_un_minimize_window":
                    tool_func = tool.func
                    break
            
            assert tool_func is not None, "windows_un_minimize_window tool not found"
            
            result = tool_func(mock_context, window_title="NonexistentApp")
            
            # Should return failure with clear message
            assert result.success is False
            assert "not found" in result.error.lower()