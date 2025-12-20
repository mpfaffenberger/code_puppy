"""Tests for shared calendar tools."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.calendar_shared import (
    msgraph_list_shared_calendars,
    msgraph_get_user_calendar_events,
    msgraph_find_meeting_times,
    msgraph_get_schedule,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


class TestMSGraphSharedCalendars:
    """Tests for shared calendar operations."""

    def test_msgraph_list_shared_calendars(self, mock_context):
        """Test listing calendars including shared ones."""
        with patch(
            "code_puppy.tools.msgraph.calendar_shared.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "value": [
                    {
                        "id": "cal-001",
                        "name": "Calendar",
                        "isDefaultCalendar": True,
                        "canEdit": True,
                    },
                    {
                        "id": "cal-002",
                        "name": "Team Calendar",
                        "owner": {
                            "name": "Jane Doe",
                            "address": "jane@example.com",
                        },
                        "canEdit": False,
                    },
                ]
            }
            mock_get_client.return_value = mock_client

            result = msgraph_list_shared_calendars(mock_context)

            assert result["success"] is True
            assert len(result["calendars"]) == 2
            assert result["shared_count"] == 1
            assert result["own_count"] == 1

    def test_msgraph_get_user_calendar_events(self, mock_context):
        """Test getting another user's calendar events."""
        with patch(
            "code_puppy.tools.msgraph.calendar_shared.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {
                "value": [
                    {
                        "id": "event-001",
                        "subject": "Team Standup",
                        "start": {"dateTime": "2025-12-18T09:00:00", "timeZone": "UTC"},
                        "end": {"dateTime": "2025-12-18T09:30:00", "timeZone": "UTC"},
                        "showAs": "busy",
                    }
                ]
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_user_calendar_events(
                mock_context,
                "jane@example.com",
                days_ahead=7,
            )

            assert result["success"] is True
            assert result["user_email"] == "jane@example.com"
            assert len(result["events"]) == 1
            assert result["events"][0]["subject"] == "Team Standup"

    def test_msgraph_find_meeting_times(self, mock_context):
        """Test finding meeting times for multiple attendees."""
        with patch(
            "code_puppy.tools.msgraph.calendar_shared.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {
                "meetingTimeSuggestions": [
                    {
                        "meetingTimeSlot": {
                            "start": {
                                "dateTime": "2025-12-19T10:00:00",
                                "timeZone": "UTC",
                            },
                            "end": {
                                "dateTime": "2025-12-19T10:30:00",
                                "timeZone": "UTC",
                            },
                        },
                        "confidence": 100.0,
                        "organizerAvailability": "free",
                    }
                ]
            }
            mock_get_client.return_value = mock_client

            result = msgraph_find_meeting_times(
                mock_context,
                ["jane@example.com", "john@example.com"],
                duration_minutes=30,
            )

            assert result["success"] is True
            assert len(result["suggestions"]) == 1
            assert result["suggestions"][0]["confidence"] == 100.0

    def test_msgraph_get_schedule(self, mock_context):
        """Test getting free/busy schedule for users."""
        with patch(
            "code_puppy.tools.msgraph.calendar_shared.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {
                "value": [
                    {
                        "scheduleId": "jane@example.com",
                        "availabilityView": "002222000000000000",
                        "scheduleItems": [
                            {
                                "start": {"dateTime": "2025-12-18T10:00:00"},
                                "end": {"dateTime": "2025-12-18T11:00:00"},
                                "status": "busy",
                            }
                        ],
                    }
                ]
            }
            mock_get_client.return_value = mock_client

            result = msgraph_get_schedule(
                mock_context,
                ["jane@example.com"],
                "2025-12-18T09:00:00",
                "2025-12-18T17:00:00",
            )

            assert result["success"] is True
            assert len(result["schedules"]) == 1
            assert result["schedules"][0]["email"] == "jane@example.com"
