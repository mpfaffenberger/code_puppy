"""Tests for Microsoft Graph Calendar Attendee Management tools."""

from unittest.mock import Mock, patch

import pytest

from code_puppy.tools.msgraph.calendar_attendees import (
    msgraph_add_event_attendees,
    msgraph_remove_event_attendee,
    msgraph_respond_to_event,
    msgraph_search_events,
)


class TestAddEventAttendees:
    """Tests for msgraph_add_event_attendees."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_add_attendees_success(self, mock_context):
        """Test adding attendees to an event."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Sync",
            "attendees": [
                {"emailAddress": {"address": "existing@test.com"}, "type": "required"},
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_client.patch.return_value = {}
            mock_get_client.return_value = mock_client

            result = msgraph_add_event_attendees(
                mock_context,
                event_id="event-123",
                attendees=["new1@test.com", "new2@test.com"],
            )

            assert result["success"] is True
            assert len(result["added"]) == 2
            assert "new1@test.com" in result["added"]
            assert "new2@test.com" in result["added"]
            assert result["total_attendees"] == 3

    def test_add_attendees_already_exists(self, mock_context):
        """Test adding attendee who already exists."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Sync",
            "attendees": [
                {"emailAddress": {"address": "existing@test.com"}, "type": "required"},
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_get_client.return_value = mock_client

            result = msgraph_add_event_attendees(
                mock_context,
                event_id="event-123",
                attendees=["existing@test.com"],
            )

            assert result["success"] is True
            assert len(result["added"]) == 0
            assert "existing@test.com" in result["skipped"]

    def test_add_attendees_not_authenticated(self, mock_context):
        """Test when not authenticated."""
        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_get_client.return_value = None

            result = msgraph_add_event_attendees(
                mock_context,
                event_id="event-123",
                attendees=["test@test.com"],
            )

            assert result["success"] is False


class TestRemoveEventAttendee:
    """Tests for msgraph_remove_event_attendee."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_remove_attendee_success(self, mock_context):
        """Test removing an attendee from an event."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Sync",
            "attendees": [
                {"emailAddress": {"address": "keep@test.com"}, "type": "required"},
                {"emailAddress": {"address": "remove@test.com"}, "type": "required"},
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_client.patch.return_value = {}
            mock_get_client.return_value = mock_client

            result = msgraph_remove_event_attendee(
                mock_context,
                event_id="event-123",
                attendee_email="remove@test.com",
            )

            assert result["success"] is True
            assert result["removed"] == "remove@test.com"
            assert result["remaining_attendees"] == 1

    def test_remove_attendee_not_found(self, mock_context):
        """Test removing an attendee who isn't on the invite."""
        mock_event = {
            "id": "event-123",
            "subject": "Team Sync",
            "attendees": [
                {"emailAddress": {"address": "other@test.com"}, "type": "required"},
            ],
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event
            mock_get_client.return_value = mock_client

            result = msgraph_remove_event_attendee(
                mock_context,
                event_id="event-123",
                attendee_email="notfound@test.com",
            )

            assert result["success"] is False
            assert "not found" in result["error"]


class TestSearchEvents:
    """Tests for msgraph_search_events."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_search_events_success(self, mock_context):
        """Test searching for events."""
        mock_response = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Weekly Standup",
                    "start": {"dateTime": "2025-01-20T10:00:00Z"},
                    "end": {"dateTime": "2025-01-20T10:30:00Z"},
                    "location": {"displayName": "Room A"},
                    "organizer": {"emailAddress": {"name": "Alice"}},
                    "attendees": [{}, {}],
                    "isOnlineMeeting": False,
                },
                {
                    "id": "event-2",
                    "subject": "Budget Review",
                    "start": {"dateTime": "2025-01-21T14:00:00Z"},
                    "end": {"dateTime": "2025-01-21T15:00:00Z"},
                    "location": {"displayName": "Room B"},
                    "organizer": {"emailAddress": {"name": "Bob"}},
                    "attendees": [],
                    "isOnlineMeeting": True,
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = msgraph_search_events(mock_context, query="standup")

            assert result["success"] is True
            assert result["total_found"] == 1
            assert result["events"][0]["subject"] == "Weekly Standup"

    def test_search_events_no_matches(self, mock_context):
        """Test search with no matches."""
        mock_response = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Team Meeting",
                    "start": {"dateTime": "2025-01-20T10:00:00Z"},
                    "end": {"dateTime": "2025-01-20T11:00:00Z"},
                    "location": {},
                    "organizer": {"emailAddress": {}},
                    "attendees": [],
                    "isOnlineMeeting": False,
                },
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = msgraph_search_events(mock_context, query="nonexistent")

            assert result["success"] is True
            assert result["total_found"] == 0


class TestRespondToEvent:
    """Tests for msgraph_respond_to_event."""

    @pytest.fixture
    def mock_context(self):
        return Mock()

    def test_respond_accept(self, mock_context):
        """Test accepting an event."""
        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {}
            mock_get_client.return_value = mock_client

            result = msgraph_respond_to_event(
                mock_context,
                event_id="event-123",
                response="accept",
            )

            assert result["success"] is True
            assert result["response"] == "accept"
            mock_client.post.assert_called_once()

    def test_respond_decline_with_comment(self, mock_context):
        """Test declining an event with a comment."""
        with patch(
            "code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {}
            mock_get_client.return_value = mock_client

            result = msgraph_respond_to_event(
                mock_context,
                event_id="event-123",
                response="decline",
                comment="I have a conflict",
            )

            assert result["success"] is True
            assert result["response"] == "decline"
            assert result["comment"] == "I have a conflict"

    def test_respond_invalid_response(self, mock_context):
        """Test with invalid response type."""
        result = msgraph_respond_to_event(
            mock_context,
            event_id="event-123",
            response="maybe",
        )

        assert result["success"] is False
        assert "accept" in result["error"] or "decline" in result["error"]
