"""Unit tests for code_puppy.command_line.model_picker_completion module."""
from unittest.mock import Mock, patch
import pytest

from code_puppy.command_line.model_picker_completion import (
    load_model_names,
    get_active_model,
    set_active_model,
    ModelNameCompleter,
)


class TestLoadModelNames:
    """Test load_model_names function."""
    
    @patch('code_puppy.command_line.model_picker_completion.ModelFactory.load_config')
    def test_load_model_names(self, mock_load_config):
        """Test loading model names from config."""
        mock_load_config.return_value = {
            "gpt-4": {},
            "gpt-3.5-turbo": {},
            "claude-3": {},
        }
        
        names = load_model_names()
        
        assert len(names) == 3
        assert "gpt-4" in names


class TestGetActiveModel:
    """Test get_active_model function."""
    
    @patch('code_puppy.command_line.model_picker_completion.get_global_model_name')
    def test_get_active_model(self, mock_get_global):
        """Test getting active model name."""
        mock_get_global.return_value = "gpt-4"
        
        model = get_active_model()
        
        assert model == "gpt-4"


class TestSetActiveModel:
    """Test set_active_model function."""
    
    @patch('code_puppy.command_line.model_picker_completion.set_model_name')
    @patch('code_puppy.agents.get_current_agent')
    def test_set_active_model_success(self, mock_get_agent, mock_set_name):
        """Test setting active model successfully."""
        mock_agent = Mock()
        mock_get_agent.return_value = mock_agent
        
        set_active_model("gpt-4")
        
        mock_set_name.assert_called_once_with("gpt-4")
        mock_agent.reload_code_generation_agent.assert_called_once()
    
    @patch('code_puppy.command_line.model_picker_completion.set_model_name')
    @patch('code_puppy.agents.get_current_agent')
    def test_set_active_model_with_refresh_config(self, mock_get_agent, mock_set_name):
        """Test setting model with refresh_config support."""
        mock_agent = Mock()
        mock_agent.refresh_config = Mock()
        mock_get_agent.return_value = mock_agent
        
        set_active_model("claude-3")
        
        mock_agent.refresh_config.assert_called_once()
        mock_agent.reload_code_generation_agent.assert_called_once()
    
    @patch('code_puppy.command_line.model_picker_completion.set_model_name')
    @patch('code_puppy.agents.get_current_agent')
    def test_set_active_model_agent_fails(self, mock_get_agent, mock_set_name):
        """Test setting model when agent operations fail."""
        mock_get_agent.side_effect = RuntimeError("Agent error")
        
        # Should not raise, should swallow error
        set_active_model("gpt-4")
        
        mock_set_name.assert_called_once_with("gpt-4")


class TestModelNameCompleter:
    """Test ModelNameCompleter class."""
    
    @patch('code_puppy.command_line.model_picker_completion.load_model_names')
    def test_completer_init(self, mock_load):
        """Test ModelNameCompleter initialization."""
        mock_load.return_value = ["gpt-4", "claude-3"]
        
        completer = ModelNameCompleter()
        
        assert completer.trigger == "/model"
        assert completer.model_names == ["gpt-4", "claude-3"]
    
    @patch('code_puppy.command_line.model_picker_completion.load_model_names')
    @patch('code_puppy.command_line.model_picker_completion.get_active_model')
    def test_get_completions_with_trigger(self, mock_active, mock_load):
        """Test completions when trigger is present."""
        mock_load.return_value = ["gpt-4", "gpt-3.5-turbo"]
        mock_active.return_value = "gpt-4"
        
        completer = ModelNameCompleter()
        
        from prompt_toolkit.document import Document
        doc = Document(text="/model ", cursor_position=7)
        
        completions = list(completer.get_completions(doc, None))
        
        assert len(completions) == 2
        assert any(c.text == "gpt-4" for c in completions)
    
    @patch('code_puppy.command_line.model_picker_completion.load_model_names')
    @patch('code_puppy.command_line.model_picker_completion.get_active_model')
    def test_get_completions_no_trigger(self, mock_active, mock_load):
        """Test no completions when trigger not present."""
        mock_load.return_value = ["gpt-4"]
        mock_active.return_value = "gpt-4"
        
        completer = ModelNameCompleter()
        
        from prompt_toolkit.document import Document
        doc = Document(text="hello ", cursor_position=6)
        
        completions = list(completer.get_completions(doc, None))
        
        assert len(completions) == 0
