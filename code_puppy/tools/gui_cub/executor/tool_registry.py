"""Tool registry for workflow executor.

This module provides a centralized registry of GUI-Cub tool functions
that can be used by the WorkflowExecutor. This eliminates the need for
direct imports in the executor and provides a single source of truth
for all available tools.

Architectural Benefits:
- No direct imports in WorkflowExecutor
- Single source of truth for tool functions
- Easy to add new tools
- Consistent with agent tools architecture
- Can be extended with validation and metadata
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from pydantic_ai import RunContext


class ToolRegistry:
    """Registry of GUI-Cub tool functions for workflow executor.
    
    This class holds references to all tool functions that can be called
    by workflows. It provides a clean interface for accessing tools without
    direct imports.
    """

    def __init__(self):
        """Initialize the tool registry with all available tool functions."""
        # Import tools here to populate the registry
        # This is the ONLY place where these imports happen
        
        # Keyboard control tools
        from code_puppy.tools.gui_cub.keyboard_control import (
            desktop_keyboard_type,
            desktop_keyboard_press,
            desktop_keyboard_hotkey,
        )
        
        # Mouse control tools
        from code_puppy.tools.gui_cub.mouse_control import desktop_mouse_click
        
        # Window control tools
        from code_puppy.tools.gui_cub.window_control import focus_window
        
        # Multi-strategy click
        from code_puppy.tools.gui_cub.multi_strategy_click import (
            desktop_click_element_smart,
        )
        
        # OCR tools
        from code_puppy.tools.gui_cub.ocr.tools import (
            desktop_find_text,
            desktop_extract_text,
        )
        
        # OS unified tools
        from code_puppy.tools.gui_cub.os_unified import ui_click_element
        
        # Screen capture tools
        from code_puppy.tools.gui_cub.screen_capture import (
            screenshot,
            screenshot_analyze,
        )
        
        # Store tool functions in registry
        self._tools = {
            # Keyboard control
            "keyboard_type": desktop_keyboard_type,
            "keyboard_press": desktop_keyboard_press,
            "keyboard_hotkey": desktop_keyboard_hotkey,
            
            # Mouse control
            "mouse_click": desktop_mouse_click,
            
            # Window control
            "focus_window": focus_window,
            
            # Multi-strategy click
            "click_element_smart": desktop_click_element_smart,
            
            # OCR
            "find_text": desktop_find_text,
            "extract_text": desktop_extract_text,
            
            # OS unified
            "ui_click_element": ui_click_element,
            
            # Screen capture
            "screenshot": screenshot,
            "screenshot_analyze": screenshot_analyze,
        }
    
    def get(self, tool_name: str) -> Callable:
        """Get a tool function by name.
        
        Args:
            tool_name: Name of the tool to retrieve
            
        Returns:
            The tool function
            
        Raises:
            KeyError: If tool name is not found in registry
        """
        if tool_name not in self._tools:
            available = ", ".join(sorted(self._tools.keys()))
            raise KeyError(
                f"Tool '{tool_name}' not found in registry. "
                f"Available tools: {available}"
            )
        return self._tools[tool_name]
    
    def __getattr__(self, name: str) -> Callable:
        """Allow attribute-style access to tools.
        
        Example:
            tools.keyboard_type(context, "hello")
        """
        try:
            return self.get(name)
        except KeyError:
            raise AttributeError(
                f"ToolRegistry has no attribute '{name}'"
            ) from None
    
    @property
    def available_tools(self) -> list[str]:
        """Get list of all available tool names."""
        return sorted(self._tools.keys())


# Global registry instance
_registry = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance (singleton pattern).
    
    Returns:
        The global ToolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
