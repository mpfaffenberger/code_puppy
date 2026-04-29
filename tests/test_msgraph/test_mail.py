"""Unit tests for MS Graph mail module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.mail import (
    msgraph_list_messages,
    msgraph_get_message,
    msgraph_send_mail,
    msgraph_reply_to_message,
    msgraph_search_mail,
    msgraph_list_mail_folders,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphNotFoundError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture(autouse=True)
def auto_approve_msgraph_actions():
    """Auto-approve all msgraph approval requests in tests."""
    with patch(
        "code_puppy.tools.msgraph.mail.require_user_approval"
    ):
        yield


@pytest.fixture
def mock_message_preview_data():
    """Create mock message preview data from MS Graph API."""
    return {
        "value": [
            {
                "id": "msg-123-abc",
                "subject": "Weekly Update",
                "from": {
                    "emailAddress": {
                        "name": "John Doe",
                        "address": "john.doe@walmart.com",
                    }
                },
                "receivedDateTime": "2025-01-15T10:30:00Z",
                "bodyPreview": "Here is the weekly update for the team...",
                "isRead": True,
                "hasAttachments": False,
                "importance": "normal",
            },
            {
                "id": "msg-456-def",
                "subject": "URGENT: Review Needed",
                "from": {
                    "emailAddress": {
                        "name": "Jane Smith",
                        "address": "jane.smith@walmart.com",
                    }
                },
                "receivedDateTime": "2025-01-15T09:15:00Z",
                "bodyPreview": "Please review the attached document ASAP...",
                "isRead": False,
                "hasAttachments": True,
                "importance": "high",
            },
        ]
    }


@pytest.fixture
def mock_message_full_data():
    """Create mock full message data from MS Graph API."""
    return {
        "id": "msg-123-abc",
        "subject": "Weekly Update",
        "from": {
            "emailAddress": {
                "name": "John Doe",
                "address": "john.doe@walmart.com",
            }
        },
        "toRecipients": [
            {
                "emailAddress": {
                    "name": "Alice Johnson",
                    "address": "alice.johnson@walmart.com",
                }
            },
            {
                "emailAddress": {
                    "name": "Bob Williams",
                    "address": "bob.williams@walmart.com",
                }
            },
        ],
        "ccRecipients": [
            {
                "emailAddress": {
                    "name": "Manager",
                    "address": "manager@walmart.com",
                }
            }
        ],
        "bccRecipients": [],
        "body": {
            "contentType": "html",
            "content": "<html><body><p>Here is the weekly update.</p></body></html>",
        },
        "receivedDateTime": "2025-01-15T10:30:00Z",
        "sentDateTime": "2025-01-15T10:29:45Z",
        "isRead": True,
        "hasAttachments": False,
        "importance": "normal",
        "conversationId": "conv-789-ghi",
    }


@pytest.fixture
def mock_folders_data():
    """Create mock mail folders data from MS Graph API."""
    return {
        "value": [
            {
                "id": "folder-inbox",
                "displayName": "Inbox",
                "unreadItemCount": 5,
                "totalItemCount": 150,
                "parentFolderId": None,
            },
            {
                "id": "folder-sent",
                "displayName": "Sent Items",
                "unreadItemCount": 0,
                "totalItemCount": 200,
                "parentFolderId": None,
            },
            {
                "id": "folder-drafts",
                "displayName": "Drafts",
                "unreadItemCount": 0,
                "totalItemCount": 3,
                "parentFolderId": None,
            },
        ]
    }


class TestMSGraphMailTools:
    """Test suite for MS Graph mail tools."""

    def test_msgraph_list_messages(self, mock_context, mock_message_preview_data):
        """Test listing messages from inbox."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_message_preview_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context)

            assert result["success"] is True
            assert "messages" in result
            assert result["total_count"] == 2
            assert result["folder"] == "inbox"
            assert len(result["messages"]) == 2

            # Check first message
            msg1 = result["messages"][0]
            assert msg1["id"] == "msg-123-abc"
            assert msg1["subject"] == "Weekly Update"
            assert msg1["from"]["name"] == "John Doe"
            assert msg1["from"]["email"] == "john.doe@walmart.com"
            assert msg1["is_read"] is True
            assert msg1["has_attachments"] is False

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/me/mailFolders/inbox/messages" in call_args[0][0]

    def test_msgraph_list_messages_with_folder(
        self, mock_context, mock_message_preview_data
    ):
        """Test listing messages from a specific folder."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_message_preview_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context, folder="sentitems")

            assert result["success"] is True
            assert result["folder"] == "sentitems"

            # Verify correct folder was used in API call
            call_args = mock_client.get.call_args
            assert "/me/mailFolders/sentitems/messages" in call_args[0][0]

    def test_msgraph_list_messages_unread_filter(
        self, mock_context, mock_message_preview_data
    ):
        """Test filtering unread messages only."""
        # Only unread message
        unread_only = {
            "value": [mock_message_preview_data["value"][1]]  # The unread one
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = unread_only
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context, filter_unread=True)

            assert result["success"] is True
            assert result["total_count"] == 1
            assert result["messages"][0]["is_read"] is False

            # Verify filter was applied in API call
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$filter"] == "isRead eq false"

    def test_msgraph_list_messages_with_pagination(self, mock_context):
        """Test listing messages with pagination parameters."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context, limit=25, skip=50)

            assert result["success"] is True

            # Verify pagination parameters
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 25
            assert call_args[1]["params"]["$skip"] == 50

    def test_msgraph_list_messages_auth_error(self, mock_context):
        """Test handling of authentication error."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired or invalid")
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]

    def test_msgraph_get_message(self, mock_context, mock_message_full_data):
        """Test getting a full message by ID."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_message_full_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "msg-123-abc")

            assert result["success"] is True
            assert "message" in result

            msg = result["message"]
            assert msg["id"] == "msg-123-abc"
            assert msg["subject"] == "Weekly Update"
            assert msg["from"]["name"] == "John Doe"
            assert msg["from"]["email"] == "john.doe@walmart.com"

            # Check recipients
            assert len(msg["to"]) == 2
            assert msg["to"][0]["email"] == "alice.johnson@walmart.com"
            assert msg["to"][1]["email"] == "bob.williams@walmart.com"
            assert len(msg["cc"]) == 1
            assert msg["cc"][0]["email"] == "manager@walmart.com"
            assert len(msg["bcc"]) == 0

            # Check body (HTML stripped)
            assert "Here is the weekly update" in msg["body"]
            assert msg["body_type"] == "html"

            # Check other fields
            assert msg["conversation_id"] == "conv-789-ghi"
            assert msg["is_read"] is True

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/me/messages/msg-123-abc" in call_args[0][0]

    def test_msgraph_get_message_not_found(self, mock_context):
        """Test handling of message not found error."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Message not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "nonexistent-msg-id")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "not_found"
            assert "not found" in result["error"].lower()

    def test_msgraph_send_mail(self, mock_context):
        """Test sending a simple email."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = None  # sendMail returns 202 No Content
            mock_get_client.return_value = mock_client

            result = msgraph_send_mail(
                mock_context,
                to=["recipient@walmart.com"],
                subject="Test Subject",
                body="This is a test email.",
            )

            assert result["success"] is True
            assert result["message"] == "Email sent successfully"
            assert result["to"] == ["recipient@walmart.com"]
            assert result["subject"] == "Test Subject"

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/sendMail"

            payload = call_args[1]["json"]
            assert payload["message"]["subject"] == "Test Subject"
            assert payload["message"]["body"]["content"] == "This is a test email."
            assert payload["message"]["body"]["contentType"] == "Text"
            assert len(payload["message"]["toRecipients"]) == 1
            assert (
                payload["message"]["toRecipients"][0]["emailAddress"]["address"]
                == "recipient@walmart.com"
            )

    def test_msgraph_send_mail_with_cc_bcc(self, mock_context):
        """Test sending email with CC and BCC recipients."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_send_mail(
                mock_context,
                to=["primary@walmart.com"],
                subject="Meeting Notes",
                body="<p>Here are the notes.</p>",
                cc=["cc1@walmart.com", "cc2@walmart.com"],
                bcc=["bcc@walmart.com"],
                is_html=True,
            )

            assert result["success"] is True

            # Verify payload structure
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            # Check content type for HTML
            assert payload["message"]["body"]["contentType"] == "HTML"

            # Check CC recipients
            assert "ccRecipients" in payload["message"]
            assert len(payload["message"]["ccRecipients"]) == 2
            cc_emails = [
                r["emailAddress"]["address"] for r in payload["message"]["ccRecipients"]
            ]
            assert "cc1@walmart.com" in cc_emails
            assert "cc2@walmart.com" in cc_emails

            # Check BCC recipients
            assert "bccRecipients" in payload["message"]
            assert len(payload["message"]["bccRecipients"]) == 1
            assert (
                payload["message"]["bccRecipients"][0]["emailAddress"]["address"]
                == "bcc@walmart.com"
            )

    def test_msgraph_send_mail_multiple_recipients(self, mock_context):
        """Test sending email to multiple TO recipients."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = None
            mock_get_client.return_value = mock_client

            recipients = [
                "user1@walmart.com",
                "user2@walmart.com",
                "user3@walmart.com",
            ]

            result = msgraph_send_mail(
                mock_context,
                to=recipients,
                subject="Team Update",
                body="Update for everyone.",
            )

            assert result["success"] is True
            assert result["to"] == recipients

            # Verify all recipients in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert len(payload["message"]["toRecipients"]) == 3

    def test_msgraph_send_mail_auth_error(self, mock_context):
        """Test handling authentication error when sending mail."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_send_mail(
                mock_context,
                to=["recipient@walmart.com"],
                subject="Test",
                body="Test body",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_reply_to_message(self, mock_context):
        """Test replying to a message."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Get original message for recipient extraction
            mock_client.get.return_value = {
                "from": {"emailAddress": {"address": "sender@walmart.com"}},
                "toRecipients": [],
                "ccRecipients": [],
            }
            # First post (createReply) returns draft with id, second post (send) returns None
            mock_client.post.side_effect = [{"id": "draft-123"}, None]
            mock_client.patch.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_reply_to_message(
                mock_context,
                message_id="msg-123-abc",
                body="Thanks for the update!",
            )

            assert result["success"] is True
            assert "Reply sent successfully" in result["message"]
            assert result["message_id"] == "msg-123-abc"
            assert result["reply_all"] is False

            # Verify createReply was called first
            first_call = mock_client.post.call_args_list[0]
            assert first_call[0][0] == "/me/messages/msg-123-abc/createReply"
            # Verify send was called with the draft id
            second_call = mock_client.post.call_args_list[1]
            assert second_call[0][0] == "/me/messages/draft-123/send"

    def test_msgraph_reply_all(self, mock_context):
        """Test replying all to a message."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Get original message for recipient extraction
            mock_client.get.return_value = {
                "from": {"emailAddress": {"address": "sender@walmart.com"}},
                "toRecipients": [
                    {"emailAddress": {"address": "me@walmart.com"}},
                ],
                "ccRecipients": [
                    {"emailAddress": {"address": "manager@walmart.com"}},
                ],
            }
            # First post (createReplyAll) returns draft with id, second post (send) returns None
            mock_client.post.side_effect = [{"id": "draft-456"}, None]
            mock_client.patch.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_reply_to_message(
                mock_context,
                message_id="msg-456-def",
                body="Noted, thanks everyone!",
                reply_all=True,
            )

            assert result["success"] is True
            assert "Reply All sent successfully" in result["message"]
            assert result["message_id"] == "msg-456-def"
            assert result["reply_all"] is True

            # Verify createReplyAll was called
            first_call = mock_client.post.call_args_list[0]
            assert first_call[0][0] == "/me/messages/msg-456-def/createReplyAll"

    def test_msgraph_reply_to_message_not_found(self, mock_context):
        """Test replying to a non-existent message."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            # Fetching original message fails with not found
            mock_client.get.side_effect = MSGraphNotFoundError("Message not found")
            mock_get_client.return_value = mock_client

            result = msgraph_reply_to_message(
                mock_context,
                message_id="nonexistent-id",
                body="Reply text",
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_search_mail(self, mock_context, mock_message_preview_data):
        """Test searching emails."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_message_preview_data
            mock_get_client.return_value = mock_client

            result = msgraph_search_mail(mock_context, query="weekly update")

            assert result["success"] is True
            assert "messages" in result
            assert result["total_count"] == 2
            assert result["query"] == "weekly update"

            # Verify search parameter
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/messages"
            assert call_args[1]["params"]["$search"] == '"weekly update"'

    def test_msgraph_search_mail_with_limit(self, mock_context):
        """Test searching emails with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_search_mail(mock_context, query="budget", limit=25)

            assert result["success"] is True

            # Verify limit parameter
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 25

    def test_msgraph_search_mail_empty_results(self, mock_context):
        """Test search with no matching results."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_search_mail(mock_context, query="xyznonexistentquery123")

            assert result["success"] is True
            assert result["messages"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_mail_folders(self, mock_context, mock_folders_data):
        """Test listing mail folders."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_folders_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_mail_folders(mock_context)

            assert result["success"] is True
            assert "folders" in result
            assert result["total_count"] == 3
            assert len(result["folders"]) == 3

            # Check folder details
            inbox = result["folders"][0]
            assert inbox["id"] == "folder-inbox"
            assert inbox["display_name"] == "Inbox"
            assert inbox["unread_count"] == 5
            assert inbox["total_count"] == 150

            sent = result["folders"][1]
            assert sent["display_name"] == "Sent Items"
            assert sent["unread_count"] == 0

            drafts = result["folders"][2]
            assert drafts["display_name"] == "Drafts"
            assert drafts["total_count"] == 3

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/mailFolders"

    def test_msgraph_list_mail_folders_auth_error(self, mock_context):
        """Test handling of authentication error when listing folders."""
        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Session expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_mail_folders(mock_context)

            assert result["success"] is False
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]


