"""Unit tests for MS Graph calendar module."""

import pytest
from unittest.mock import Mock, patch

from code_puppy.tools.msgraph.calendar import (
    msgraph_list_events,
    msgraph_get_event,
    msgraph_create_event,
    msgraph_update_event,
    msgraph_delete_event,
    msgraph_get_availability,
    msgraph_list_calendars,
)
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphAuthError,
    MSGraphNotFoundError,
)


@pytest.fixture
def mock_context():
    """Create a mock RunContext."""
    return Mock()


@pytest.fixture
def mock_event_preview_data():
    """Create mock event preview data from MS Graph API."""
    return {
        "value": [
            {
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
                "isAllDay": False,
                "isOnlineMeeting": True,
                "responseStatus": {
                    "response": "accepted",
                },
            },
            {
                "id": "event-456-def",
                "subject": "Project Review",
                "start": {
                    "dateTime": "2025-12-18T14:00:00",
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": "2025-12-18T15:00:00",
                    "timeZone": "UTC",
                },
                "location": {
                    "displayName": "",
                },
                "isAllDay": False,
                "isOnlineMeeting": False,
                "responseStatus": {
                    "response": "tentativelyAccepted",
                },
            },
        ]
    }


@pytest.fixture
def mock_event_full_data():
    """Create mock full event data from MS Graph API."""
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
            "content": "<html><body><p>Daily team standup meeting</p></body></html>",
        },
        "organizer": {
            "emailAddress": {
                "name": "John Doe",
                "address": "john.doe@walmart.com",
            },
        },
        "attendees": [
            {
                "emailAddress": {
                    "name": "Alice Johnson",
                    "address": "alice.johnson@walmart.com",
                },
                "type": "required",
                "status": {
                    "response": "accepted",
                },
            },
            {
                "emailAddress": {
                    "name": "Bob Williams",
                    "address": "bob.williams@walmart.com",
                },
                "type": "optional",
                "status": {
                    "response": "tentativelyAccepted",
                },
            },
        ],
        "isAllDay": False,
        "isCancelled": False,
        "isOnlineMeeting": True,
        "onlineMeeting": {
            "joinUrl": "https://teams.microsoft.com/l/meetup-join/12345",
        },
        "webLink": "https://outlook.office.com/calendar/item/12345",
        "responseStatus": {
            "response": "accepted",
        },
    }


@pytest.fixture
def mock_calendars_data():
    """Create mock calendars data from MS Graph API."""
    return {
        "value": [
            {
                "id": "calendar-default",
                "name": "Calendar",
                "color": "auto",
                "isDefaultCalendar": True,
                "canEdit": True,
                "canShare": True,
                "owner": {
                    "name": "John Doe",
                    "address": "john.doe@walmart.com",
                },
            },
            {
                "id": "calendar-work",
                "name": "Work",
                "color": "lightBlue",
                "isDefaultCalendar": False,
                "canEdit": True,
                "canShare": False,
                "owner": {
                    "name": "John Doe",
                    "address": "john.doe@walmart.com",
                },
            },
            {
                "id": "calendar-shared",
                "name": "Team Calendar",
                "color": "lightGreen",
                "isDefaultCalendar": False,
                "canEdit": False,
                "canShare": False,
                "owner": {
                    "name": "Team Lead",
                    "address": "team.lead@walmart.com",
                },
            },
        ]
    }


@pytest.fixture
def mock_availability_data():
    """Create mock availability/schedule data from MS Graph API."""
    return {
        "value": [
            {
                "scheduleId": "alice.johnson@walmart.com",
                "availabilityView": "0000222200002222",
                "scheduleItems": [
                    {
                        "status": "busy",
                        "subject": "Meeting",
                        "location": "Room A",
                        "start": {
                            "dateTime": "2025-12-18T10:00:00",
                            "timeZone": "UTC",
                        },
                        "end": {
                            "dateTime": "2025-12-18T11:00:00",
                            "timeZone": "UTC",
                        },
                    },
                ],
                "workingHours": {
                    "startTime": "08:00:00",
                    "endTime": "17:00:00",
                },
            },
            {
                "scheduleId": "bob.williams@walmart.com",
                "availabilityView": "0000000000000000",
                "scheduleItems": [],
                "workingHours": {
                    "startTime": "09:00:00",
                    "endTime": "18:00:00",
                },
            },
        ]
    }


