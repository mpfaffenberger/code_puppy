"""Unit tests for MS Graph approval TUI whitelist instructions."""

import pytest
from unittest.mock import patch, MagicMock

from code_puppy.tools.msgraph.approval_tui import (
    _get_whitelist_instructions,
    _fallback_prompt,
    request_approval,
    ApprovalState,
)


class TestGetWhitelistInstructions:
    """Test suite for _get_whitelist_instructions helper."""

    def test_mail_context_returns_mail_instructions(self):
        """Test that mail context returns email whitelist instructions."""
        instructions = _get_whitelist_instructions("mail")

        assert len(instructions) > 0
        # Check for key mail-specific content
        instructions_text = "\n".join(instructions)
        assert "msgraph_mail_whitelist" in instructions_text
        assert "Tip:" in instructions_text
        assert "whitelist" in instructions_text.lower()

    def test_mail_instructions_contain_example_command(self):
        """Test that mail instructions include the /set command example."""
        instructions = _get_whitelist_instructions("mail")
        instructions_text = "\n".join(instructions)

        assert "/set msgraph_mail_whitelist" in instructions_text
        assert "@walmart.com" in instructions_text  # Example email domain

    def test_teams_context_returns_teams_instructions(self):
        """Test that teams context returns Teams whitelist instructions."""
        instructions = _get_whitelist_instructions("teams")

        assert len(instructions) > 0
        # Check for key teams-specific content
        instructions_text = "\n".join(instructions)
        assert "msgraph_teams_whitelist" in instructions_text
        assert "Tip:" in instructions_text

    def test_teams_instructions_contain_all_formats(self):
        """Test that teams instructions document all supported formats."""
        instructions = _get_whitelist_instructions("teams")
        instructions_text = "\n".join(instructions)

        # Should document email format for DMs
        assert "user@walmart.com" in instructions_text or "email" in instructions_text.lower()
        # Should document chat: prefix for named group chats
        assert "chat:" in instructions_text
        # Should document channel: prefix for channels
        assert "channel:" in instructions_text

    def test_empty_context_returns_empty_list(self):
        """Test that empty context returns no instructions."""
        instructions = _get_whitelist_instructions("")

        assert instructions == []

    def test_unknown_context_returns_empty_list(self):
        """Test that unknown context returns no instructions."""
        instructions = _get_whitelist_instructions("unknown")
        assert instructions == []

        instructions = _get_whitelist_instructions("calendar")
        assert instructions == []

        instructions = _get_whitelist_instructions("onedrive")
        assert instructions == []


class TestApprovalStateContext:
    """Test suite for ApprovalState context field."""

    def test_default_context_is_empty(self):
        """Test that ApprovalState defaults to empty context."""
        state = ApprovalState(action="Test", details={})

        assert state.context == ""

    def test_context_can_be_set_to_mail(self):
        """Test that context can be explicitly set to mail."""
        state = ApprovalState(action="Send Email", details={"To": "test@test.com"}, context="mail")

        assert state.context == "mail"

    def test_context_can_be_set_to_teams(self):
        """Test that context can be explicitly set to teams."""
        state = ApprovalState(
            action="Teams Message", details={"Chat": "test"}, context="teams"
        )

        assert state.context == "teams"


class TestFallbackPromptWhitelistTip:
    """Test suite for _fallback_prompt whitelist tip display."""

    @patch("code_puppy.messaging.message_queue.emit_prompt")
    def test_mail_context_shows_mail_whitelist_tip(self, mock_emit_prompt):
        """Test that fallback prompt shows mail whitelist tip for mail context."""
        mock_emit_prompt.return_value = "n"  # User rejects

        _fallback_prompt("Send Email", {"To": "test@test.com"}, context="mail")

        # Check that emit_prompt was called with mail whitelist tip
        call_args = mock_emit_prompt.call_args[0][0]
        assert "msgraph_mail_whitelist" in call_args

    @patch("code_puppy.messaging.message_queue.emit_prompt")
    def test_teams_context_shows_teams_whitelist_tip(self, mock_emit_prompt):
        """Test that fallback prompt shows teams whitelist tip for teams context."""
        mock_emit_prompt.return_value = "n"  # User rejects

        _fallback_prompt("Teams Message", {"Chat": "test-chat"}, context="teams")

        # Check that emit_prompt was called with teams whitelist tip
        call_args = mock_emit_prompt.call_args[0][0]
        assert "msgraph_teams_whitelist" in call_args

    @patch("code_puppy.messaging.message_queue.emit_prompt")
    def test_empty_context_shows_no_whitelist_tip(self, mock_emit_prompt):
        """Test that fallback prompt shows no whitelist tip for empty context."""
        mock_emit_prompt.return_value = "n"  # User rejects

        _fallback_prompt("Some Action", {"Detail": "value"}, context="")

        # Check that emit_prompt was called without whitelist tips
        call_args = mock_emit_prompt.call_args[0][0]
        assert "msgraph_mail_whitelist" not in call_args
        assert "msgraph_teams_whitelist" not in call_args

    @patch("code_puppy.messaging.message_queue.emit_prompt")
    def test_fallback_prompt_returns_true_on_yes(self, mock_emit_prompt):
        """Test that fallback prompt returns True when user approves."""
        mock_emit_prompt.return_value = "y"

        result = _fallback_prompt("Test", {}, context="mail")

        assert result is True

    @patch("code_puppy.messaging.message_queue.emit_prompt")
    def test_fallback_prompt_returns_false_on_no(self, mock_emit_prompt):
        """Test that fallback prompt returns False when user rejects."""
        mock_emit_prompt.return_value = "n"

        result = _fallback_prompt("Test", {}, context="mail")

        assert result is False


class TestRequestApprovalContextPassing:
    """Test suite for request_approval context parameter handling."""

    @patch("code_puppy.tools.msgraph.approval_tui.is_interactive")
    def test_request_approval_non_interactive_returns_false(self, mock_interactive):
        """Test that request_approval returns False in non-interactive mode."""
        mock_interactive.return_value = False

        result = request_approval("Test", {}, context="mail")

        assert result is False

    @patch("code_puppy.tools.msgraph.approval_tui.is_interactive")
    @patch("code_puppy.tools.msgraph.approval_tui._fallback_prompt")
    @patch("code_puppy.tools.msgraph.approval_tui.asyncio.get_running_loop")
    def test_request_approval_passes_context_to_fallback(
        self, mock_loop, mock_fallback, mock_interactive
    ):
        """Test that request_approval passes context to fallback prompt."""
        mock_interactive.return_value = True
        mock_loop.return_value = MagicMock()  # Simulate async context
        mock_fallback.return_value = True

        request_approval("Send Email", {"To": "test@test.com"}, context="mail")

        # Verify fallback was called with context
        mock_fallback.assert_called_once()
        call_kwargs = mock_fallback.call_args
        # Check positional or keyword args for context
        assert call_kwargs[1].get("context") == "mail" or "mail" in call_kwargs[0]

    def test_request_approval_default_context_is_empty(self):
        """Test that request_approval defaults to empty context."""
        # We can't easily test this without mocking everything,
        # but we can verify the function signature
        import inspect
        sig = inspect.signature(request_approval)
        context_param = sig.parameters.get("context")

        assert context_param is not None
        assert context_param.default == ""
