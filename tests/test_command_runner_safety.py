"""Integration tests for safety validation in command runner."""

from unittest.mock import MagicMock, patch

from pydantic_ai import RunContext

from code_puppy.tools.command_runner import run_shell_command


class TestCommandRunnerSafetyIntegration:
    """Test safety validation integration with command runner."""

    @patch("code_puppy.tools.command_runner.validate_command_safety")
    @patch("code_puppy.config.get_yolo_mode")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_dangerous_command_blocked_before_execution(
        self, mock_permission, mock_yolo, mock_validate
    ):
        """Test that dangerous commands are blocked before execution."""
        # Setup
        mock_yolo.return_value = True  # Skip confirmation prompt
        mock_permission.return_value = "medium"

        # Mock validation to return dangerous and should_block=True
        mock_validation_result = MagicMock()
        mock_validation_result.is_safe = False
        mock_validation_result.risk_level = "critical"
        mock_validation_result.reasoning = "This command will destroy everything"
        mock_validation_result.error = None
        mock_validation_result.should_block = True  # Critical > medium
        mock_validate.return_value = mock_validation_result

        # Create a mock context
        mock_context = MagicMock(spec=RunContext)

        # Execute
        result = run_shell_command(mock_context, "rm -rf /")

        # Verify
        assert result.success is False
        assert result.exit_code == -2  # Safety block exit code
        assert "safety validation" in result.error.lower()
        assert "destroy everything" in result.error.lower()

    @patch("code_puppy.tools.command_runner.validate_command_safety")
    @patch("code_puppy.config.get_yolo_mode")
    @patch("code_puppy.config.get_safety_permission_level")
    @patch("code_puppy.tools.command_runner.subprocess.Popen")
    def test_safe_command_executes_normally(
        self, mock_popen, mock_permission, mock_yolo, mock_validate
    ):
        """Test that safe commands execute normally."""
        # Setup
        mock_yolo.return_value = True  # Skip confirmation prompt
        mock_permission.return_value = "medium"

        # Mock validation to return safe
        mock_validation_result = MagicMock()
        mock_validation_result.is_safe = True
        mock_validation_result.risk_level = "safe"
        mock_validation_result.reasoning = "Safe command"
        mock_validation_result.error = None
        mock_validation_result.should_block = False
        mock_validate.return_value = mock_validation_result

        # Mock process execution
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        mock_process.returncode = 0
        mock_process.pid = 12345
        mock_process.stdout.readline.side_effect = ["output\n", ""]
        mock_process.stderr.readline.side_effect = [""]
        mock_popen.return_value = mock_process

        # Create a mock context
        mock_context = MagicMock(spec=RunContext)

        # Execute
        run_shell_command(mock_context, "echo hello")

        # Verify validation was called
        mock_validate.assert_called_once()

        # Verify command was executed (Popen was called)
        mock_popen.assert_called_once()

    @patch("code_puppy.tools.command_runner.validate_command_safety")
    @patch("code_puppy.config.get_yolo_mode")
    @patch("code_puppy.config.get_safety_permission_level")
    def test_validation_error_logged_but_allows_execution(
        self, mock_permission, mock_yolo, mock_validate
    ):
        """Test that validation errors are logged but don't block (fail open)."""
        # Setup
        mock_yolo.return_value = True
        mock_permission.return_value = "medium"

        # Mock validation to return safe with error
        mock_validation_result = MagicMock()
        mock_validation_result.is_safe = True  # Fail open
        mock_validation_result.risk_level = "unknown"
        mock_validation_result.reasoning = "Service unavailable"
        mock_validation_result.error = "Connection timeout"
        mock_validation_result.should_block = False  # Fail open
        mock_validate.return_value = mock_validation_result

        # Create a mock context
        mock_context = MagicMock(spec=RunContext)

        # Since validation passed (fail open), the command will proceed
        # to normal execution flow. We'll just verify validation was called.
        with patch("code_puppy.tools.command_runner.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 0
            mock_process.returncode = 0
            mock_process.pid = 12345
            mock_process.stdout.readline.side_effect = [""]
            mock_process.stderr.readline.side_effect = [""]
            mock_popen.return_value = mock_process

            run_shell_command(mock_context, "ls")

            # Verify validation was called
            mock_validate.assert_called_once()

            # Command should have been executed despite validation error
            mock_popen.assert_called_once()

    def test_empty_command_rejected_before_validation(self):
        """Test that empty commands are rejected before validation."""
        mock_context = MagicMock(spec=RunContext)

        result = run_shell_command(mock_context, "")

        assert result.success is False
        assert "empty" in result.error.lower()