class TestMSGraphCalendarTools:
    """Test suite for MS Graph calendar tools."""

    def test_msgraph_list_events(self, mock_context, mock_event_preview_data):
        """Test listing calendar events with default parameters."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event_preview_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_events(mock_context)

            assert result["success"] is True
            assert "events" in result
            assert result["total_count"] == 2
            assert len(result["events"]) == 2

            # Check first event
            event1 = result["events"][0]
            assert event1["id"] == "event-123-abc"
            assert event1["subject"] == "Team Standup"
            assert event1["start"] == "2025-12-18T09:00:00"
            assert event1["end"] == "2025-12-18T09:30:00"
            assert event1["location"] == "Conference Room A"
            assert event1["is_all_day"] is False
            assert event1["is_online_meeting"] is True
            assert event1["response_status"] == "accepted"

            # Verify calendarView endpoint was used
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/calendarView"

    def test_msgraph_list_events_with_date_range(
        self, mock_context, mock_event_preview_data
    ):
        """Test listing events with custom date range."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event_preview_data
            mock_get_client.return_value = mock_client

            start = "2025-12-18T00:00:00Z"
            end = "2025-12-25T23:59:59Z"
            result = msgraph_list_events(mock_context, start=start, end=end)

            assert result["success"] is True
            assert result["start"] == start
            assert result["end"] == end

            # Verify date params were passed to API
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["startDateTime"] == start
            assert call_args[1]["params"]["endDateTime"] == end

    def test_msgraph_list_events_with_limit(self, mock_context):
        """Test listing events with custom limit."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_events(mock_context, limit=25)

            assert result["success"] is True

            # Verify limit was passed
            call_args = mock_client.get.call_args
            assert call_args[1]["params"]["$top"] == 25

    def test_msgraph_list_events_empty_results(self, mock_context):
        """Test listing events with no results."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_events(mock_context)

            assert result["success"] is True
            assert result["events"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_events_auth_error(self, mock_context):
        """Test handling of authentication error when listing events."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_events(mock_context)

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]

    def test_msgraph_get_event(self, mock_context, mock_event_full_data):
        """Test getting a specific event by ID."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_event_full_data
            mock_get_client.return_value = mock_client

            result = msgraph_get_event(mock_context, "event-123-abc")

            assert result["success"] is True
            assert "event" in result

            event = result["event"]
            assert event["id"] == "event-123-abc"
            assert event["subject"] == "Team Standup"
            assert event["start"] == "2025-12-18T09:00:00"
            assert event["end"] == "2025-12-18T09:30:00"
            assert event["location"] == "Conference Room A"

            # Check organizer
            assert event["organizer"]["name"] == "John Doe"
            assert event["organizer"]["email"] == "john.doe@walmart.com"

            # Check attendees
            assert len(event["attendees"]) == 2
            assert event["attendees"][0]["name"] == "Alice Johnson"
            assert event["attendees"][0]["email"] == "alice.johnson@walmart.com"
            assert event["attendees"][0]["type"] == "required"
            assert event["attendees"][0]["response"] == "accepted"

            # Check meeting details
            assert event["is_online_meeting"] is True
            assert (
                event["teams_link"] == "https://teams.microsoft.com/l/meetup-join/12345"
            )
            assert event["web_link"] == "https://outlook.office.com/calendar/item/12345"

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "/me/events/event-123-abc" in call_args[0][0]

    def test_msgraph_get_event_not_found(self, mock_context):
        """Test handling of event not found error."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphNotFoundError("Event not found")
            mock_get_client.return_value = mock_client

            result = msgraph_get_event(mock_context, "nonexistent-event-id")

            assert result["success"] is False
            assert "error" in result
            assert result["error_type"] == "not_found"
            assert "not found" in result["error"].lower()

    def test_msgraph_create_event(self, mock_context):
        """Test creating a basic calendar event."""
        created_event = {
            "id": "new-event-789",
            "subject": "New Meeting",
            "webLink": "https://outlook.office.com/calendar/item/new-event-789",
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_event
            mock_get_client.return_value = mock_client

            result = msgraph_create_event(
                mock_context,
                subject="New Meeting",
                start="2025-12-20T10:00:00",
                end="2025-12-20T11:00:00",
            )

            assert result["success"] is True
            assert "event" in result
            assert result["event"]["id"] == "new-event-789"
            assert result["event"]["subject"] == "New Meeting"
            assert (
                result["event"]["web_link"]
                == "https://outlook.office.com/calendar/item/new-event-789"
            )

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/calendar/events"

            payload = call_args[1]["json"]
            assert payload["subject"] == "New Meeting"
            assert payload["start"]["dateTime"] == "2025-12-20T10:00:00"
            assert payload["end"]["dateTime"] == "2025-12-20T11:00:00"

    def test_msgraph_create_event_with_attendees(self, mock_context):
        """Test creating an event with attendees."""
        created_event = {
            "id": "event-with-attendees",
            "subject": "Team Meeting",
            "webLink": "https://outlook.office.com/calendar/item/event-with-attendees",
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_event
            mock_get_client.return_value = mock_client

            attendees = [
                "alice.johnson@walmart.com",
                "bob.williams@walmart.com",
            ]

            result = msgraph_create_event(
                mock_context,
                subject="Team Meeting",
                start="2025-12-20T10:00:00",
                end="2025-12-20T11:00:00",
                attendees=attendees,
                body="Discuss Q1 planning",
                location="Conference Room B",
            )

            assert result["success"] is True

            # Verify payload structure
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            # Check attendees
            assert "attendees" in payload
            assert len(payload["attendees"]) == 2
            attendee_emails = [
                a["emailAddress"]["address"] for a in payload["attendees"]
            ]
            assert "alice.johnson@walmart.com" in attendee_emails
            assert "bob.williams@walmart.com" in attendee_emails

            # Check body
            assert payload["body"]["content"] == "Discuss Q1 planning"
            assert payload["body"]["contentType"] == "Text"

            # Check location
            assert payload["location"]["displayName"] == "Conference Room B"

    def test_msgraph_create_event_teams_meeting(self, mock_context):
        """Test creating an event with Teams meeting."""
        created_event = {
            "id": "teams-meeting-event",
            "subject": "Virtual Standup",
            "webLink": "https://outlook.office.com/calendar/item/teams-meeting",
            "onlineMeeting": {
                "joinUrl": "https://teams.microsoft.com/l/meetup-join/67890",
            },
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = created_event
            mock_get_client.return_value = mock_client

            result = msgraph_create_event(
                mock_context,
                subject="Virtual Standup",
                start="2025-12-20T09:00:00",
                end="2025-12-20T09:30:00",
                is_online_meeting=True,
            )

            assert result["success"] is True
            assert "teams_link" in result["event"]
            assert (
                result["event"]["teams_link"]
                == "https://teams.microsoft.com/l/meetup-join/67890"
            )

            # Verify online meeting fields in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["isOnlineMeeting"] is True
            assert payload["onlineMeetingProvider"] == "teamsForBusiness"

    def test_msgraph_create_event_auth_error(self, mock_context):
        """Test handling of authentication error when creating event."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_create_event(
                mock_context,
                subject="Test Event",
                start="2025-12-20T10:00:00",
                end="2025-12-20T11:00:00",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_update_event(self, mock_context, mock_event_full_data):
        """Test updating an existing event."""
        updated_event = mock_event_full_data.copy()
        updated_event["subject"] = "Updated Standup"

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = updated_event
            mock_get_client.return_value = mock_client

            result = msgraph_update_event(
                mock_context,
                event_id="event-123-abc",
                subject="Updated Standup",
            )

            assert result["success"] is True
            assert result["event"]["subject"] == "Updated Standup"

            # Verify PATCH was called
            mock_client.patch.assert_called_once()
            call_args = mock_client.patch.call_args
            assert "/me/events/event-123-abc" in call_args[0][0]
            assert call_args[1]["json"]["subject"] == "Updated Standup"

    def test_msgraph_update_event_multiple_fields(
        self, mock_context, mock_event_full_data
    ):
        """Test updating multiple event fields."""
        updated_event = mock_event_full_data.copy()
        updated_event["subject"] = "New Subject"

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.return_value = updated_event
            mock_get_client.return_value = mock_client

            result = msgraph_update_event(
                mock_context,
                event_id="event-123-abc",
                subject="New Subject",
                start="2025-12-20T14:00:00",
                end="2025-12-20T15:00:00",
                body="Updated description",
                location="New Room",
            )

            assert result["success"] is True

            # Verify all fields in payload
            call_args = mock_client.patch.call_args
            payload = call_args[1]["json"]
            assert payload["subject"] == "New Subject"
            assert payload["start"]["dateTime"] == "2025-12-20T14:00:00"
            assert payload["end"]["dateTime"] == "2025-12-20T15:00:00"
            assert payload["body"]["content"] == "Updated description"
            assert payload["location"]["displayName"] == "New Room"

    def test_msgraph_update_event_no_fields_provided(self, mock_context):
        """Test updating event with no fields returns validation error."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            result = msgraph_update_event(
                mock_context,
                event_id="event-123-abc",
                # No fields provided
            )

            assert result["success"] is False
            assert result["error_type"] == "validation"
            assert "No fields provided" in result["error"]

            # Verify no API call was made
            mock_client.patch.assert_not_called()

    def test_msgraph_update_event_not_found(self, mock_context):
        """Test updating a non-existent event."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.patch.side_effect = MSGraphNotFoundError("Event not found")
            mock_get_client.return_value = mock_client

            result = msgraph_update_event(
                mock_context,
                event_id="nonexistent-event",
                subject="New Subject",
            )

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_delete_event(self, mock_context):
        """Test deleting an event."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.return_value = None  # DELETE returns 204 No Content
            mock_get_client.return_value = mock_client

            result = msgraph_delete_event(mock_context, "event-123-abc")

            assert result["success"] is True
            assert result["message"] == "Event deleted successfully"
            assert result["event_id"] == "event-123-abc"

            # Verify DELETE was called
            mock_client.delete.assert_called_once()
            call_args = mock_client.delete.call_args
            assert call_args[0][0] == "/me/events/event-123-abc"

    def test_msgraph_delete_event_not_found(self, mock_context):
        """Test deleting a non-existent event."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.side_effect = MSGraphNotFoundError("Event not found")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_event(mock_context, "nonexistent-event")

            assert result["success"] is False
            assert result["error_type"] == "not_found"

    def test_msgraph_delete_event_auth_error(self, mock_context):
        """Test handling of authentication error when deleting."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.delete.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_delete_event(mock_context, "event-123")

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_get_availability(self, mock_context, mock_availability_data):
        """Test checking free/busy availability."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = mock_availability_data
            mock_get_client.return_value = mock_client

            emails = ["alice.johnson@walmart.com", "bob.williams@walmart.com"]
            start = "2025-12-18T08:00:00Z"
            end = "2025-12-18T18:00:00Z"

            result = msgraph_get_availability(
                mock_context,
                emails=emails,
                start=start,
                end=end,
            )

            assert result["success"] is True
            assert "schedules" in result
            assert len(result["schedules"]) == 2
            assert result["start"] == start
            assert result["end"] == end
            assert result["interval_minutes"] == 30  # Default

            # Check first schedule
            schedule1 = result["schedules"][0]
            assert schedule1["email"] == "alice.johnson@walmart.com"
            assert schedule1["availability_view"] == "0000222200002222"
            assert len(schedule1["schedule_items"]) == 1
            assert schedule1["schedule_items"][0]["status"] == "busy"

            # Check second schedule
            schedule2 = result["schedules"][1]
            assert schedule2["email"] == "bob.williams@walmart.com"
            assert schedule2["schedule_items"] == []  # No busy time

            # Verify API call
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "/me/calendar/getSchedule"

    def test_msgraph_get_availability_custom_interval(self, mock_context):
        """Test availability check with custom interval."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_get_availability(
                mock_context,
                emails=["user@walmart.com"],
                start="2025-12-18T08:00:00Z",
                end="2025-12-18T18:00:00Z",
                interval_minutes=60,
            )

            assert result["success"] is True
            assert result["interval_minutes"] == 60

            # Verify interval in payload
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["availabilityViewInterval"] == 60

    def test_msgraph_get_availability_auth_error(self, mock_context):
        """Test handling of authentication error when checking availability."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.post.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_get_availability(
                mock_context,
                emails=["user@walmart.com"],
                start="2025-12-18T08:00:00Z",
                end="2025-12-18T18:00:00Z",
            )

            assert result["success"] is False
            assert result["error_type"] == "authentication"

    def test_msgraph_list_calendars(self, mock_context, mock_calendars_data):
        """Test listing calendars."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = mock_calendars_data
            mock_get_client.return_value = mock_client

            result = msgraph_list_calendars(mock_context)

            assert result["success"] is True
            assert "calendars" in result
            assert result["total_count"] == 3
            assert len(result["calendars"]) == 3

            # Check default calendar
            default_cal = result["calendars"][0]
            assert default_cal["id"] == "calendar-default"
            assert default_cal["name"] == "Calendar"
            assert default_cal["is_default"] is True
            assert default_cal["can_edit"] is True
            assert default_cal["can_share"] is True
            assert default_cal["owner"] == "john.doe@walmart.com"

            # Check work calendar
            work_cal = result["calendars"][1]
            assert work_cal["name"] == "Work"
            assert work_cal["color"] == "lightBlue"
            assert work_cal["is_default"] is False

            # Check shared calendar
            shared_cal = result["calendars"][2]
            assert shared_cal["name"] == "Team Calendar"
            assert shared_cal["can_edit"] is False
            assert shared_cal["owner"] == "team.lead@walmart.com"

            # Verify API call
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert call_args[0][0] == "/me/calendars"

    def test_msgraph_list_calendars_empty(self, mock_context):
        """Test listing calendars when user has none (edge case)."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = {"value": []}
            mock_get_client.return_value = mock_client

            result = msgraph_list_calendars(mock_context)

            assert result["success"] is True
            assert result["calendars"] == []
            assert result["total_count"] == 0

    def test_msgraph_list_calendars_auth_error(self, mock_context):
        """Test handling of authentication error when listing calendars."""
        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.side_effect = MSGraphAuthError("Token expired")
            mock_get_client.return_value = mock_client

            result = msgraph_list_calendars(mock_context)

            assert result["success"] is False
            assert result["error_type"] == "authentication"
            assert "Authentication failed" in result["error"]


