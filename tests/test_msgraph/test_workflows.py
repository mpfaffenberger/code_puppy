"""Unit tests for MS Graph workflow module.

Tests the high-level workflow tools:
- msgraph_prepare_meeting_brief
- msgraph_daily_digest
- msgraph_smart_schedule
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from code_puppy.tools.msgraph.workflows import (
    msgraph_prepare_meeting_brief,
    msgraph_daily_digest,
    msgraph_smart_schedule,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_event_data():
    """Create mock event data from MS Graph API."""
    return {
        "id": "event-123-abc",
        "subject": "Team Standup",
        "start": {
            "dateTime": "2025-12-18T09:00:00",
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": "2025-12-18T09:30:00",
            "timeZone": "UTC",
        },
        "location": {
            "displayName": "Conference Room A",
        },
        "body": {
            "contentType": "html",
            "content": "<p>Daily standup meeting</p>",
        },
        "isOnlineMeeting": True,
        "onlineMeetingUrl": "https://teams.microsoft.com/meeting/123",
        "organizer": {
            "emailAddress": {
                "name": "John Doe",
                "address": "john.doe@walmart.com",
            }
        },
        "attendees": [
            {
                "emailAddress": {
                    "name": "Alice Smith",
                    "address": "alice.smith@walmart.com",
                },
                "type": "required",
                "status": {"response": "accepted"},
            },
            {
                "emailAddress": {
                    "name": "Bob Jones",
                    "address": "bob.jones@walmart.com",
                },
                "type": "required",
                "status": {"response": "tentativelyAccepted"},
            },
            {
                "emailAddress": {
                    "name": "Charlie Brown",
                    "address": "charlie.brown@walmart.com",
                },
                "type": "optional",
                "status": {"response": "none"},
            },
        ],
    }


class TestMsgraphPrepareMeetingBrief:
    """Tests for msgraph_prepare_meeting_brief workflow."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_brief_by_event_id(
        self, mock_client_fn, mock_context, mock_event_data
    ):
        """Test preparing brief using event ID."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = mock_event_data

        result = msgraph_prepare_meeting_brief(
            mock_context,
            event_id="event-123-abc",
        )

        assert result["success"] is True
        assert result["meeting"]["subject"] == "Team Standup"
        assert result["attendance"]["total"] == 3
        assert result["attendance"]["accepted"] == 1
        assert result["attendance"]["tentative"] == 1
        assert result["attendance"]["no_response"] == 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_brief_by_subject(
        self, mock_client_fn, mock_context, mock_event_data
    ):
        """Test preparing brief using meeting subject search."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": [mock_event_data]}

        result = msgraph_prepare_meeting_brief(
            mock_context,
            meeting_subject="Standup",
        )

        assert result["success"] is True
        assert "Team Standup" in result["meeting"]["subject"]

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_brief_no_match(self, mock_client_fn, mock_context):
        """Test error when no meeting matches subject."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {"value": []}

        result = msgraph_prepare_meeting_brief(
            mock_context,
            meeting_subject="NonexistentMeeting",
        )

        assert result["success"] is False
        assert "No upcoming meeting found" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_brief_missing_params(self, mock_client_fn, mock_context):
        """Test error when neither event_id nor meeting_subject provided."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        result = msgraph_prepare_meeting_brief(mock_context)

        assert result["success"] is False
        assert "Either event_id or meeting_subject" in result["error"]

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_brief_not_authenticated(self, mock_client_fn, mock_context):
        """Test error when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_prepare_meeting_brief(
            mock_context,
            event_id="event-123",
        )

        assert result["success"] is False


class TestMsgraphDailyDigest:
    """Tests for msgraph_daily_digest workflow."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_daily_digest_success(self, mock_client_fn, mock_context):
        """Test generating daily digest successfully."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        # Mock calendar response
        mock_client.get.side_effect = [
            # Today's events
            {
                "value": [
                    {
                        "id": "evt-1",
                        "subject": "Morning Standup",
                        "start": {"dateTime": "2025-12-18T09:00:00"},
                        "end": {"dateTime": "2025-12-18T09:30:00"},
                        "location": {"displayName": "Room A"},
                        "attendees": [
                            {"status": {"response": "accepted"}},
                            {"status": {"response": "accepted"}},
                        ],
                        "responseStatus": {"response": "accepted"},
                    }
                ]
            },
            # Tomorrow's events
            {
                "value": [
                    {
                        "id": "evt-2",
                        "subject": "Planning Meeting",
                        "start": {"dateTime": "2025-12-19T14:00:00"},
                        "location": {"displayName": "Room B"},
                        "responseStatus": {"response": "accepted"},
                    }
                ]
            },
            # Unread emails
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Urgent: Review needed",
                        "from": {
                            "emailAddress": {
                                "name": "Boss",
                                "address": "boss@walmart.com",
                            }
                        },
                        "receivedDateTime": "2025-12-18T08:00:00",
                        "importance": "high",
                    }
                ]
            },
        ]

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is True
        assert len(result["today"]) == 1
        assert len(result["tomorrow"]) == 1
        assert len(result["unread_emails"]) == 1
        assert result["summary"]["meetings_today"] == 1
        assert result["summary"]["meetings_tomorrow"] == 1

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_daily_digest_without_tomorrow(self, mock_client_fn, mock_context):
        """Test daily digest without tomorrow's events."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.side_effect = [
            {"value": []},  # Today's events
            {"value": []},  # Unread emails
        ]

        result = msgraph_daily_digest(mock_context, include_tomorrow=False)

        assert result["success"] is True
        assert result["tomorrow"] == []

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_daily_digest_not_authenticated(self, mock_client_fn, mock_context):
        """Test error when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_daily_digest_pending_responses(self, mock_client_fn, mock_context):
        """Test that pending responses are captured."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.side_effect = [
            # Today's events with one pending response
            {
                "value": [
                    {
                        "id": "evt-1",
                        "subject": "Need RSVP",
                        "start": {"dateTime": "2025-12-18T10:00:00"},
                        "end": {"dateTime": "2025-12-18T11:00:00"},
                        "location": {},
                        "attendees": [],
                        "responseStatus": {"response": "notResponded"},
                    }
                ]
            },
            {"value": []},  # Tomorrow
            {"value": []},  # Unread
        ]

        result = msgraph_daily_digest(mock_context)

        assert result["success"] is True
        assert len(result["pending_responses"]) == 1
        assert "Need RSVP" in result["pending_responses"][0]["subject"]


