"""Tests for code_puppy.plugins package __init__.py.

This module tests plugin loading functionality including error handling.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLoadPluginCallbacks:
    """Test the load_plugin_callbacks function."""

    def test_load_plugin_callbacks_callable(self):
        """Test that load_plugin_callbacks function exists and is callable."""
        from code_puppy.plugins import load_plugin_callbacks
        
        assert callable(load_plugin_callbacks)

    @patch("code_puppy.plugins.importlib.import_module")
    def test_import_error_is_caught(self, mock_import):
        """Test that ImportError is caught and doesn't crash."""
        from code_puppy.plugins import load_plugin_callbacks
        
        # Mock the plugins directory to have a test plugin
        with patch("code_puppy.plugins.Path") as mock_path_class:
            mock_plugin_dir = MagicMock()
            mock_plugin_dir.name = "test_plugin"
            mock_plugin_dir.is_dir.return_value = True
            
            mock_callbacks_file = MagicMock()
            mock_callbacks_file.exists.return_value = True
            mock_plugin_dir.__truediv__.return_value = mock_callbacks_file
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_plugin_dir]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            # Make import_module raise ImportError
            mock_import.side_effect = ImportError("Module not found")
            
            # Should not raise - error is caught
            load_plugin_callbacks()

    @patch("code_puppy.plugins.importlib.import_module")
    def test_unexpected_error_is_caught(self, mock_import):
        """Test that unexpected errors are caught and don't crash."""
        from code_puppy.plugins import load_plugin_callbacks
        
        with patch("code_puppy.plugins.Path") as mock_path_class:
            mock_plugin_dir = MagicMock()
            mock_plugin_dir.name = "error_plugin"
            mock_plugin_dir.is_dir.return_value = True
            
            mock_callbacks_file = MagicMock()
            mock_callbacks_file.exists.return_value = True
            mock_plugin_dir.__truediv__.return_value = mock_callbacks_file
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_plugin_dir]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            # Make import_module raise unexpected error
            mock_import.side_effect = RuntimeError("Unexpected error")
            
            # Should not raise - error is caught
            load_plugin_callbacks()

    @patch("code_puppy.plugins.importlib.import_module")
    def test_successful_load_completes(self, mock_import):
        """Test that successful plugin loading completes without error."""
        from code_puppy.plugins import load_plugin_callbacks
        
        with patch("code_puppy.plugins.Path") as mock_path_class:
            mock_plugin_dir = MagicMock()
            mock_plugin_dir.name = "good_plugin"
            mock_plugin_dir.is_dir.return_value = True
            
            mock_callbacks_file = MagicMock()
            mock_callbacks_file.exists.return_value = True
            mock_plugin_dir.__truediv__.return_value = mock_callbacks_file
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_plugin_dir]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            # Successful import
            mock_import.return_value = MagicMock()
            
            # Should complete without error
            load_plugin_callbacks()

    def test_skips_non_directory_items(self):
        """Test that non-directory items are skipped."""
        from code_puppy.plugins import load_plugin_callbacks
        
        with patch("code_puppy.plugins.Path") as mock_path_class:
            # Create a mock file (not a directory)
            mock_file = MagicMock()
            mock_file.name = "not_a_dir.py"
            mock_file.is_dir.return_value = False
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_file]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            with patch("code_puppy.plugins.importlib.import_module") as mock_import:
                # Call the function
                load_plugin_callbacks()
                
                # Should not try to import
                mock_import.assert_not_called()

    def test_skips_hidden_directories(self):
        """Test that directories starting with _ are skipped."""
        from code_puppy.plugins import load_plugin_callbacks
        
        with patch("code_puppy.plugins.Path") as mock_path_class:
            # Create a mock hidden directory
            mock_hidden_dir = MagicMock()
            mock_hidden_dir.name = "_hidden"
            mock_hidden_dir.is_dir.return_value = True
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_hidden_dir]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            with patch("code_puppy.plugins.importlib.import_module") as mock_import:
                # Call the function
                load_plugin_callbacks()
                
                # Should not try to import hidden directories
                mock_import.assert_not_called()

    def test_skips_directories_without_register_callbacks(self):
        """Test that directories without register_callbacks.py are skipped."""
        from code_puppy.plugins import load_plugin_callbacks
        
        with patch("code_puppy.plugins.Path") as mock_path_class:
            mock_plugin_dir = MagicMock()
            mock_plugin_dir.name = "incomplete_plugin"
            mock_plugin_dir.is_dir.return_value = True
            
            # Make register_callbacks.py NOT exist
            mock_callbacks_file = MagicMock()
            mock_callbacks_file.exists.return_value = False
            mock_plugin_dir.__truediv__.return_value = mock_callbacks_file
            
            mock_parent = MagicMock()
            mock_parent.iterdir.return_value = [mock_plugin_dir]
            mock_path_instance = MagicMock()
            mock_path_instance.parent = mock_parent
            mock_path_class.return_value = mock_path_instance
            
            with patch("code_puppy.plugins.importlib.import_module") as mock_import:
                # Call the function
                load_plugin_callbacks()
                
                # Should not try to import
                mock_import.assert_not_called()
