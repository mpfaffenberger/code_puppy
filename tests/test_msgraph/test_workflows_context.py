"""Tests for MS Graph Context Workflows."""

import pytest
from unittest.mock import MagicMock, patch

from code_puppy.tools.msgraph.workflows_context import (
    msgraph_gather_context,
    msgraph_prioritized_inbox,
    msgraph_draft_response,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestGatherContext:
    """Tests for msgraph_gather_context."""

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_gather_all_sources_success(self, mock_client, mock_ctx):
        """Test gathering context from all sources."""
        mock_client.return_value.get.side_effect = [
            # Emails
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Platform Migration Update",
                        "from": {"emailAddress": {"name": "Aaron", "address": "a@test.com"}},
                        "receivedDateTime": "2024-12-17T10:00:00Z",
                        "bodyPreview": "Here's the update...",
                        "importance": "high",
                    }
                ]
            },
            # Files
            {
                "value": [
                    {
                        "id": "file-1",
                        "name": "Migration Plan.docx",
                        "webUrl": "https://sharepoint.com/file-1",
                        "lastModifiedDateTime": "2024-12-16T10:00:00Z",
                        "createdBy": {"user": {"displayName": "Jane"}},
                        "size": 12345,
                    }
                ]
            },
            # Events
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Platform Migration Sync",
                        "start": {"dateTime": "2024-12-18T14:00:00Z"},
                        "end": {"dateTime": "2024-12-18T15:00:00Z"},
                        "organizer": {"emailAddress": {"name": "Brandon"}},
                        "location": {"displayName": "Teams"},
                        "attendees": [{}, {}],
                    }
                ]
            },
        ]

        result = msgraph_gather_context(
            mock_ctx,
            topic="Platform Migration",
            include_teams=False,
        )

        assert result["success"] is True
        assert result["total_items"] == 3
        assert "emails" in result["sources_succeeded"]
        assert "files" in result["sources_succeeded"]
        assert "events" in result["sources_succeeded"]
        assert len(result["sources_failed"]) == 0

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_partial_success(self, mock_client, mock_ctx):
        """Test handling partial failures gracefully."""
        mock_client.return_value.get.side_effect = [
            # Emails succeed
            {"value": [{"id": "msg-1", "subject": "Test", "from": {"emailAddress": {}}}]},
            # Files fail
            Exception("File search failed"),
            # Events succeed
            {"value": []},
        ]

        result = msgraph_gather_context(
            mock_ctx,
            topic="Test",
            include_teams=False,
        )

        assert result["success"] is True  # Partial success is still success
        assert "emails" in result["sources_succeeded"]
        assert "events" in result["sources_succeeded"]
        assert "files" in result["sources_failed"]

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_all_fail(self, mock_client, mock_ctx):
        """Test when all sources fail."""
        mock_client.return_value.get.side_effect = Exception("API error")

        result = msgraph_gather_context(
            mock_ctx,
            topic="Test",
            include_teams=False,
        )

        assert result["success"] is False
        assert len(result["sources_succeeded"]) == 0
        assert len(result["sources_failed"]) == 3


class TestPrioritizedInbox:
    """Tests for msgraph_prioritized_inbox."""

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_prioritization(self, mock_client, mock_ctx):
        """Test email prioritization by sender importance."""
        mock_client.return_value.get.side_effect = [
            # People response (relevance-ranked)
            {
                "value": [
                    {
                        "displayName": "Boss",
                        "emailAddresses": [{"address": "boss@test.com"}],
                    },
                    {
                        "displayName": "Colleague",
                        "emailAddresses": [{"address": "colleague@test.com"}],
                    },
                ]
            },
            # Unread emails
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Low priority from unknown",
                        "from": {"emailAddress": {"name": "Unknown", "address": "unknown@test.com"}},
                        "receivedDateTime": "2024-12-17T10:00:00Z",
                        "importance": "normal",
                        "bodyPreview": "...",
                    },
                    {
                        "id": "msg-2",
                        "subject": "Critical from boss",
                        "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                        "receivedDateTime": "2024-12-17T09:00:00Z",
                        "importance": "high",
                        "bodyPreview": "...",
                    },
                ]
            },
        ]

        result = msgraph_prioritized_inbox(mock_ctx, top=20)

        assert result["success"] is True
        assert result["total"] == 2
        # Boss email should be first (ranked #1 + high importance)
        assert result["emails"][0]["from"] == "Boss"
        assert result["emails"][0]["priority_tier"] == "critical"
        # Unknown should be last
        assert result["emails"][1]["from"] == "Unknown"
        assert result["emails"][1]["priority_tier"] == "low"

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_prioritized_inbox(mock_ctx)

        assert result["success"] is False


class TestDraftResponse:
    """Tests for msgraph_draft_response."""

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_draft_accept(self, mock_client, mock_ctx):
        """Test preparing context for acceptance response."""
        mock_client.return_value.get.side_effect = [
            # Original email
            {
                "id": "msg-1",
                "subject": "Meeting Invitation",
                "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                "toRecipients": [],
                "ccRecipients": [],
                "body": {"content": "Please join our meeting tomorrow."},
                "receivedDateTime": "2024-12-17T10:00:00Z",
                "importance": "high",
                "conversationId": "conv-1",
            },
            # Thread context
            {"value": []},
        ]

        result = msgraph_draft_response(
            mock_ctx,
            email_id="msg-1",
            intent="accept the meeting",
            tone="professional",
        )

        assert result["success"] is True
        assert result["original_email"]["subject"] == "Meeting Invitation"
        assert result["response_guidance"]["intent"] == "accept the meeting"
        assert "confirm" in result["response_guidance"]["suggested_structure"][1].lower()

    @patch("code_puppy.tools.msgraph.workflows_context.get_msgraph_client")
    def test_draft_decline(self, mock_client, mock_ctx):
        """Test preparing context for decline response."""
        mock_client.return_value.get.side_effect = [
            {
                "id": "msg-1",
                "subject": "Invitation",
                "from": {"emailAddress": {"name": "Someone", "address": "s@t.com"}},
                "body": {"content": "Please attend."},
                "receivedDateTime": "2024-12-17T10:00:00Z",
                "conversationId": "conv-1",
            },
            {"value": []},
        ]

        result = msgraph_draft_response(
            mock_ctx,
            email_id="msg-1",
            intent="decline politely",
            tone="friendly",
        )

        assert result["success"] is True
        assert "decline" in result["response_guidance"]["suggested_structure"][1].lower()
