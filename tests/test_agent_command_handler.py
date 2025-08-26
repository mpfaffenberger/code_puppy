"""Tests for the /agent command in command handler."""

import pytest
from unittest.mock import patch, MagicMock

from code_puppy.command_line.command_handler import handle_command


class TestAgentCommand:
    """Test the /agent command functionality."""
    
    @patch('code_puppy.messaging.emit_info')
    @patch('code_puppy.messaging.emit_success')
    @patch('code_puppy.messaging.emit_error')
    @patch('code_puppy.messaging.emit_warning')
    @patch('code_puppy.agents.get_current_agent_config')
    @patch('code_puppy.agents.get_available_agents')
    @patch('code_puppy.agents.get_agent_descriptions')
    def test_agent_command_list(self, mock_descriptions, mock_available, 
                               mock_current, mock_warn, mock_error, 
                               mock_success, mock_info):
        """Test /agent command without arguments shows agent list."""
        # Mock the current agent
        mock_agent = MagicMock()
        mock_agent.display_name = "Code-Puppy 🐶"
        mock_agent.description = "The most loyal digital puppy"
        mock_agent.name = "code-puppy"
        mock_current.return_value = mock_agent
        
        # Mock available agents
        mock_available.return_value = {
            "code-puppy": "Code-Puppy 🐶"
        }
        
        # Mock descriptions
        mock_descriptions.return_value = {
            "code-puppy": "The most loyal digital puppy"
        }
        
        result = handle_command("/agent")
        
        assert result is True
        assert mock_info.call_count >= 3  # Should show current + available agents
    
    @patch('code_puppy.messaging.emit_success')
    @patch('code_puppy.messaging.emit_info')
    @patch('code_puppy.agents.set_current_agent')
    @patch('code_puppy.agents.get_current_agent_config')
    @patch('code_puppy.agent.get_code_generation_agent')
    def test_agent_command_switch_valid(self, mock_get_agent, mock_current_config,
                                      mock_set_agent, mock_info, mock_success):
        """Test /agent command with valid agent name switches agent."""
        # Mock successful agent switch
        mock_set_agent.return_value = True
        
        # Mock the new agent config
        mock_agent = MagicMock()
        mock_agent.display_name = "Code-Puppy 🐶"
        mock_agent.description = "The most loyal digital puppy"
        mock_current_config.return_value = mock_agent
        
        result = handle_command("/agent code-puppy")
        
        assert result is True
        mock_set_agent.assert_called_once_with("code-puppy")
        mock_get_agent.assert_called_once_with(force_reload=True)
        mock_success.assert_called_once()
    
    @patch('code_puppy.messaging.emit_error')
    @patch('code_puppy.messaging.emit_warning')
    @patch('code_puppy.agents.set_current_agent')
    @patch('code_puppy.agents.get_available_agents')
    def test_agent_command_switch_invalid(self, mock_available, mock_set_agent,
                                        mock_warning, mock_error):
        """Test /agent command with invalid agent name shows error."""
        # Mock failed agent switch
        mock_set_agent.return_value = False
        mock_available.return_value = {"code-puppy": "Code-Puppy 🐶"}
        
        result = handle_command("/agent nonexistent")
        
        assert result is True
        mock_set_agent.assert_called_once_with("nonexistent")
        mock_error.assert_called_once()
        mock_warning.assert_called_once()
    
    @patch('code_puppy.messaging.emit_warning')
    def test_agent_command_too_many_args(self, mock_warning):
        """Test /agent command with too many arguments shows usage."""
        result = handle_command("/agent code-puppy extra args")
        
        assert result is True
        mock_warning.assert_called_once_with("Usage: /agent [agent-name]")
    
    def test_agent_command_case_insensitive(self):
        """Test that agent names are case insensitive."""
        with patch('code_puppy.agents.set_current_agent') as mock_set_agent:
            mock_set_agent.return_value = True
            
            with patch('code_puppy.agents.get_current_agent_config'):
                with patch('code_puppy.agent.get_code_generation_agent'):
                    with patch('code_puppy.messaging.emit_success'):
                        with patch('code_puppy.messaging.emit_info'):
                            handle_command("/agent CODE-PUPPY")
                            
            # Should convert to lowercase
            mock_set_agent.assert_called_once_with("code-puppy")
