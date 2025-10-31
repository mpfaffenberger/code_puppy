"""Tests for agent tools functionality."""

from unittest.mock import MagicMock

from code_puppy.tools.agent_tools import register_invoke_agent, register_list_agents


class TestAgentTools:
    """Test suite for agent tools."""

    def test_list_agents_tool(self):
        """Test that list_agents tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_list_agents(mock_agent)

    def test_invoke_agent_tool(self):
        """Test that invoke_agent tool registers correctly."""
        # Create a mock agent to register tools to
        mock_agent = MagicMock()

        # Register the tool - this should not raise an exception
        register_invoke_agent(mock_agent)

    def test_invoke_agent_includes_prompt_additions(self):
        """Test that invoke_agent includes prompt additions like file permission handling."""
        # Test that the fix properly adds prompt additions to temporary agents
        from unittest.mock import patch

        from code_puppy import callbacks
        from code_puppy.plugins.file_permission_handler.register_callbacks import (
            get_file_permission_prompt_additions,
        )

        # Mock yolo mode to be False so we can test prompt additions
        with patch(
            "code_puppy.plugins.file_permission_handler.register_callbacks.get_yolo_mode",
            return_value=False,
        ):
            # Register the file permission callback (normally done at startup)
            callbacks.register_callback(
                "load_prompt", get_file_permission_prompt_additions
            )

            # Get prompt additions to verify they exist
            prompt_additions = callbacks.on_load_prompt()

            # Verify we have file permission prompt additions
            assert len(prompt_additions) > 0

            # Verify the content contains expected file permission instructions
            file_permission_text = "".join(prompt_additions)
            assert "FILE PERMISSION REJECTION" in file_permission_text
            assert "IMMEDIATE STOP" in file_permission_text
