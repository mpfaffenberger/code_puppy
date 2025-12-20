"""Tests for MS Graph Search API tools."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.search import (
    msgraph_unified_search,
    msgraph_search_emails_advanced,
    msgraph_search_files_advanced,
    msgraph_search_teams_messages,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


@pytest.fixture
def sample_search_response():
    return {
        "value": [
            {
                "hitsContainers": [
                    {
                        "hits": [
                            {
                                "rank": 1,
                                "summary": "This is a preview of the result",
                                "resource": {
                                    "@odata.type": "#microsoft.graph.message",
                                    "id": "msg-1",
                                    "subject": "Q4 Planning Discussion",
                                    "from": {
                                        "emailAddress": {
                                            "name": "Aaron Berg",
                                            "address": "aaron@walmart.com",
                                        }
                                    },
                                    "receivedDateTime": "2024-12-17T10:00:00Z",
                                    "webLink": "https://outlook.office.com/mail/id/msg-1",
                                },
                            },
                            {
                                "rank": 2,
                                "summary": "File preview",
                                "resource": {
                                    "@odata.type": "#microsoft.graph.driveItem",
                                    "id": "file-1",
                                    "name": "Q4_Planning.pptx",
                                    "webUrl": "https://sharepoint.com/sites/team/Q4_Planning.pptx",
                                    "lastModifiedDateTime": "2024-12-16T14:00:00Z",
                                    "createdBy": {"user": {"displayName": "Jane Doe"}},
                                },
                            },
                        ]
                    }
                ]
            }
        ]
    }


class TestUnifiedSearch:
    """Tests for msgraph_unified_search."""

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_unified_search_success(self, mock_client, mock_ctx, sample_search_response):
        """Test unified search across types."""
        mock_client.return_value.post.return_value = sample_search_response

        result = msgraph_unified_search(mock_ctx, query="Q4 Planning")

        assert result["success"] is True
        assert result["total_count"] == 2
        assert "message" in result["results_by_type"]
        assert "driveItem" in result["results_by_type"]
        assert result["results_by_type"]["message"][0]["subject"] == "Q4 Planning Discussion"

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_unified_search_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_unified_search(mock_ctx, query="test")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_unified_search_custom_types(self, mock_client, mock_ctx):
        """Test searching specific entity types."""
        mock_client.return_value.post.return_value = {"value": []}

        result = msgraph_unified_search(
            mock_ctx,
            query="test",
            entity_types=["message", "chatMessage"],
        )

        assert result["success"] is True
        call_args = mock_client.return_value.post.call_args
        request_body = call_args[1]["json"]
        assert request_body["requests"][0]["entityTypes"] == ["message", "chatMessage"]


class TestSearchEmailsAdvanced:
    """Tests for msgraph_search_emails_advanced."""

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_search_with_filters(self, mock_client, mock_ctx):
        """Test advanced email search with filters."""
        mock_client.return_value.post.return_value = {
            "value": [
                {
                    "hitsContainers": [
                        {
                            "hits": [
                                {
                                    "summary": "Email preview",
                                    "resource": {
                                        "id": "msg-2",
                                        "subject": "Budget Review",
                                        "from": {
                                            "emailAddress": {
                                                "name": "CFO",
                                                "address": "cfo@walmart.com",
                                            }
                                        },
                                        "receivedDateTime": "2024-12-17T10:00:00Z",
                                        "hasAttachments": True,
                                        "isRead": False,
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        result = msgraph_search_emails_advanced(
            mock_ctx,
            query="budget",
            from_address="cfo@walmart.com",
            has_attachment=True,
            is_unread=True,
        )

        assert result["success"] is True
        assert result["count"] == 1
        # Verify KQL query was built
        assert 'from:"cfo@walmart.com"' in result["query"]
        assert "hasAttachment:true" in result["query"]


class TestSearchFilesAdvanced:
    """Tests for msgraph_search_files_advanced."""

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_search_files(self, mock_client, mock_ctx):
        """Test advanced file search."""
        mock_client.return_value.post.return_value = {
            "value": [
                {
                    "hitsContainers": [
                        {
                            "hits": [
                                {
                                    "summary": "File content preview",
                                    "resource": {
                                        "id": "file-2",
                                        "name": "Report.docx",
                                        "webUrl": "https://sharepoint.com/Report.docx",
                                        "lastModifiedDateTime": "2024-12-17T10:00:00Z",
                                        "size": 12345,
                                        "createdBy": {"user": {"displayName": "Author"}},
                                        "lastModifiedBy": {"user": {"displayName": "Editor"}},
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        result = msgraph_search_files_advanced(
            mock_ctx,
            query="report",
            file_type="docx",
        )

        assert result["success"] is True
        assert result["count"] == 1
        assert 'fileType:"docx"' in result["query"]


class TestSearchTeamsMessages:
    """Tests for msgraph_search_teams_messages."""

    @patch("code_puppy.tools.msgraph.search.get_msgraph_client")
    def test_search_teams(self, mock_client, mock_ctx):
        """Test searching Teams messages."""
        mock_client.return_value.post.return_value = {
            "value": [
                {
                    "hitsContainers": [
                        {
                            "hits": [
                                {
                                    "summary": "Teams message preview",
                                    "resource": {
                                        "id": "chat-msg-1",
                                        "body": {"content": "Hey, can you review this?"},
                                        "from": {"user": {"displayName": "Colleague"}},
                                        "createdDateTime": "2024-12-17T10:00:00Z",
                                        "chatId": "chat-123",
                                    },
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        result = msgraph_search_teams_messages(mock_ctx, query="review")

        assert result["success"] is True
        assert result["count"] == 1
        assert result["messages"][0]["from"] == "Colleague"
