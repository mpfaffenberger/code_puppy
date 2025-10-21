"""Comprehensive unit tests for code_puppy.messaging.spinner module.

Tests spinner registration and management functions.
"""
import pytest
from unittest.mock import Mock, patch

from code_puppy.messaging.spinner import (
    register_spinner,
    unregister_spinner,
    pause_all_spinners,
    resume_all_spinners,
    update_spinner_context,
    clear_spinner_context,
    SpinnerBase,
    ConsoleSpinner,
    TextualSpinner,
)


class TestSpinnerRegistration:
    """Test spinner registration and unregistration."""
    
    def setup_method(self):
        """Clear active spinners before each test."""
        import code_puppy.messaging.spinner as spinner_module
        spinner_module._active_spinners.clear()
    
    def test_register_spinner(self):
        """Test registering a spinner."""
        mock_spinner = Mock()
        
        register_spinner(mock_spinner)
        
        import code_puppy.messaging.spinner as spinner_module
        assert mock_spinner in spinner_module._active_spinners
    
    def test_register_spinner_duplicate(self):
        """Test registering same spinner twice doesn't duplicate."""
        mock_spinner = Mock()
        
        register_spinner(mock_spinner)
        register_spinner(mock_spinner)  # Register again
        
        import code_puppy.messaging.spinner as spinner_module
        # Should only appear once
        assert spinner_module._active_spinners.count(mock_spinner) == 1
    
    def test_register_multiple_spinners(self):
        """Test registering multiple different spinners."""
        spinner1 = Mock()
        spinner2 = Mock()
        spinner3 = Mock()
        
        register_spinner(spinner1)
        register_spinner(spinner2)
        register_spinner(spinner3)
        
        import code_puppy.messaging.spinner as spinner_module
        assert len(spinner_module._active_spinners) == 3


class TestPauseAllSpinners:
    """Test pausing all active spinners."""
    
    def setup_method(self):
        """Clear active spinners before each test."""
        import code_puppy.messaging.spinner as spinner_module
        spinner_module._active_spinners.clear()
    
    def test_pause_all_spinners(self):
        """Test pause_all_spinners calls pause on all spinners."""
        spinner1 = Mock()
        spinner2 = Mock()
        
        register_spinner(spinner1)
        register_spinner(spinner2)
        
        pause_all_spinners()
        
        spinner1.pause.assert_called_once()
        spinner2.pause.assert_called_once()
    
    def test_pause_all_spinners_with_error(self):
        """Test pause_all_spinners handles errors gracefully."""
        spinner1 = Mock()
        spinner2 = Mock()
        spinner1.pause.side_effect = RuntimeError("Pause failed")
        
        register_spinner(spinner1)
        register_spinner(spinner2)
        
        # Should not raise, should continue to next spinner
        pause_all_spinners()
        
        spinner1.pause.assert_called_once()
        spinner2.pause.assert_called_once()


class TestResumeAllSpinners:
    """Test resuming all active spinners."""
    
    def setup_method(self):
        """Clear active spinners before each test."""
        import code_puppy.messaging.spinner as spinner_module
        spinner_module._active_spinners.clear()
    
    def test_resume_all_spinners(self):
        """Test resume_all_spinners calls resume on all spinners."""
        spinner1 = Mock()
        spinner2 = Mock()
        
        register_spinner(spinner1)
        register_spinner(spinner2)
        
        resume_all_spinners()
        
        spinner1.resume.assert_called_once()
        spinner2.resume.assert_called_once()
    
    def test_resume_all_spinners_with_error(self):
        """Test resume_all_spinners handles errors gracefully."""
        spinner1 = Mock()
        spinner2 = Mock()
        spinner1.resume.side_effect = RuntimeError("Resume failed")
        
        register_spinner(spinner1)
        register_spinner(spinner2)
        
        # Should not raise, should continue to next spinner
        resume_all_spinners()
        
        spinner1.resume.assert_called_once()
        spinner2.resume.assert_called_once()


class TestSpinnerContext:
    """Test spinner context management."""
    
    @patch.object(SpinnerBase, 'set_context_info')
    def test_update_spinner_context(self, mock_set_context):
        """Test update_spinner_context calls SpinnerBase.set_context_info."""
        update_spinner_context("Processing...")
        
        mock_set_context.assert_called_once_with("Processing...")
    
    @patch.object(SpinnerBase, 'clear_context_info')
    def test_clear_spinner_context(self, mock_clear_context):
        """Test clear_spinner_context calls SpinnerBase.clear_context_info."""
        clear_spinner_context()
        
        mock_clear_context.assert_called_once()
