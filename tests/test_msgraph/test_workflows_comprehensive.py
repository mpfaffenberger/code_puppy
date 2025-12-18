"""Comprehensive tests for workflows.py to achieve higher coverage.

These tests target specific branches and error paths.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.msgraph.workflows import (
    msgraph_prepare_meeting_brief,
    msgraph_daily_digest,
    msgraph_smart_schedule,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return MagicMock()


class TestPrepareMeetingBrief:
    """Tests for msgraph_prepare_meeting_brief."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_prepare_meeting_brief(mock_context, event_id="event-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_with_event_id(self, mock_client_fn, mock_context):
        """Test with direct event_id."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # Event details
            {
                "id": "event-123",
                "subject": "Design Review",
                "start": {"dateTime": (now + timedelta(hours=2)).isoformat()},
                "end": {"dateTime": (now + timedelta(hours=3)).isoformat()},
                "location": {"displayName": "Room A"},
                "body": {"content": "Review the new design"},
                "attendees": [
                    {
                        "emailAddress": {
                            "address": "alice@walmart.com",
                            "name": "Alice",
                        },
                        "status": {"response": "accepted"},
                    },
                ],
                "organizer": {"emailAddress": {"address": "me@walmart.com"}},
                "isOnlineMeeting": True,
                "onlineMeetingUrl": "https://teams.microsoft.com/meet",
            },
            # Attendee profile
            {
                "displayName": "Alice",
                "jobTitle": "Designer",
                "department": "UX",
            },
            # Related emails
            {"value": []},
            # OneDrive files
            {"value": []},
        ]

        result = msgraph_prepare_meeting_brief(mock_context, event_id="event-123")

        assert result["success"] is True
        assert result["meeting"]["subject"] == "Design Review"

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_with_meeting_subject(self, mock_client_fn, mock_context):
        """Test searching by meeting subject."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # Search for events
            {
                "value": [
                    {
                        "id": "event-found",
                        "subject": "Sprint Planning",
                        "start": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                        "end": {"dateTime": (now + timedelta(hours=2)).isoformat()},
                        "location": {},
                        "body": {},
                        "attendees": [],
                        "organizer": {"emailAddress": {"address": "me@walmart.com"}},
                    }
                ]
            },
            # Related emails
            {"value": []},
            # OneDrive files
            {"value": []},
        ]

        result = msgraph_prepare_meeting_brief(mock_context, meeting_subject="Sprint")

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_no_event_or_subject(self, mock_client_fn, mock_context):
        """Test when neither event_id nor meeting_subject provided."""
        client = MagicMock()
        mock_client_fn.return_value = client

        result = msgraph_prepare_meeting_brief(mock_context)

        assert result["success"] is False
        assert "event_id or meeting_subject" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_meeting_not_found(self, mock_client_fn, mock_context):
        """Test when meeting subject search finds nothing."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.return_value = {"value": []}

        result = msgraph_prepare_meeting_brief(
            mock_context, meeting_subject="Nonexistent"
        )

        assert result["success"] is False
        assert "No upcoming meeting found" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_attendee_profile_lookup_fails(self, mock_client_fn, mock_context):
        """Test graceful handling when attendee profile lookup fails."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        call_count = [0]

        def side_effect(path, **kwargs):
            call_count[0] += 1
            if "/me/events/" in path:
                return {
                    "id": "event-123",
                    "subject": "Meeting",
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                    "attendees": [
                        {
                            "emailAddress": {
                                "address": "alice@walmart.com",
                                "name": "Alice",
                            }
                        }
                    ],
                    "organizer": {"emailAddress": {"address": "me@walmart.com"}},
                }
            if "/users/" in path:
                raise Exception("User not found")
            return {"value": []}

        client.get.side_effect = side_effect

        result = msgraph_prepare_meeting_brief(mock_context, event_id="event-123")

        assert result["success"] is True
        # Attendee should still be listed but without detailed profile

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_general_exception(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("Network error")

        result = msgraph_prepare_meeting_brief(mock_context, event_id="event-123")

        assert result["success"] is False


class TestDailyDigest:
    """Tests for msgraph_daily_digest."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_basic_digest(self, mock_client_fn, mock_context):
        """Test basic daily digest generation."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)

        client.get.side_effect = [
            # Today's events
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Team Sync",
                        "start": {"dateTime": now.isoformat()},
                        "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                        "location": {},
                        "attendees": [],
                        "isOnlineMeeting": False,
                        "responseStatus": {"response": "accepted"},
                    }
                ]
            },
            # Tomorrow's events
            {"value": []},
            # Unread emails
            {"value": []},
            # Pending responses
            {"value": []},
        ]

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is True
        assert "today" in result
        assert len(result["today"]) >= 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_digest_with_tomorrow(self, mock_client_fn, mock_context):
        """Test digest includes tomorrow's events."""
        client = MagicMock()
        mock_client_fn.return_value = client

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        client.get.side_effect = [
            # Today's events
            {"value": []},
            # Tomorrow's events
            {
                "value": [
                    {
                        "id": "event-tomorrow",
                        "subject": "Planning Meeting",
                        "start": {"dateTime": tomorrow.isoformat()},
                        "end": {
                            "dateTime": (tomorrow + timedelta(hours=1)).isoformat()
                        },
                        "location": {},
                        "attendees": [],
                        "isOnlineMeeting": True,
                        "responseStatus": {},
                    }
                ]
            },
            # Unread emails
            {"value": []},
            # Pending responses
            {"value": []},
        ]

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is True
        assert "tomorrow" in result
        assert len(result["tomorrow"]) >= 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_digest_with_unread_emails(self, mock_client_fn, mock_context):
        """Test digest with unread emails."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.get.side_effect = [
            {"value": []},  # Today
            {"value": []},  # Tomorrow
            # Unread emails
            {
                "value": [
                    {
                        "id": "mail-1",
                        "subject": "Important update",
                        "from": {
                            "emailAddress": {
                                "name": "Colleague",
                                "address": "colleague@walmart.com",
                            }
                        },
                        "receivedDateTime": "2025-12-18T10:00:00Z",
                        "importance": "normal",
                    }
                ]
            },
            # Pending responses
            {"value": []},
        ]

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is True
        assert len(result["unread_emails"]) >= 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_general_exception(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("Network error")

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is False


class TestSmartSchedule:
    """Tests for msgraph_smart_schedule."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_not_authenticated(self, mock_client_fn, mock_context):
        """Test when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_smart_schedule(
            mock_context,
            attendees=["alice@walmart.com"],
            duration_minutes=30,
            subject="Test Meeting",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_find_available_slots(self, mock_client_fn, mock_context):
        """Test finding available slots."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.post.return_value = {
            "meetingTimeSuggestions": [
                {
                    "confidence": 100,
                    "meetingTimeSlot": {
                        "start": {"dateTime": "2025-12-18T10:00:00"},
                        "end": {"dateTime": "2025-12-18T10:30:00"},
                    },
                    "attendeeAvailability": [
                        {"attendee": {"emailAddress": {"address": "alice@walmart.com"}}}
                    ],
                }
            ]
        }

        result = msgraph_smart_schedule(
            mock_context,
            attendees=["alice@walmart.com"],
            duration_minutes=30,
            subject="Quick Sync",
        )

        assert result["success"] is True
        assert len(result["suggestions"]) >= 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_no_available_slots(self, mock_client_fn, mock_context):
        """Test when no available slots found."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.post.return_value = {"meetingTimeSuggestions": []}

        result = msgraph_smart_schedule(
            mock_context,
            attendees=["alice@walmart.com"],
            duration_minutes=30,
            subject="Test",
        )

        assert result["success"] is True
        assert len(result["suggestions"]) == 0

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_create_meeting_after_selection(self, mock_client_fn, mock_context):
        """Test creating meeting after finding slot."""
        client = MagicMock()
        mock_client_fn.return_value = client

        client.post.side_effect = [
            # Find meeting times
            {
                "meetingTimeSuggestions": [
                    {
                        "confidence": 100,
                        "meetingTimeSlot": {
                            "start": {"dateTime": "2025-12-18T10:00:00"},
                            "end": {"dateTime": "2025-12-18T10:30:00"},
                        },
                    }
                ]
            },
            # Create event
            {
                "id": "event-new",
                "subject": "Quick Sync",
                "start": {"dateTime": "2025-12-18T10:00:00"},
                "end": {"dateTime": "2025-12-18T10:30:00"},
            },
        ]

        result = msgraph_smart_schedule(
            mock_context,
            attendees=["alice@walmart.com"],
            duration_minutes=30,
            subject="Quick Sync",
            auto_create=True,
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_general_exception(self, mock_client_fn, mock_context):
        """Test general exception handling."""
        mock_client_fn.side_effect = Exception("API error")

        result = msgraph_smart_schedule(
            mock_context,
            attendees=["alice@walmart.com"],
            duration_minutes=30,
            subject="Test",
        )

        assert result["success"] is False
