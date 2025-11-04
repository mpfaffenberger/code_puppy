"""Comprehensive tests for mouse control tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.gui_cub.mouse_control import register_mouse_control_tools
from code_puppy.tools.gui_cub.result_types import (
    MouseActionResult,
    MouseDragResult,
    MousePositionResult,
    MouseScrollResult,
)


class DummyAgent:
    """Mock agent for testing tool registration."""

    def __init__(self):
        self.tools = {}

    def tool(self, fn):
        """Decorator that registers a tool function."""
        self.tools[fn.__name__] = fn
        return fn


@pytest.fixture
def agent():
    """Create a mock agent with mouse tools registered."""
    mock_agent = DummyAgent()
    
    with patch('code_puppy.tools.gui_cub.mouse_control.PYAUTOGUI_AVAILABLE', True):
        with patch('code_puppy.tools.gui_cub.mouse_control.pyautogui') as mock_pyautogui:
            with patch('code_puppy.tools.gui_cub.mouse_control.IS_MACOS', False):
                mock_pyautogui.position.return_value = (100, 100)
                register_mouse_control_tools(mock_agent)
                yield mock_agent, mock_pyautogui


class TestDesktopMouseMove:
    """Test desktop_mouse_move function."""

    def test_move_to_coordinates(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        mock_pyautogui.position.return_value = (500, 300)
        result = tool(context=None, x=500, y=300)
        
        assert isinstance(result, MouseActionResult)
        assert result.success is True
        assert result.x == 500
        assert result.y == 300
        mock_pyautogui.moveTo.assert_called_once_with(500, 300, duration=0.25)

    def test_move_with_duration(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        mock_pyautogui.position.return_value = (800, 600)
        result = tool(context=None, x=800, y=600, duration=1.0)
        
        assert result.success is True
        mock_pyautogui.moveTo.assert_called_once_with(800, 600, duration=1.0)

    def test_move_instant(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        mock_pyautogui.position.return_value = (100, 200)
        result = tool(context=None, x=100, y=200, duration=0)
        
        assert result.success is True
        mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0)

    def test_move_failure_wrong_position(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        mock_pyautogui.position.return_value = (50, 50)
        result = tool(context=None, x=500, y=300)
        
        assert result.success is False
        assert "Mouse movement failed" in result.error
        assert result.x == 50
        assert result.y == 50

    def test_move_within_tolerance(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        mock_pyautogui.position.return_value = (501, 299)
        result = tool(context=None, x=500, y=300)
        
        assert result.success is True


class TestDesktopMouseClick:
    """Test desktop_mouse_click function."""

    def test_click_at_current_position(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (100, 100)
        result = tool(context=None)
        
        assert isinstance(result, MouseActionResult)
        assert result.success is True
        assert result.button == "left"
        assert result.clicks == 1
        mock_pyautogui.click.assert_called_once_with(button="left", clicks=1, interval=0.0)

    def test_click_at_specific_coordinates(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (500, 300)
        result = tool(context=None, x=500, y=300)
        
        assert result.success is True
        assert result.x == 500
        assert result.y == 300
        mock_pyautogui.click.assert_called_once_with(
            x=500, y=300, button="left", clicks=1, interval=0.0
        )

    def test_right_click(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (100, 100)
        result = tool(context=None, button="right")
        
        assert result.success is True
        assert result.button == "right"
        mock_pyautogui.click.assert_called_once_with(button="right", clicks=1, interval=0.0)

    def test_middle_click(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (100, 100)
        result = tool(context=None, button="middle")
        
        assert result.success is True
        assert result.button == "middle"

    def test_double_click(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (100, 100)
        result = tool(context=None, clicks=2)
        
        assert result.success is True
        assert result.clicks == 2
        mock_pyautogui.click.assert_called_once_with(button="left", clicks=2, interval=0.0)

    def test_click_with_interval(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (100, 100)
        result = tool(context=None, clicks=3, interval=0.5)
        
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(
            button="left", clicks=3, interval=0.5
        )

    def test_click_combinations(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_click']
        
        mock_pyautogui.position.return_value = (500, 300)
        result = tool(context=None, x=500, y=300, button="right", clicks=2)
        
        assert result.success is True
        assert result.button == "right"
        assert result.clicks == 2
        mock_pyautogui.click.assert_called_once_with(
            x=500, y=300, button="right", clicks=2, interval=0.0
        )


class TestDesktopMouseDrag:
    """Test desktop_mouse_drag function."""

    def test_drag_to_coordinates(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_drag']
        
        mock_pyautogui.position.side_effect = [(100, 100), (500, 300)]
        result = tool(context=None, x=500, y=300)
        
        assert isinstance(result, MouseDragResult)
        assert result.success is True
        assert result.start_x == 100
        assert result.start_y == 100
        assert result.end_x == 500
        assert result.end_y == 300
        assert result.button == "left"
        
        mock_pyautogui.drag.assert_called_once_with(400, 200, duration=0.25, button="left")

    def test_drag_with_duration(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_drag']
        
        mock_pyautogui.position.side_effect = [(200, 200), (800, 600)]
        result = tool(context=None, x=800, y=600, duration=2.0)
        
        assert result.success is True
        mock_pyautogui.drag.assert_called_once_with(600, 400, duration=2.0, button="left")

    def test_drag_with_right_button(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_drag']
        
        mock_pyautogui.position.side_effect = [(100, 100), (300, 300)]
        result = tool(context=None, x=300, y=300, button="right")
        
        assert result.success is True
        assert result.button == "right"
        mock_pyautogui.drag.assert_called_once_with(200, 200, duration=0.25, button="right")

    def test_drag_negative_offset(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_drag']
        
        mock_pyautogui.position.side_effect = [(500, 500), (300, 200)]
        result = tool(context=None, x=300, y=200)
        
        assert result.success is True
        mock_pyautogui.drag.assert_called_once_with(-200, -300, duration=0.25, button="left")


class TestDesktopMouseScroll:
    """Test desktop_mouse_scroll function."""

    def test_scroll_up(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_scroll']
        
        result = tool(context=None, clicks=5)
        
        assert isinstance(result, MouseScrollResult)
        assert result.success is True
        assert result.clicks == 5
        assert result.direction == "up"
        mock_pyautogui.scroll.assert_called_once_with(5)

    def test_scroll_down(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_scroll']
        
        result = tool(context=None, clicks=-10)
        
        assert result.success is True
        assert result.clicks == -10
        assert result.direction == "down"
        mock_pyautogui.scroll.assert_called_once_with(-10)

    def test_scroll_at_position(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_scroll']
        
        result = tool(context=None, clicks=3, x=500, y=500)
        
        assert result.success is True
        assert result.clicks == 3
        mock_pyautogui.scroll.assert_called_once_with(3, x=500, y=500)

    def test_scroll_zero(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_scroll']
        
        result = tool(context=None, clicks=0)
        
        assert result.success is True
        assert result.direction == "down"


class TestDesktopMouseGetPosition:
    """Test desktop_mouse_get_position function."""

    def test_get_position(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_get_position']
        
        mock_pyautogui.position.return_value = (542, 319)
        result = tool(context=None)
        
        assert isinstance(result, MousePositionResult)
        assert result.x == 542
        assert result.y == 319

    def test_get_position_different_coords(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_get_position']
        
        mock_pyautogui.position.return_value = (1920, 1080)
        result = tool(context=None)
        
        assert result.x == 1920
        assert result.y == 1080


class TestDesktopCheckAutomationPermissions:
    """Test desktop_check_automation_permissions function."""

    def test_check_permissions_non_macos(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_check_automation_permissions']
        
        with patch('code_puppy.tools.gui_cub.mouse_control.IS_MACOS', False):
            with patch('code_puppy.tools.gui_cub.mouse_control.pyautogui.position') as mock_pos:
                mock_pos.return_value = (100, 200)
                result = tool(context=None)
        
        assert result["has_permission"] is True
        assert result["status"] == "Basic automation appears to be working ✅"

    def test_check_permissions_macos_granted(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_check_automation_permissions']
        
        with patch('code_puppy.tools.gui_cub.mouse_control.IS_MACOS', True):
            with patch('code_puppy.tools.gui_cub.mouse_control.check_macos_accessibility_permission') as mock_check:
                mock_check.return_value = (True, None)
                result = tool(context=None)
        
        assert result["has_permission"] is True

    def test_check_permissions_macos_denied(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_check_automation_permissions']
        
        with patch('code_puppy.tools.gui_cub.mouse_control.IS_MACOS', True):
            with patch('code_puppy.tools.gui_cub.platform.get_display_info') as mock_display:
                mock_display.return_value = {
                    "platform": "macOS",
                    "macos_accessibility_permission": False,
                    "message": "Permission denied"
                }
                result = tool(context=None)
        
        assert result["has_permission"] is False
        assert "instructions" in result


class TestMacOSPermissionHandling:
    """Test macOS permission handling in mouse operations."""

    def test_move_fails_without_macos_permission(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_mouse_move']
        
        with patch('code_puppy.tools.gui_cub.mouse_control.IS_MACOS', True):
            with patch('code_puppy.tools.gui_cub.mouse_control.check_macos_accessibility_permission') as mock_check:
                mock_check.return_value = (False, "Permission required")
                
                result = tool(context=None, x=500, y=300)
        
        assert result.success is False
        assert "Permission" in result.error


class TestToolRegistration:
    """Test that all tools are properly registered."""

    def test_all_tools_registered(self, agent):
        mock_agent, _ = agent
        
        expected_tools = [
            'desktop_mouse_move',
            'desktop_mouse_click',
            'desktop_mouse_drag',
            'desktop_mouse_scroll',
            'desktop_mouse_get_position',
            'desktop_check_automation_permissions',
        ]
        
        for tool_name in expected_tools:
            assert tool_name in mock_agent.tools

    def test_tools_are_callable(self, agent):
        mock_agent, _ = agent
        
        for tool_name, tool_func in mock_agent.tools.items():
            assert callable(tool_func)
