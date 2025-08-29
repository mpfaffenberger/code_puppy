"""Tests for the /agent command handling in TUI mode."""

from unittest.mock import patch, MagicMock

from code_puppy.tui.app import CodePuppyTUI


class TestTUIAgentCommand:
    """Test the TUI's handling of /agent commands."""

    @patch("code_puppy.tui.app.get_code_generation_agent")
    @patch("code_puppy.tui.app.handle_command")
    def test_tui_handles_agent_command(self, mock_handle_command, mock_get_agent):
        """Test that TUI properly delegates /agent commands to command handler."""
        # Create a TUI app instance
        app = CodePuppyTUI()

        # Mock the agent
        mock_agent_instance = MagicMock()
        mock_get_agent.return_value = mock_agent_instance

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

        # Verify that get_code_generation_agent was called to refresh the agent instance
        mock_get_agent.assert_called()

    @patch("code_puppy.tui.app.get_code_generation_agent")
    def test_tui_refreshes_agent_after_command(self, mock_get_agent):
        """Test that TUI refreshes its agent instance after processing /agent command."""
        # Create a TUI app instance
        app = CodePuppyTUI()

        # Set initial agent
        initial_agent = MagicMock()
        app.agent = initial_agent

        # Mock get_code_generation_agent to return a new agent instance
        new_agent = MagicMock()
        mock_get_agent.return_value = new_agent

        # Simulate that an /agent command was processed
        with patch("code_puppy.tui.app.handle_command"):
            import asyncio

            loop = asyncio.get_event_loop()
            loop.run_until_complete(app.process_message("/agent code-puppy"))

        # Verify that the agent was refreshed
        mock_get_agent.assert_called()
