"""Tests for Microsoft Graph Meeting Health tools."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from code_puppy.tools.msgraph.meeting_health import (
    _assess_meeting_health,
    _calculate_acceptance_rate,
    _check_room_status,
    msgraph_analyze_meeting_health,
    msgraph_find_my_pending_responses,
    msgraph_find_pending_rsvps,
    msgraph_get_meeting_responses,
    msgraph_suggest_reschedule,
)


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_calculate_acceptance_rate_empty(self):
        """Test with no attendees."""
        result = _calculate_acceptance_rate([])
        assert result["total"] == 0
        assert result["acceptance_rate"] == 0.0

    def test_calculate_acceptance_rate_all_accepted(self):
        """Test with all attendees accepted."""
        attendees = [
            {"status": {"response": "accepted"}},
            {"status": {"response": "accepted"}},
            {"status": {"response": "accepted"}},
        ]
        result = _calculate_acceptance_rate(attendees)
        assert result["total"] == 3
        assert result["accepted"] == 3
        assert result["acceptance_rate"] == 100.0

    def test_calculate_acceptance_rate_mixed(self):
        """Test with mixed responses."""
        attendees = [
            {"status": {"response": "accepted"}},
            {"status": {"response": "declined"}},
            {"status": {"response": "tentativelyAccepted"}},
            {"status": {"response": "none"}},
        ]
        result = _calculate_acceptance_rate(attendees)
        assert result["total"] == 4
        assert result["accepted"] == 1
        assert result["declined"] == 1
        assert result["tentative"] == 1
        assert result["no_response"] == 1
        assert result["acceptance_rate"] == 25.0

    def test_check_room_status_no_location(self):
        """Test with no location."""
        result = _check_room_status(None)
        assert result["has_room"] is False
        assert "No location specified" in result["issues"]

    def test_check_room_status_conference_room(self):
        """Test with valid conference room."""
        location = {
            "displayName": "Conference Room A",
            "locationType": "conferenceRoom",
        }
        result = _check_room_status(location)
        assert result["has_room"] is True
        assert result["room_name"] == "Conference Room A"
        assert result["issues"] == []

    def test_check_room_status_tbd(self):
        """Test with TBD location."""
        location = {"displayName": "TBD", "locationType": ""}
        result = _check_room_status(location)
        assert result["has_room"] is False
        assert "Location not confirmed" in result["issues"]

    def test_assess_meeting_health_healthy(self):
        """Test health assessment for a healthy meeting."""
        event = {
            "attendees": [
                {"status": {"response": "accepted"}},
                {"status": {"response": "accepted"}},
            ],
            "location": {
                "displayName": "Room 101",
                "locationType": "conferenceRoom",
            },
        }
        result = _assess_meeting_health(event)
        assert result["health"] == "healthy"
        assert result["issues"] == []

    def test_assess_meeting_health_low_acceptance(self):
        """Test health assessment for low acceptance rate."""
        event = {
            "attendees": [
                {"status": {"response": "accepted"}},
                {"status": {"response": "none"}},
                {"status": {"response": "none"}},
                {"status": {"response": "none"}},
            ],
            "location": {"displayName": "Room 101"},
        }
        result = _assess_meeting_health(event)
        assert result["health"] in ("warning", "critical")
        assert any(i["type"] == "low_acceptance" for i in result["issues"])


class TestAnalyzeMeetingHealth:
    """Tests for msgraph_analyze_meeting_health."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    @pytest.fixture
    def mock_events_response(self):
        now = datetime.now(timezone.utc)
        return {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Healthy Meeting",
                    "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                    "end": {"dateTime": (now + timedelta(days=1, hours=1)).isoformat()},
                    "location": {"displayName": "Room A"},
                    "attendees": [
                        {"status": {"response": "accepted"}},
                        {"status": {"response": "accepted"}},
                    ],
                    "isOnlineMeeting": False,
                },
                {
                    "id": "event-2",
                    "subject": "Problem Meeting",
                    "start": {"dateTime": (now + timedelta(hours=2)).isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=3)).isoformat()},
                    "location": {"displayName": "TBD"},
                    "attendees": [
                        {"status": {"response": "none"}},
                        {"status": {"response": "none"}},
                        {"status": {"response": "none"}},
                    ],
                    "isOnlineMeeting": False,
                },
            ]
        }

    def test_analyze_meeting_health_success(self, mock_context, mock_events_response):
        """Test successful meeting health analysis."""
        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_events_response
            mock_get_client.return_value = mock_client

            result = msgraph_analyze_meeting_health(mock_context, days_ahead=7)

            assert result["success"] is True
            assert result["summary"]["total_meetings"] == 2
            assert len(result["critical"]) >= 1  # Problem meeting
            assert "recommendations" in result

    def test_analyze_meeting_health_not_authenticated(self, mock_context):
        """Test when not authenticated."""
        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_get_client.return_value = None

            result = msgraph_analyze_meeting_health(mock_context)

            assert result["success"] is False
            assert "error" in result


