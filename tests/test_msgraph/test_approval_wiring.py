"""Tests that verify approval wiring is correct for msgraph send functions.

These tests ensure that send functions pass the correct arguments to
require_user_approval(), which is critical for whitelist skip logic.
"""

import pytest
from unittest.mock import Mock, patch, call


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestMailApprovalWiring:
    """Test that mail functions wire approval correctly."""

    def test_send_mail_passes_all_recipients_to_approval(self, mock_context):
        """msgraph_send_mail should pass combined to+cc+bcc to require_user_approval."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.mail.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            mock_client.post.return_value = None
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.mail import msgraph_send_mail

            msgraph_send_mail(
                mock_context,
                to=["primary@walmart.com"],
                subject="Test",
                body="Body",
                cc=["cc@walmart.com"],
                bcc=["bcc@walmart.com"],
            )

            # Verify approval was called with all recipients
            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            assert "primary@walmart.com" in recipients
            assert "cc@walmart.com" in recipients
            assert "bcc@walmart.com" in recipients
            assert call_kwargs.kwargs.get("context") == "mail" or call_kwargs[1].get(
                "context"
            ) == "mail"

    def test_reply_passes_original_sender_to_approval(self, mock_context):
        """msgraph_reply_to_message should pass original sender as recipient."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.mail.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            # Original message response
            mock_client.get.return_value = {
                "from": {"emailAddress": {"address": "sender@walmart.com"}},
                "toRecipients": [],
                "ccRecipients": [],
            }
            # Draft creation response
            mock_client.post.side_effect = [
                {"id": "draft-123"},  # createReply
                None,  # send
            ]
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.mail import msgraph_reply_to_message

            msgraph_reply_to_message(
                mock_context,
                message_id="msg-123",
                body="Thanks!",
                reply_all=False,
            )

            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            assert "sender@walmart.com" in recipients
            assert call_kwargs.kwargs.get("context") == "mail" or call_kwargs[1].get(
                "context"
            ) == "mail"

    def test_reply_all_passes_all_recipients_to_approval(self, mock_context):
        """msgraph_reply_to_message with reply_all should pass all recipients."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.mail.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            # Original message response
            mock_client.get.return_value = {
                "from": {"emailAddress": {"address": "sender@walmart.com"}},
                "toRecipients": [
                    {"emailAddress": {"address": "me@walmart.com"}},
                    {"emailAddress": {"address": "colleague@walmart.com"}},
                ],
                "ccRecipients": [
                    {"emailAddress": {"address": "manager@walmart.com"}},
                ],
            }
            mock_client.post.side_effect = [{"id": "draft-123"}, None]
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.mail import msgraph_reply_to_message

            msgraph_reply_to_message(
                mock_context,
                message_id="msg-123",
                body="Thanks all!",
                reply_all=True,
            )

            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            # Should include sender + all To + all CC
            assert "sender@walmart.com" in recipients
            assert "me@walmart.com" in recipients
            assert "colleague@walmart.com" in recipients
            assert "manager@walmart.com" in recipients


class TestTeamsApprovalWiring:
    """Test that Teams functions wire approval correctly."""

    def test_send_channel_message_passes_channel_id_to_approval(self, mock_context):
        """msgraph_send_channel_message should pass channel_id as recipient."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.teams.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "msg-123"}
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.teams import msgraph_send_channel_message

            msgraph_send_channel_message(
                mock_context,
                team_id="team-abc",
                channel_id="channel-xyz",
                content="Hello team!",
            )

            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            assert "channel-xyz" in recipients
            assert call_kwargs.kwargs.get("context") == "teams" or call_kwargs[1].get(
                "context"
            ) == "teams"

    def test_send_chat_message_passes_chat_id_to_approval(self, mock_context):
        """msgraph_send_chat_message should pass chat_id as recipient."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.teams.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "msg-123"}
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.teams import msgraph_send_chat_message

            msgraph_send_chat_message(
                mock_context,
                chat_id="19:abc123@thread.v2",
                content="Hello!",
            )

            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            assert "19:abc123@thread.v2" in recipients
            assert call_kwargs.kwargs.get("context") == "teams" or call_kwargs[1].get(
                "context"
            ) == "teams"

    def test_send_direct_message_passes_user_email_to_approval(self, mock_context):
        """msgraph_send_direct_message should pass user_id/email as recipient."""
        with patch(
            "code_puppy.tools.msgraph.teams.get_msgraph_client"
        ) as mock_get_client, patch(
            "code_puppy.tools.msgraph.teams.require_user_approval"
        ) as mock_approval:
            mock_client = Mock()
            # Get or create chat returns chat info
            mock_client.post.side_effect = [
                {"id": "chat-123"},  # create/get chat
                {"id": "msg-456"},  # send message
            ]
            mock_get_client.return_value = mock_client

            from code_puppy.tools.msgraph.teams import msgraph_send_direct_message

            msgraph_send_direct_message(
                mock_context,
                user_email="colleague@walmart.com",
                content="Hey!",
            )

            mock_approval.assert_called_once()
            call_kwargs = mock_approval.call_args
            recipients = call_kwargs.kwargs.get("recipients") or call_kwargs[1].get(
                "recipients"
            )

            assert "colleague@walmart.com" in recipients
            assert call_kwargs.kwargs.get("context") == "teams" or call_kwargs[1].get(
                "context"
            ) == "teams"