class TestMSGraphMailFormatting:
    """Test suite for mail data formatting."""

    def test_message_preview_formatting(self, mock_context):
        """Verify message preview fields are properly mapped."""
        raw_message = {
            "value": [
                {
                    "id": "test-msg-id",
                    "subject": "Test Subject",
                    "from": {
                        "emailAddress": {
                            "name": "Sender Name",
                            "address": "sender@walmart.com",
                        }
                    },
                    "receivedDateTime": "2025-01-15T08:00:00Z",
                    "bodyPreview": "A" * 250,  # Long preview
                    "isRead": False,
                    "hasAttachments": True,
                    "importance": "high",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = raw_message
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context)

            msg = result["messages"][0]
            assert msg["id"] == "test-msg-id"
            assert msg["subject"] == "Test Subject"
            assert msg["from"]["name"] == "Sender Name"
            assert msg["from"]["email"] == "sender@walmart.com"
            assert msg["received"] == "2025-01-15T08:00:00Z"
            assert len(msg["preview"]) <= 200  # Truncated
            assert msg["is_read"] is False
            assert msg["has_attachments"] is True
            assert msg["importance"] == "high"

    def test_message_with_no_subject(self, mock_context):
        """Test handling of message with missing subject."""
        raw_message = {
            "value": [
                {
                    "id": "no-subject-msg",
                    # subject is missing
                    "from": {
                        "emailAddress": {
                            "name": "Someone",
                            "address": "someone@walmart.com",
                        }
                    },
                    "receivedDateTime": "2025-01-15T08:00:00Z",
                    "bodyPreview": "Body text",
                    "isRead": True,
                    "hasAttachments": False,
                    "importance": "normal",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = raw_message
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context)

            msg = result["messages"][0]
            assert msg["subject"] == "(No Subject)"

    def test_html_body_is_stripped(self, mock_context):
        """Test that HTML tags are stripped from message body."""
        html_message = {
            "id": "html-msg",
            "subject": "HTML Email",
            "from": {
                "emailAddress": {
                    "name": "Sender",
                    "address": "sender@walmart.com",
                }
            },
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {
                "contentType": "html",
                "content": "<html><body><p>Hello&nbsp;World!</p><br/>"
                "<div>Line&amp;Two</div></body></html>",
            },
            "receivedDateTime": "2025-01-15T08:00:00Z",
            "sentDateTime": "2025-01-15T07:59:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "conversationId": "conv-123",
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = html_message
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "html-msg")

            msg = result["message"]
            # HTML tags should be stripped
            assert "<html>" not in msg["body"]
            assert "<p>" not in msg["body"]
            assert "<div>" not in msg["body"]
            # HTML entities should be decoded
            assert "Hello World!" in msg["body"]
            assert "Line&Two" in msg["body"]

    def test_plain_text_body_preserved(self, mock_context):
        """Test that plain text body is preserved."""
        text_message = {
            "id": "text-msg",
            "subject": "Plain Text Email",
            "from": {
                "emailAddress": {
                    "name": "Sender",
                    "address": "sender@walmart.com",
                }
            },
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {
                "contentType": "text",
                "content": "This is plain text.\nWith multiple lines.",
            },
            "receivedDateTime": "2025-01-15T08:00:00Z",
            "sentDateTime": "2025-01-15T07:59:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "conversationId": "conv-456",
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = text_message
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "text-msg")

            msg = result["message"]
            assert msg["body"] == "This is plain text.\nWith multiple lines."
            assert msg["body_type"] == "text"

    def test_folder_formatting(self, mock_context):
        """Verify folder fields are properly mapped."""
        raw_folders = {
            "value": [
                {
                    "id": "folder-id-123",
                    "displayName": "Custom Folder",
                    "unreadItemCount": 10,
                    "totalItemCount": 50,
                    "parentFolderId": "parent-folder-id",
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = raw_folders
            mock_get_client.return_value = mock_client

            result = msgraph_list_mail_folders(mock_context)

            folder = result["folders"][0]
            assert folder["id"] == "folder-id-123"
            assert folder["display_name"] == "Custom Folder"
            assert folder["unread_count"] == 10
            assert folder["total_count"] == 50
            assert folder["parent_folder_id"] == "parent-folder-id"


class TestMSGraphMailTruncation:
    """Test suite for MS Graph mail truncation functionality."""

    def test_msgraph_list_messages_with_item_offset(self, mock_context):
        """Test list_messages with item_offset parameter."""
        messages = {
            "value": [
                {
                    "id": f"msg-{i}",
                    "subject": f"Message {i}",
                    "from": {
                        "emailAddress": {"name": "Sender", "address": "s@test.com"}
                    },
                    "receivedDateTime": "2025-01-15T10:00:00Z",
                    "bodyPreview": "Preview text",
                    "isRead": True,
                    "hasAttachments": False,
                    "importance": "normal",
                }
                for i in range(10)
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = messages
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context, item_offset=5)

            assert result["success"] is True
            assert "truncated" in result
            assert "items_returned" in result
            # Should skip first 5 items
            assert result["messages"][0]["id"] == "msg-5"

    def test_msgraph_list_messages_truncation_response_fields(self, mock_context):
        """Test that list_messages includes truncation fields."""
        messages = {
            "value": [
                {
                    "id": f"msg-{i}",
                    "subject": f"Message {i}",
                    "from": {
                        "emailAddress": {"name": "Sender", "address": "s@test.com"}
                    },
                    "receivedDateTime": "2025-01-15T10:00:00Z",
                    "bodyPreview": "Preview text",
                    "isRead": True,
                    "hasAttachments": False,
                    "importance": "normal",
                }
                for i in range(5)
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = messages
            mock_get_client.return_value = mock_client

            result = msgraph_list_messages(mock_context)

            assert result["success"] is True
            assert "truncated" in result
            assert result["truncated"] is False
            assert "items_returned" in result
            assert result["items_returned"] == 5

    def test_msgraph_get_message_body_truncation_fields(self, mock_context):
        """Test that get_message includes body truncation fields."""
        message = {
            "id": "msg-123",
            "subject": "Test Message",
            "from": {"emailAddress": {"name": "Sender", "address": "s@test.com"}},
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {"contentType": "text", "content": "Short body"},
            "receivedDateTime": "2025-01-15T10:00:00Z",
            "sentDateTime": "2025-01-15T09:59:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "conversationId": "conv-123",
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = message
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "msg-123")

            assert result["success"] is True
            msg = result["message"]
            assert "body_truncated" in msg
            assert msg["body_truncated"] is False
            assert "body_total_chars" in msg

    def test_msgraph_get_message_large_body_truncation(self, mock_context):
        """Test that large message bodies are truncated."""
        large_body = "X" * 15000
        message = {
            "id": "msg-123",
            "subject": "Large Message",
            "from": {"emailAddress": {"name": "Sender", "address": "s@test.com"}},
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {"contentType": "text", "content": large_body},
            "receivedDateTime": "2025-01-15T10:00:00Z",
            "sentDateTime": "2025-01-15T09:59:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "conversationId": "conv-123",
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = message
            mock_get_client.return_value = mock_client

            result = msgraph_get_message(mock_context, "msg-123")

            assert result["success"] is True
            msg = result["message"]
            assert msg["body_truncated"] is True
            assert len(msg["body"]) == 10000
            assert msg["body_total_chars"] == 15000
            assert msg["body_next_offset"] == 10000

    def test_msgraph_get_message_with_char_offset(self, mock_context):
        """Test get_message with char_offset for body pagination."""
        large_body = "A" * 5000 + "B" * 10000  # 15000 total
        message = {
            "id": "msg-123",
            "subject": "Large Message",
            "from": {"emailAddress": {"name": "Sender", "address": "s@test.com"}},
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {"contentType": "text", "content": large_body},
            "receivedDateTime": "2025-01-15T10:00:00Z",
            "sentDateTime": "2025-01-15T09:59:00Z",
            "isRead": True,
            "hasAttachments": False,
            "importance": "normal",
            "conversationId": "conv-123",
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = message
            mock_get_client.return_value = mock_client

            # Get second page starting at offset 10000
            result = msgraph_get_message(mock_context, "msg-123", char_offset=10000)

            assert result["success"] is True
            msg = result["message"]
            assert msg["body_char_offset"] == 10000
            assert len(msg["body"]) == 5000  # Remaining after offset
            assert msg["body_truncated"] is False

    def test_msgraph_search_mail_with_item_offset(self, mock_context):
        """Test search_mail with item_offset parameter."""
        messages = {
            "value": [
                {
                    "id": f"msg-{i}",
                    "subject": f"Search Result {i}",
                    "from": {
                        "emailAddress": {"name": "Sender", "address": "s@test.com"}
                    },
                    "receivedDateTime": "2025-01-15T10:00:00Z",
                    "bodyPreview": "Preview text",
                    "isRead": True,
                    "hasAttachments": False,
                    "importance": "normal",
                }
                for i in range(8)
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.mail.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = messages
            mock_get_client.return_value = mock_client

            result = msgraph_search_mail(mock_context, query="test", item_offset=3)

            assert result["success"] is True
            assert "truncated" in result
            assert "items_returned" in result
            assert result["messages"][0]["id"] == "msg-3"
