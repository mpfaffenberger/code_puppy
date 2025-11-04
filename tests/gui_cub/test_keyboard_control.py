"""Comprehensive tests for keyboard control tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.gui_cub.keyboard_control import register_keyboard_control_tools
from code_puppy.tools.gui_cub.result_types import KeyboardActionResult


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
    """Create a mock agent with keyboard tools registered."""
    mock_agent = DummyAgent()
    
    with patch('code_puppy.tools.gui_cub.keyboard_control.PYAUTOGUI_AVAILABLE', True):
        with patch('code_puppy.tools.gui_cub.keyboard_control.pyautogui') as mock_pyautogui:
            register_keyboard_control_tools(mock_agent)
            yield mock_agent, mock_pyautogui


class TestDesktopKeyboardType:
    """Test desktop_keyboard_type function."""

    def test_type_simple_text(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_type']
        
        result = tool(context=None, text="Hello World")
        
        assert isinstance(result, KeyboardActionResult)
        assert result.success is True
        assert result.text_length == 11
        assert result.preview == "Hello World"
        mock_pyautogui.write.assert_called_once_with("Hello World", interval=0.0)

    def test_type_with_interval(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_type']
        
        result = tool(context=None, text="slow typing", interval=0.1)
        
        assert result.success is True
        mock_pyautogui.write.assert_called_once_with("slow typing", interval=0.1)

    def test_type_long_text_preview(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_type']
        
        long_text = "a" * 100
        result = tool(context=None, text=long_text)
        
        assert result.success is True
        assert result.text_length == 100
        assert len(result.preview) == 53
        assert result.preview.endswith("...")

    def test_type_empty_string(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_type']
        
        result = tool(context=None, text="")
        
        assert result.success is True
        assert result.text_length == 0
        assert result.preview == ""

    def test_type_special_characters(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_type']
        
        special_text = "test@example.com!#$"
        result = tool(context=None, text=special_text)
        
        assert result.success is True
        assert result.text_length == len(special_text)
        mock_pyautogui.write.assert_called_once_with(special_text, interval=0.0)


class TestDesktopKeyboardPress:
    """Test desktop_keyboard_press function."""

    def test_press_enter_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_press']
        
        result = tool(context=None, key="enter")
        
        assert isinstance(result, KeyboardActionResult)
        assert result.success is True
        assert result.key == "enter"
        assert result.presses == 1
        mock_pyautogui.press.assert_called_once_with("enter", presses=1, interval=0.0)

    def test_press_multiple_times(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_press']
        
        result = tool(context=None, key="tab", presses=3)
        
        assert result.success is True
        assert result.key == "tab"
        assert result.presses == 3
        mock_pyautogui.press.assert_called_once_with("tab", presses=3, interval=0.0)

    def test_press_with_interval(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_press']
        
        result = tool(context=None, key="backspace", presses=5, interval=0.1)
        
        assert result.success is True
        mock_pyautogui.press.assert_called_once_with("backspace", presses=5, interval=0.1)

    def test_press_arrow_keys(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_press']
        
        for arrow in ['up', 'down', 'left', 'right']:
            mock_pyautogui.reset_mock()
            result = tool(context=None, key=arrow)
            assert result.success is True
            assert result.key == arrow

    def test_press_function_keys(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_press']
        
        result = tool(context=None, key="f1")
        
        assert result.success is True
        assert result.key == "f1"
        mock_pyautogui.press.assert_called_once()


class TestDesktopKeyboardHotkey:
    """Test desktop_keyboard_hotkey function."""

    def test_copy_hotkey(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hotkey']
        
        # FIXED: Use proper *args unpacking
        result = tool(None, 'ctrl', 'c')
        
        assert isinstance(result, KeyboardActionResult)
        assert result.success is True
        assert result.hotkey == "ctrl+c"
        assert result.keys == ['ctrl', 'c']
        mock_pyautogui.hotkey.assert_called_once_with('ctrl', 'c')

    def test_paste_hotkey(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hotkey']
        
        result = tool(None, 'ctrl', 'v')
        
        assert result.success is True
        assert result.hotkey == "ctrl+v"
        assert result.keys == ['ctrl', 'v']

    def test_three_key_combination(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hotkey']
        
        result = tool(None, 'ctrl', 'shift', 's')
        
        assert result.success is True
        assert result.hotkey == "ctrl+shift+s"
        assert result.keys == ['ctrl', 'shift', 's']
        mock_pyautogui.hotkey.assert_called_once_with('ctrl', 'shift', 's')

    def test_alt_tab_hotkey(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hotkey']
        
        result = tool(None, 'alt', 'tab')
        
        assert result.success is True
        assert result.hotkey == "alt+tab"

    def test_command_space_hotkey(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hotkey']
        
        result = tool(None, 'command', 'space')
        
        assert result.success is True
        assert result.hotkey == "command+space"
        assert result.keys == ['command', 'space']


class TestDesktopKeyboardHold:
    """Test desktop_keyboard_hold function."""

    def test_hold_shift_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hold']
        
        result = tool(context=None, key="shift")
        
        assert isinstance(result, KeyboardActionResult)
        assert result.success is True
        assert result.key == "shift"
        assert result.status == "held"
        mock_pyautogui.keyDown.assert_called_once_with("shift")

    def test_hold_ctrl_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hold']
        
        result = tool(context=None, key="ctrl")
        
        assert result.success is True
        assert result.key == "ctrl"
        assert result.status == "held"
        mock_pyautogui.keyDown.assert_called_once_with("ctrl")

    def test_hold_alt_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_hold']
        
        result = tool(context=None, key="alt")
        
        assert result.success is True
        assert result.key == "alt"


class TestDesktopKeyboardRelease:
    """Test desktop_keyboard_release function."""

    def test_release_shift_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_release']
        
        result = tool(context=None, key="shift")
        
        assert isinstance(result, KeyboardActionResult)
        assert result.success is True
        assert result.key == "shift"
        assert result.status == "released"
        mock_pyautogui.keyUp.assert_called_once_with("shift")

    def test_release_ctrl_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_release']
        
        result = tool(context=None, key="ctrl")
        
        assert result.success is True
        assert result.key == "ctrl"
        assert result.status == "released"
        mock_pyautogui.keyUp.assert_called_once_with("ctrl")

    def test_release_alt_key(self, agent):
        mock_agent, mock_pyautogui = agent
        tool = mock_agent.tools['desktop_keyboard_release']
        
        result = tool(context=None, key="alt")
        
        assert result.success is True
        assert result.key == "alt"


class TestToolRegistration:
    """Test that all tools are properly registered."""

    def test_all_tools_registered(self, agent):
        mock_agent, _ = agent
        
        expected_tools = [
            'desktop_keyboard_type',
            'desktop_keyboard_press',
            'desktop_keyboard_hotkey',
            'desktop_keyboard_hold',
            'desktop_keyboard_release',
        ]
        
        for tool_name in expected_tools:
            assert tool_name in mock_agent.tools

    def test_tools_are_callable(self, agent):
        mock_agent, _ = agent
        
        for tool_name, tool_func in mock_agent.tools.items():
            assert callable(tool_func)


class TestHoldAndReleaseWorkflow:
    """Test hold and release workflow."""

    def test_hold_and_release_sequence(self, agent):
        mock_agent, mock_pyautogui = agent
        hold_tool = mock_agent.tools['desktop_keyboard_hold']
        release_tool = mock_agent.tools['desktop_keyboard_release']
        
        hold_result = hold_tool(context=None, key="shift")
        assert hold_result.success is True
        assert hold_result.status == "held"
        mock_pyautogui.keyDown.assert_called_with("shift")
        
        release_result = release_tool(context=None, key="shift")
        assert release_result.success is True
        assert release_result.status == "released"
        mock_pyautogui.keyUp.assert_called_with("shift")
