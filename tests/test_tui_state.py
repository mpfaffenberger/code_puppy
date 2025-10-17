"""Tests for code_puppy.tui_state.

This module tests the TUI state management functions that control
global state for the TUI application mode and instance.
"""

import pytest

from code_puppy.tui_state import (
    get_tui_app_instance,
    get_tui_mode,
    is_tui_mode,
    set_tui_app_instance,
    set_tui_mode,
)


@pytest.fixture(autouse=True)
def reset_tui_state():
    """Reset TUI state to default values before each test.
    
    This fixture runs automatically before each test to ensure
    tests don't affect each other through global state.
    """
    # Reset to default state before test
    set_tui_mode(False)
    set_tui_app_instance(None)
    
    yield
    
    # Clean up after test
    set_tui_mode(False)
    set_tui_app_instance(None)


class TestTuiModeState:
    """Test TUI mode state management functions."""

    def test_initial_tui_mode_is_false(self):
        """Test that TUI mode starts as False by default."""
        # After fixture reset, mode should be False
        assert is_tui_mode() is False
        assert get_tui_mode() is False

    def test_set_tui_mode_to_true(self):
        """Test enabling TUI mode."""
        set_tui_mode(True)
        
        assert is_tui_mode() is True
        assert get_tui_mode() is True

    def test_set_tui_mode_to_false(self):
        """Test disabling TUI mode."""
        # First enable it
        set_tui_mode(True)
        assert is_tui_mode() is True
        
        # Then disable it
        set_tui_mode(False)
        assert is_tui_mode() is False
        assert get_tui_mode() is False

    def test_is_tui_mode_reflects_current_state(self):
        """Test that is_tui_mode() returns current state."""
        # Start False
        assert is_tui_mode() is False
        
        # Change to True
        set_tui_mode(True)
        assert is_tui_mode() is True
        
        # Change back to False
        set_tui_mode(False)
        assert is_tui_mode() is False

    def test_get_tui_mode_reflects_current_state(self):
        """Test that get_tui_mode() returns current state."""
        # Start False
        assert get_tui_mode() is False
        
        # Change to True
        set_tui_mode(True)
        assert get_tui_mode() is True
        
        # Change back to False
        set_tui_mode(False)
        assert get_tui_mode() is False

    def test_get_tui_mode_and_is_tui_mode_are_equivalent(self):
        """Test that get_tui_mode() and is_tui_mode() return the same value.
        
        Note: These are duplicate functions - both should always return
        the same result for any given state.
        """
        # Test when False
        set_tui_mode(False)
        assert get_tui_mode() == is_tui_mode()
        assert get_tui_mode() is False
        
        # Test when True
        set_tui_mode(True)
        assert get_tui_mode() == is_tui_mode()
        assert get_tui_mode() is True

    def test_tui_mode_toggle_multiple_times(self):
        """Test toggling TUI mode multiple times."""
        # Should be able to toggle state multiple times without issues
        for _ in range(3):
            set_tui_mode(True)
            assert is_tui_mode() is True
            
            set_tui_mode(False)
            assert is_tui_mode() is False


class TestTuiAppInstance:
    """Test TUI app instance management functions."""

    def test_initial_app_instance_is_none(self):
        """Test that app instance starts as None by default."""
        assert get_tui_app_instance() is None

    def test_set_tui_app_instance_with_object(self):
        """Test setting app instance with a mock object."""
        mock_app = {"name": "test_app", "version": "1.0"}
        
        set_tui_app_instance(mock_app)
        
        assert get_tui_app_instance() is mock_app
        assert get_tui_app_instance() == {"name": "test_app", "version": "1.0"}

    def test_get_tui_app_instance_returns_set_value(self):
        """Test that getter returns the value set by setter."""
        test_value = "test_instance"
        
        set_tui_app_instance(test_value)
        
        assert get_tui_app_instance() == test_value

    def test_app_instance_can_be_string(self):
        """Test that app instance can be a string (Any type)."""
        test_string = "my_app_instance"
        
        set_tui_app_instance(test_string)
        
        assert get_tui_app_instance() == test_string
        assert isinstance(get_tui_app_instance(), str)

    def test_app_instance_can_be_dict(self):
        """Test that app instance can be a dict (Any type)."""
        test_dict = {"key": "value", "number": 42}
        
        set_tui_app_instance(test_dict)
        
        assert get_tui_app_instance() == test_dict
        assert isinstance(get_tui_app_instance(), dict)

    def test_app_instance_can_be_class_instance(self):
        """Test that app instance can be a class instance (Any type)."""
        class MockApp:
            def __init__(self, name):
                self.name = name
        
        mock_app = MockApp("test")
        
        set_tui_app_instance(mock_app)
        
        retrieved = get_tui_app_instance()
        assert retrieved is mock_app
        assert retrieved.name == "test"

    def test_app_instance_can_be_none(self):
        """Test that app instance can be explicitly set to None."""
        # First set to something
        set_tui_app_instance("something")
        assert get_tui_app_instance() == "something"
        
        # Then set back to None
        set_tui_app_instance(None)
        assert get_tui_app_instance() is None

    def test_app_instance_replacement(self):
        """Test that setting a new instance replaces the old one."""
        first_instance = "first"
        second_instance = "second"
        
        set_tui_app_instance(first_instance)
        assert get_tui_app_instance() == "first"
        
        set_tui_app_instance(second_instance)
        assert get_tui_app_instance() == "second"
        assert get_tui_app_instance() != "first"


class TestTuiStateIndependence:
    """Test that TUI mode and app instance are independent."""

    def test_mode_and_instance_are_independent(self):
        """Test that setting mode doesn't affect instance and vice versa."""
        # Set both
        set_tui_mode(True)
        set_tui_app_instance("test_app")
        
        assert is_tui_mode() is True
        assert get_tui_app_instance() == "test_app"
        
        # Change mode, instance should remain
        set_tui_mode(False)
        assert is_tui_mode() is False
        assert get_tui_app_instance() == "test_app"  # Unchanged
        
        # Change instance, mode should remain
        set_tui_app_instance("new_app")
        assert is_tui_mode() is False  # Unchanged
        assert get_tui_app_instance() == "new_app"

    def test_can_have_instance_without_mode(self):
        """Test that app instance can be set while TUI mode is False."""
        set_tui_mode(False)
        set_tui_app_instance("app_instance")
        
        assert is_tui_mode() is False
        assert get_tui_app_instance() == "app_instance"

    def test_can_have_mode_without_instance(self):
        """Test that TUI mode can be True while app instance is None."""
        set_tui_mode(True)
        set_tui_app_instance(None)
        
        assert is_tui_mode() is True
        assert get_tui_app_instance() is None
