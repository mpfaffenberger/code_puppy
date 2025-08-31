"""Tests for the /agent command handling in TUI mode."""

from unittest.mock import patch, MagicMock

from code_puppy.tui.app import CodePuppyTUI


class TestTUIAgentCommand:
    """Test the TUI's handling of /agent commands."""

    @patch("code_puppy.tui.app.get_runtime_agent_manager")
    @patch("code_puppy.tui.app.handle_command")
    def test_tui_handles_agent_command(self, mock_handle_command, mock_get_manager):
        """Test that TUI properly delegates /agent commands to command handler."""
        # Create a TUI app instance
        app = CodePuppyTUI()

        # Mock the agent manager and agent
        mock_agent_instance = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_agent.return_value = mock_agent_instance
        mock_get_manager.return_value = mock_manager

        # Mock handle_command to simulate successful processing
        mock_handle_command.return_value = True

        # Simulate processing an /agent command
        message = "/agent code-puppy"
        app.agent = mock_agent_instance

        # Call the method that processes messages
        # We'll need to mock some UI elements to avoid complex setup
        with (
            patch.object(app, "add_user_message"),
            patch.object(app, "_update_submit_cancel_button"),
            patch.object(app, "start_agent_progress"),
            patch.object(app, "stop_agent_progress"),
            patch.object(app, "refresh_history_display"),
        ):
            import asyncio

            # Create an event loop for the async test
            loop = asyncio.get_event_loop()
            loop.run_until_complete(app.process_message(message))

        # Verify that handle_command was called with the correct argument
        mock_handle_command.assert_called_once_with(message)

        # Verify that agent manager's get_agent was called to refresh the agent instance
        mock_manager.get_agent.assert_called()

    @patch("code_puppy.tui.app.get_runtime_agent_manager")
    def test_tui_refreshes_agent_after_command(self, mock_get_manager):
        """Test that TUI refreshes its agent instance after processing /agent command."""
        # Create a TUI app instance
        app = CodePuppyTUI()

        # Mock the agent manager
        mock_manager = MagicMock()
        initial_agent = MagicMock()
        new_agent = MagicMock()
        
        # Set initial agent
        app.agent = initial_agent
        app.agent_manager = mock_manager
        
        # Mock manager to return a new agent instance
        mock_manager.get_agent.return_value = new_agent
        mock_get_manager.return_value = mock_manager

        # Simulate that an /agent command was processed
        with patch("code_puppy.tui.app.handle_command"):
            import asyncio

            loop = asyncio.get_event_loop()
            loop.run_until_complete(app.process_message("/agent code-puppy"))

        # Verify that the agent was refreshed through the manager
        mock_manager.get_agent.assert_called()
