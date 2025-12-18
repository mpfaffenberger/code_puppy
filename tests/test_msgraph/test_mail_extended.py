"""Tests for extended Mail tools."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.mail_extended import (
    msgraph_move_message,
    msgraph_archive_message,
    msgraph_mark_as_read,
    msgraph_mark_as_unread,
    msgraph_forward_message,
    msgraph_delete_message,
    msgraph_list_attachments,
    msgraph_get_attachment,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestMSGraphMailExtended:
    """Tests for extended mail operations."""

    def test_msgraph_move_message(self, mock_context):
        """Test moving a message to a folder."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "msg-001"}
            mock_get_client.return_value = mock_client

            result = msgraph_move_message(mock_context, "msg-001", "archive")

            assert result["success"] is True
            assert result["new_folder"] == "archive"

    def test_msgraph_archive_message(self, mock_context):
        """Test archiving a message."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {"id": "msg-001"}
            mock_get_client.return_value = mock_client

            result = msgraph_archive_message(mock_context, "msg-001")

            assert result["success"] is True
            assert result["action"] == "archived"

    def test_msgraph_mark_as_read(self, mock_context):
        """Test marking a message as read."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_mark_as_read(mock_context, "msg-001")

            assert result["success"] is True
            assert result["is_read"] is True

    def test_msgraph_mark_as_unread(self, mock_context):
        """Test marking a message as unread."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_mark_as_unread(mock_context, "msg-001")

            assert result["success"] is True
            assert result["is_read"] is False

    def test_msgraph_forward_message(self, mock_context):
        """Test forwarding a message."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_forward_message(
                mock_context,
                "msg-001",
                ["person@example.com"],
                "FYI",
            )

            assert result["success"] is True
            assert "person@example.com" in result["forwarded_to"]

    def test_msgraph_delete_message(self, mock_context):
        """Test deleting a message."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.return_value = None
            mock_get_client.return_value = mock_client

            result = msgraph_delete_message(mock_context, "msg-001")

            assert result["success"] is True
            assert result["action"] == "deleted"


class TestMSGraphAttachments:
    """Tests for attachment operations."""

    def test_msgraph_list_attachments(self, mock_context):
        """Test listing attachments."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "value": [
                    {
                        "id": "att-001",
                        "name": "document.pdf",
                        "contentType": "application/pdf",
                        "size": 12345,
                        "isInline": False,
                    }
                ]
            }
            mock_get_client.return_value = mock_client

            result = msgraph_list_attachments(mock_context, "msg-001")

            assert result["success"] is True
            assert result["total_count"] == 1
            assert result["attachments"][0]["name"] == "document.pdf"

    def test_msgraph_get_attachment(self, mock_context):
        """Test getting an attachment."""
        with patch(
            "code_puppy.tools.msgraph.mail_extended.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "id": "att-001",
                "name": "document.pdf",
                "contentType": "application/pdf",
                "size": 12345,
                "contentBytes": "base64encodedcontent",
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_attachment(mock_context, "msg-001", "att-001")

            assert result["success"] is True
            assert result["attachment"]["name"] == "document.pdf"
            assert result["attachment"]["content_bytes"] is not None