class TestMSGraphCalendarFormatting:
    """Test suite for calendar data formatting."""

    def test_event_preview_formatting(self, mock_context):
        """Verify event preview fields are properly mapped."""
        raw_event = {
            "value": [
                {
                    "id": "test-event-id",
                    # subject is missing - should default to "(No Subject)"
                    "start": {
                        "dateTime": "2025-12-20T14:00:00",
                        "timeZone": "UTC",
                    },
                    "end": {
                        "dateTime": "2025-12-20T15:00:00",
                        "timeZone": "UTC",
                    },
                    "location": {},  # Empty location
                    "isAllDay": True,
                    "isOnlineMeeting": False,
                    "responseStatus": {
                        "response": "none",
                    },
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = raw_event
            mock_get_client.return_value = mock_client

            result = msgraph_list_events(mock_context)

            event = result["events"][0]
            assert event["id"] == "test-event-id"
            assert event["subject"] == "(No Subject)"
            assert event["start"] == "2025-12-20T14:00:00"
            assert event["is_all_day"] is True
            assert event["location"] is None  # Empty displayName

    def test_full_event_formatting_with_html_body(self, mock_context):
        """Test that HTML body is preserved in full event."""
        html_event = {
            "id": "html-event",
            "subject": "Meeting",
            "start": {"dateTime": "2025-12-20T10:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2025-12-20T11:00:00", "timeZone": "UTC"},
            "location": {},
            "body": {
                "contentType": "html",
                "content": "<html><body><p>Important meeting</p></body></html>",
            },
            "organizer": {
                "emailAddress": {"name": "Org", "address": "org@walmart.com"}
            },
            "attendees": [],
            "isAllDay": False,
            "isCancelled": False,
            "isOnlineMeeting": False,
            "responseStatus": {"response": "accepted"},
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = html_event
            mock_get_client.return_value = mock_client

            result = msgraph_get_event(mock_context, "html-event")

            # Body should be preserved (not stripped like in mail)
            assert (
                "<html>" in result["event"]["body"]
                or "Important meeting" in result["event"]["body"]
            )

    def test_calendar_formatting(self, mock_context):
        """Verify calendar fields are properly mapped."""
        raw_calendars = {
            "value": [
                {
                    "id": "cal-id-123",
                    "name": "My Calendar",
                    "color": "lightPink",
                    "isDefaultCalendar": False,
                    "canEdit": True,
                    "canShare": True,
                    "owner": {
                        "name": "Owner Name",
                        "address": "owner@walmart.com",
                    },
                }
            ]
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = raw_calendars
            mock_get_client.return_value = mock_client

            result = msgraph_list_calendars(mock_context)

            cal = result["calendars"][0]
            assert cal["id"] == "cal-id-123"
            assert cal["name"] == "My Calendar"
            assert cal["color"] == "lightPink"
            assert cal["is_default"] is False
            assert cal["can_edit"] is True
            assert cal["can_share"] is True
            assert cal["owner"] == "owner@walmart.com"

    def test_attendee_formatting(self, mock_context):
        """Test that attendees are properly formatted."""
        event_with_attendees = {
            "id": "event-attendees",
            "subject": "Team Meeting",
            "start": {"dateTime": "2025-12-20T10:00:00", "timeZone": "UTC"},
            "end": {"dateTime": "2025-12-20T11:00:00", "timeZone": "UTC"},
            "location": {},
            "body": {"contentType": "text", "content": ""},
            "organizer": {
                "emailAddress": {
                    "name": "Organizer",
                    "address": "organizer@walmart.com",
                }
            },
            "attendees": [
                {
                    "emailAddress": {
                        "name": "Required Attendee",
                        "address": "required@walmart.com",
                    },
                    "type": "required",
                    "status": {"response": "accepted"},
                },
                {
                    "emailAddress": {
                        "name": "Optional Attendee",
                        "address": "optional@walmart.com",
                    },
                    "type": "optional",
                    "status": {"response": "declined"},
                },
            ],
            "isAllDay": False,
            "isCancelled": False,
            "isOnlineMeeting": False,
            "responseStatus": {"response": "organizer"},
        }

        with patch(
            "code_puppy.tools.msgraph.calendar.get_msgraph_client"
        ) as mock_get_client:
            mock_client = Mock()
            mock_client.get.return_value = event_with_attendees
            mock_get_client.return_value = mock_client

            result = msgraph_get_event(mock_context, "event-attendees")

            attendees = result["event"]["attendees"]
            assert len(attendees) == 2

            assert attendees[0]["name"] == "Required Attendee"
            assert attendees[0]["email"] == "required@walmart.com"
            assert attendees[0]["type"] == "required"
            assert attendees[0]["response"] == "accepted"

            assert attendees[1]["name"] == "Optional Attendee"
            assert attendees[1]["type"] == "optional"
            assert attendees[1]["response"] == "declined"