class TestGetMeetingResponses:
    """Tests for msgraph_get_meeting_responses."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_get_meeting_responses_success(self, mock_context):
        """Test getting meeting response details."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Sync",
            "start": {"dateTime": "2025-01-20T10:00:00Z"},
            "attendees": [
                {
                    "emailAddress": {"name": "Alice", "address": "alice@test.com"},
                    "status": {"response": "accepted"},
                    "type": "required",
                },
                {
                    "emailAddress": {"name": "Bob", "address": "bob@test.com"},
                    "status": {"response": "declined"},
                    "type": "required",
                },
                {
                    "emailAddress": {"name": "Carol", "address": "carol@test.com"},
                    "status": {"response": "none"},
                    "type": "optional",
                },
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_get_client.return_value = mock_client

            result = msgraph_get_meeting_responses(mock_context, event_id="event-123")

            assert result["success"] is True
            assert result["event_id"] == "event-123"
            assert len(result["accepted"]) == 1
            assert len(result["declined"]) == 1
            assert len(result["no_response"]) == 1
            assert result["statistics"]["total"] == 3


class TestFindPendingRsvps:
    """Tests for msgraph_find_pending_rsvps."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_find_pending_rsvps_success(self, mock_context):
        """Test finding meetings with pending RSVPs."""
        now = datetime.now(timezone.utc)
        mock_response = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Needs Follow-up",
                    "start": {"dateTime": (now + timedelta(hours=12)).isoformat()},
                    "attendees": [
                        {
                            "emailAddress": {"name": "Person 1"},
                            "status": {"response": "none"},
                        },
                        {
                            "emailAddress": {"name": "Person 2"},
                            "status": {"response": "none"},
                        },
                        {
                            "emailAddress": {"name": "Person 3"},
                            "status": {"response": "accepted"},
                        },
                    ],
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = msgraph_find_pending_rsvps(
                mock_context, hours_ahead=48, min_no_response_pct=50.0
            )

            assert result["success"] is True
            assert result["total_found"] == 1
            assert result["meetings_needing_followup"][0]["no_response_pct"] > 50


class TestFindMyPendingResponses:
    """Tests for msgraph_find_my_pending_responses."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_find_my_pending_responses_success(self, mock_context):
        """Test finding meetings I haven't responded to."""
        mock_response = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Awaiting My RSVP",
                    "start": {"dateTime": "2025-01-22T14:00:00Z"},
                    "end": {"dateTime": "2025-01-22T15:00:00Z"},
                    "location": {"displayName": "Room B"},
                    "organizer": {
                        "emailAddress": {
                            "name": "Meeting Host",
                            "address": "host@test.com",
                        }
                    },
                    "isOnlineMeeting": True,
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = msgraph_find_my_pending_responses(mock_context, days_ahead=7)

            assert result["success"] is True
            assert result["total_pending"] == 1
            assert result["pending_responses"][0]["organizer_name"] == "Meeting Host"


class TestSuggestReschedule:
    """Tests for msgraph_suggest_reschedule."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_suggest_reschedule_success(self, mock_context):
        """Test suggesting reschedule times."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Meeting",
            "start": {"dateTime": "2025-01-20T10:00:00Z"},
            "end": {"dateTime": "2025-01-20T11:00:00Z"},
            "attendees": [
                {"emailAddress": {"name": "Alice", "address": "alice@test.com"}},
                {"emailAddress": {"name": "Bob", "address": "bob@test.com"}},
            ],
        }

        mock_suggestions = {
            "meetingTimeSuggestions": [
                {
                    "meetingTimeSlot": {
                        "start": {"dateTime": "2025-01-21T14:00:00Z"},
                        "end": {"dateTime": "2025-01-21T15:00:00Z"},
                    },
                    "confidence": 100,
                    "attendeeAvailability": [
                        {
                            "attendee": {
                                "emailAddress": {"name": "Alice"},
                            },
                            "availability": "free",
                        },
                        {
                            "attendee": {
                                "emailAddress": {"name": "Bob"},
                            },
                            "availability": "free",
                        },
                    ],
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_client.post.return_value = mock_suggestions
            mock_get_client.return_value = mock_client

            result = msgraph_suggest_reschedule(mock_context, event_id="event-123")

            assert result["success"] is True
            assert result["total_suggestions"] == 1
            assert result["suggestions"][0]["confidence"] == 100

    def test_suggest_reschedule_no_attendees(self, mock_context):
        """Test when meeting has no attendees."""
        mock_event = {
            "id": "event-123",
            "subject": "Solo Meeting",
            "start": {"dateTime": "2025-01-20T10:00:00Z"},
            "end": {"dateTime": "2025-01-20T11:00:00Z"},
            "attendees": [],
        }

        with patch(
            "code_puppy.tools.msgraph.meeting_health.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_get_client.return_value = mock_client

            result = msgraph_suggest_reschedule(mock_context, event_id="event-123")

            assert result["success"] is False
            assert "No attendees" in result["error"]