class TestMsgraphSmartSchedule:
    """Tests for msgraph_smart_schedule workflow."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_smart_schedule_find_times(self, mock_client_fn, mock_context):
        """Test finding available meeting times."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        # Mock findMeetingTimes response
        mock_client.post.return_value = {
            "meetingTimeSuggestions": [
                {
                    "confidence": 100.0,
                    "meetingTimeSlot": {
                        "start": {
                            "dateTime": "2025-12-19T10:00:00",
                            "timeZone": "UTC",
                        },
                        "end": {
                            "dateTime": "2025-12-19T11:00:00",
                            "timeZone": "UTC",
                        },
                    },
                },
                {
                    "confidence": 80.0,
                    "meetingTimeSlot": {
                        "start": {
                            "dateTime": "2025-12-19T14:00:00",
                            "timeZone": "UTC",
                        },
                        "end": {
                            "dateTime": "2025-12-19T15:00:00",
                            "timeZone": "UTC",
                        },
                    },
                },
            ]
        }

        result = msgraph_smart_schedule(
            mock_context,
            subject="1:1 Sync",
            attendees=["alice@walmart.com", "bob@walmart.com"],
            duration_minutes=60,
        )

        assert result["success"] is True
        assert "suggestions" in result
        assert len(result["suggestions"]) == 2

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_smart_schedule_no_attendees(self, mock_client_fn, mock_context):
        """Test error when no attendees provided."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        result = msgraph_smart_schedule(
            mock_context,
            subject="Meeting",
            attendees=[],
        )

        assert result["success"] is False
        assert "at least one attendee" in result["error"].lower()

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_smart_schedule_not_authenticated(self, mock_client_fn, mock_context):
        """Test error when not authenticated."""
        mock_client_fn.return_value = None

        result = msgraph_smart_schedule(
            mock_context,
            subject="Meeting",
            attendees=["alice@walmart.com"],
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_smart_schedule_auto_create(self, mock_client_fn, mock_context):
        """Test auto-creating event at best time."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client

        # Mock findMeetingTimes response
        mock_client.post.side_effect = [
            # First call: findMeetingTimes
            {
                "meetingTimeSuggestions": [
                    {
                        "confidence": 100.0,
                        "meetingTimeSlot": {
                            "start": {
                                "dateTime": "2025-12-19T10:00:00",
                                "timeZone": "UTC",
                            },
                            "end": {
                                "dateTime": "2025-12-19T11:00:00",
                                "timeZone": "UTC",
                            },
                        },
                    },
                ]
            },
            # Second call: create event
            {
                "id": "new-event-123",
                "subject": "1:1 Sync",
                "start": {
                    "dateTime": "2025-12-19T10:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2025-12-19T11:00:00",
                    "timeZone": "UTC",
                },
            },
        ]

        result = msgraph_smart_schedule(
            mock_context,
            subject="1:1 Sync",
            attendees=["alice@walmart.com"],
            auto_create=True,
        )

        assert result["success"] is True
        # Verify event creation was attempted
        assert mock_client.post.call_count == 2


class TestWorkflowToolFunctionSignatures:
    """Smoke tests to verify all workflow tools have correct signatures."""

    def test_prepare_meeting_brief_signature(self):
        """Verify msgraph_prepare_meeting_brief has expected parameters."""
        import inspect

        sig = inspect.signature(msgraph_prepare_meeting_brief)
        params = list(sig.parameters.keys())

        assert "ctx" in params
        assert "event_id" in params
        assert "meeting_subject" in params

    def test_daily_digest_signature(self):
        """Verify msgraph_daily_digest has expected parameters."""
        import inspect

        sig = inspect.signature(msgraph_daily_digest)
        params = list(sig.parameters.keys())

        assert "ctx" in params
        assert "include_tomorrow" in params

    def test_smart_schedule_signature(self):
        """Verify msgraph_smart_schedule has expected parameters."""
        import inspect

        sig = inspect.signature(msgraph_smart_schedule)
        params = list(sig.parameters.keys())

        assert "ctx" in params
        assert "subject" in params
        assert "attendees" in params
        assert "duration_minutes" in params
        assert "prefer_morning" in params
        assert "auto_create" in params
