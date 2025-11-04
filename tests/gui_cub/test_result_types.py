"""Tests for RPA result type Pydantic models."""

import pytest
from pydantic import ValidationError

from code_puppy.tools.gui_cub.result_types import (
    BaseRPAResult,
    MouseActionResult,
    KeyboardActionResult,
    ScreenshotResult,
    WindowBoundsResult,
    ElementInfo,
)


class TestBaseRPAResult:
    """Test BaseRPAResult model."""
    
    def test_can_create_with_success(self):
        """Test creating result with success=True."""
        result = BaseRPAResult(success=True)
        assert result.success is True
        assert result.error is None
    
    def test_can_create_with_error(self):
        """Test creating result with error message."""
        result = BaseRPAResult(success=False, error="Test error")
        assert result.success is False
        assert result.error == "Test error"
    
    def test_success_is_required(self):
        """Test that success field is required."""
        with pytest.raises(ValidationError):
            BaseRPAResult()


class TestMouseActionResult:
    """Test MouseActionResult model."""
    
    def test_can_create_with_coordinates(self):
        """Test creating result with mouse coordinates."""
        result = MouseActionResult(
            success=True,
            x=100,
            y=200,
            button="left",
            clicks=1
        )
        assert result.x == 100
        assert result.y == 200
        assert result.button == "left"
        assert result.clicks == 1
    
    def test_button_must_be_valid_literal(self):
        """Test that button must be left/right/middle."""
        # Valid buttons should work
        for button in ["left", "right", "middle"]:
            result = MouseActionResult(success=True, button=button)
            assert result.button == button
        
        # Invalid button should fail
        with pytest.raises(ValidationError):
            MouseActionResult(success=True, button="invalid")
    
    def test_can_create_minimal(self):
        """Test creating result with minimal fields."""
        result = MouseActionResult(success=True)
        assert result.success is True
        assert result.x is None
        assert result.button is None


class TestKeyboardActionResult:
    """Test KeyboardActionResult model."""
    
    def test_can_create_with_text(self):
        """Test creating result with typed text info."""
        result = KeyboardActionResult(
            success=True,
            text_length=5,
            preview="Hello"
        )
        assert result.text_length == 5
        assert result.preview == "Hello"
    
    def test_can_create_with_hotkey(self):
        """Test creating result with hotkey info."""
        result = KeyboardActionResult(
            success=True,
            hotkey="Cmd+C",
            keys=["Cmd", "C"],
            platform="macOS"
        )
        assert result.hotkey == "Cmd+C"
        assert result.keys == ["Cmd", "C"]
        assert result.platform == "macOS"
    
    def test_can_create_minimal(self):
        """Test creating result with minimal fields."""
        result = KeyboardActionResult(success=True)
        assert result.success is True
        assert result.text_length is None


class TestWindowBoundsResult:
    """Test WindowBoundsResult model."""
    
    def test_can_create_with_bounds(self):
        """Test creating result with window bounds."""
        result = WindowBoundsResult(
            success=True,
            x=0,
            y=0,
            width=1920,
            height=1080,
            app_name="TestApp",
            window_title="Test Window"
        )
        
        assert result.x == 0
        assert result.y == 0
        assert result.width == 1920
        assert result.height == 1080
        assert result.app_name == "TestApp"
        assert result.window_title == "Test Window"
    
    def test_can_create_minimal(self):
        """Test creating result with minimal fields."""
        result = WindowBoundsResult(success=True)
        assert result.success is True
        assert result.x is None


class TestElementInfo:
    """Test ElementInfo model."""
    
    def test_can_create_minimal(self):
        """Test creating element with minimal info."""
        element = ElementInfo()
        assert element.role is None
        assert element.title is None
    
    def test_can_create_with_position(self):
        """Test creating element with position."""
        element = ElementInfo(
            role="Button",
            title="Submit",
            x=100, y=200,
            width=80, height=30,
            center_x=140, center_y=215
        )
        
        assert element.role == "Button"
        assert element.title == "Submit"
        assert element.x == 100
        assert element.center_x == 140
    
    def test_can_create_with_platform_specific_fields(self):
        """Test creating element with Windows-specific fields."""
        element = ElementInfo(
            control_type="Button",
            class_name="WinButton",
            auto_id="btn_submit"
        )
        
        assert element.control_type == "Button"
        assert element.class_name == "WinButton"
        assert element.auto_id == "btn_submit"


class TestScreenshotResult:
    """Test ScreenshotResult model."""
    
    def test_can_create_with_path(self):
        """Test creating screenshot result with file path."""
        result = ScreenshotResult(
            success=True,
            screenshot_path="/tmp/screenshot.png",
            width=1920,
            height=1080
        )
        
        assert result.screenshot_path == "/tmp/screenshot.png"
        assert result.width == 1920
        assert result.height == 1080
    
    def test_screenshot_data_excluded_from_serialization(self):
        """Test that screenshot_data is excluded from dict."""
        result = ScreenshotResult(
            success=True,
            screenshot_data=b"fake_image_data"
        )
        
        # screenshot_data should be excluded from dict
        result_dict = result.model_dump()
        assert "screenshot_data" not in result_dict
