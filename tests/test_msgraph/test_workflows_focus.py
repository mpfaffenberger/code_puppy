"""Tests for MS Graph Focus and Productivity Workflows."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from code_puppy.tools.msgraph.workflows_focus import (
    msgraph_daily_focus,
    msgraph_smart_meeting_prep,
)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestDailyFocus:
    """Tests for msgraph_daily_focus."""

    @patch("code_puppy.tools.msgraph.workflows_focus.get_msgraph_client")
    def test_full_daily_focus(self, mock_client, mock_ctx):
        """Test complete daily focus with all sources."""
        mock_client.return_value.get.side_effect = [
            # People response
            {
                "value": [
                    {
                        "displayName": "Boss",
                        "emailAddresses": [{"address": "boss@test.com"}],
                    }
                ]
            },
            # Calendar events
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Team Standup",
                        "start": {"dateTime": "2024-12-18T09:00:00Z"},
                        "end": {"dateTime": "2024-12-18T09:30:00Z"},
                        "organizer": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                        "isOnlineMeeting": True,
                        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/meet/1"},
                        "responseStatus": {"response": "accepted"},
                        "importance": "normal",
                        "bodyPreview": "Daily sync",
                    }
                ]
            },
            # Unread emails
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Urgent: Q4 Review",
                        "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                        "receivedDateTime": "2024-12-18T08:00:00Z",
                        "importance": "high",
                        "bodyPreview": "Please review ASAP",
                    }
                ]
            },
            # Task lists
            {"value": [{"id": "list-1", "displayName": "Tasks"}]},
            # Tasks
            {"value": []},
        ]

        result = msgraph_daily_focus(mock_ctx)

        assert result["success"] is True
        assert len(result["meetings_today"]) == 1
        assert result["meetings_today"][0]["subject"] == "Team Standup"
        assert len(result["priority_emails"]) == 1
        assert result["priority_emails"][0]["from"] == "Boss"
        assert "calendar" in result["sources_status"]
        assert result["sources_status"]["calendar"] == "success"

    @patch("code_puppy.tools.msgraph.workflows_focus.get_msgraph_client")
    def test_urgent_items_detected(self, mock_client, mock_ctx):
        """Test that urgent items are flagged."""
        mock_client.return_value.get.side_effect = [
            # People - Boss is #1
            {
                "value": [
                    {
                        "displayName": "Boss",
                        "emailAddresses": [{"address": "boss@test.com"}],
                    }
                ]
            },
            # Calendar - meeting needs response
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Urgent Meeting",
                        "start": {"dateTime": "2024-12-18T10:00:00Z"},
                        "end": {"dateTime": "2024-12-18T11:00:00Z"},
                        "organizer": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                        "responseStatus": {"response": "notResponded"},
                    }
                ]
            },
            # Emails - high importance from VIP
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Critical Issue",
                        "from": {"emailAddress": {"name": "Boss", "address": "boss@test.com"}},
                        "receivedDateTime": "2024-12-18T08:00:00Z",
                        "importance": "high",
                    }
                ]
            },
            # Tasks
            {"value": []},
        ]

        result = msgraph_daily_focus(mock_ctx)

        assert result["success"] is True
        assert len(result["urgent"]) >= 1
        # Should have meeting response needed
        urgent_types = [u["type"] for u in result["urgent"]]
        assert "meeting_response_needed" in urgent_types

    @patch("code_puppy.tools.msgraph.workflows_focus.get_msgraph_client")
    def test_not_authenticated(self, mock_client, mock_ctx):
        """Test when not authenticated."""
        mock_client.return_value = None

        result = msgraph_daily_focus(mock_ctx)

        assert result["success"] is False


class TestSmartMeetingPrep:
    """Tests for msgraph_smart_meeting_prep."""

    @patch("code_puppy.tools.msgraph.workflows_focus.get_msgraph_client")
    def test_meeting_prep_by_subject(self, mock_client, mock_ctx):
        """Test preparing for a meeting by subject search."""
        mock_client.return_value.get.side_effect = [
            # Find meeting by subject
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Q4 Planning Session",
                        "start": {"dateTime": "2024-12-18T14:00:00Z"},
                        "end": {"dateTime": "2024-12-18T15:00:00Z"},
                        "organizer": {"emailAddress": {"name": "Director", "address": "dir@test.com"}},
                        "attendees": [
                            {
                                "emailAddress": {"name": "Alice", "address": "alice@test.com"},
                                "type": "required",
                                "status": {"response": "accepted"},
                            },
                            {
                                "emailAddress": {"name": "Bob", "address": "bob@test.com"},
                                "type": "optional",
                                "status": {"response": "tentativelyAccepted"},
                            },
                        ],
                        "body": {"content": "Agenda: 1. Review Q3 2. Plan Q4"},
                        "location": {"displayName": "Conference Room A"},
                        "isOnlineMeeting": True,
                        "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/meet/1"},
                        "importance": "high",
                    }
                ]
            },
            # Recent email threads
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "RE: Q4 Planning Prep",
                        "from": {"emailAddress": {"name": "Alice"}},
                        "receivedDateTime": "2024-12-17T10:00:00Z",
                        "bodyPreview": "Here are the numbers...",
                    }
                ]
            },
            # Related files
            {
                "value": [
                    {
                        "id": "file-1",
                        "name": "Q4 Planning Deck.pptx",
                        "webUrl": "https://sharepoint.com/file-1",
                        "lastModifiedDateTime": "2024-12-16T10:00:00Z",
                    }
                ]
            },
            # Previous meetings
            {
                "value": [
                    {
                        "id": "event-old",
                        "subject": "Q3 Planning Session",
                        "start": {"dateTime": "2024-09-15T14:00:00Z"},
                    }
                ]
            },
        ]

        result = msgraph_smart_meeting_prep(
            mock_ctx, meeting_subject="Q4 Planning"
        )

        assert result["success"] is True
        assert result["meeting"]["subject"] == "Q4 Planning Session"
        assert len(result["attendees"]) == 2
        assert result["attendees"][0]["name"] == "Alice"
        assert len(result["recent_threads"]) == 1
        assert len(result["related_files"]) == 1
        assert result["related_files"][0]["name"] == "Q4 Planning Deck.pptx"

    @patch("code_puppy.tools.msgraph.workflows_focus.get_msgraph_client")
    def test_meeting_not_found(self, mock_client, mock_ctx):
        """Test when no matching meeting is found."""
        mock_client.return_value.get.return_value = {"value": []}

        result = msgraph_smart_meeting_prep(
            mock_ctx, meeting_subject="Nonexistent Meeting"
        )

        assert result["success"] is False
        assert "No meeting found" in result["error"]

    def test_no_parameters(self, mock_ctx):
        """Test that missing parameters returns error."""
        result = msgraph_smart_meeting_prep(mock_ctx)

        assert result["success"] is False
        assert "meeting_subject or event_id" in result["error"]
