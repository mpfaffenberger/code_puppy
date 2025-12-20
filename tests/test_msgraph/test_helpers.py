"""Tests for helper/utility functions in msgraph modules.

These are internal functions that handle datetime formatting,
data normalization, and other utilities.
"""

from unittest.mock import MagicMock, patch


class TestCalendarHelpers:
    """Test helper functions in calendar.py."""

    def test_ensure_utc_format_empty_string(self):
        """Test _ensure_utc_format with empty string."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        result = _ensure_utc_format("")
        assert result == ""

    def test_ensure_utc_format_none(self):
        """Test _ensure_utc_format with None-like empty."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        # Empty string is the only "falsy" value we can pass
        result = _ensure_utc_format("")
        assert result == ""

    def test_ensure_utc_format_already_has_z(self):
        """Test _ensure_utc_format when string already has Z."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        result = _ensure_utc_format("2025-12-18T10:00:00Z")
        assert result == "2025-12-18T10:00:00Z"

    def test_ensure_utc_format_has_plus_offset(self):
        """Test _ensure_utc_format when string has + timezone offset."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        result = _ensure_utc_format("2025-12-18T10:00:00+05:00")
        assert result == "2025-12-18T10:00:00+05:00"

    def test_ensure_utc_format_has_minus_offset(self):
        """Test _ensure_utc_format when string has - timezone offset."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        result = _ensure_utc_format("2025-12-18T10:00:00-08:00")
        assert result == "2025-12-18T10:00:00-08:00"

    def test_ensure_utc_format_no_timezone(self):
        """Test _ensure_utc_format adds Z when no timezone."""
        from code_puppy.tools.msgraph.calendar import _ensure_utc_format

        result = _ensure_utc_format("2025-12-18T10:00:00")
        assert result == "2025-12-18T10:00:00Z"

    def test_format_datetime_for_graph_basic(self):
        """Test _format_datetime_for_graph basic formatting."""
        from code_puppy.tools.msgraph.calendar import _format_datetime_for_graph

        result = _format_datetime_for_graph("2025-12-18T10:00:00Z")
        assert result["dateTime"] == "2025-12-18T10:00:00"
        assert result["timeZone"] == "UTC"

    def test_format_datetime_for_graph_with_offset(self):
        """Test _format_datetime_for_graph with timezone offset."""
        from code_puppy.tools.msgraph.calendar import _format_datetime_for_graph

        result = _format_datetime_for_graph("2025-12-18T10:00:00+05:00")
        assert result["dateTime"] == "2025-12-18T10:00:00"


class TestMailHelpers:
    """Test helper functions in mail.py."""

    def test_format_email_address(self):
        """Test email address formatting."""
        # Import any helper if available
        pass  # mail.py doesn't have exposed helpers


class TestPresenceHelpers:
    """Test presence.py tools with proper mocking."""

    @patch("code_puppy.tools.msgraph.presence.get_msgraph_client")
    def test_get_my_presence_success(self, mock_client_fn):
        """Test getting my presence successfully."""
        from code_puppy.tools.msgraph.presence import msgraph_get_my_presence

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "availability": "Available",
            "activity": "Available",
        }

        mock_context = MagicMock()
        result = msgraph_get_my_presence(mock_context)

        assert result["success"] is True
        assert result["presence"]["availability"] == "Available"

    @patch("code_puppy.tools.msgraph.presence.get_msgraph_client")
    def test_get_user_presence_success(self, mock_client_fn):
        """Test getting another user's presence."""
        from code_puppy.tools.msgraph.presence import msgraph_get_user_presence

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "availability": "Busy",
            "activity": "InAMeeting",
        }

        mock_context = MagicMock()
        result = msgraph_get_user_presence(mock_context, user_id="user-123")

        assert result["success"] is True
        assert result["presence"]["availability"] == "Busy"


class TestCalendarAttendeeHelpers:
    """Test calendar_attendees.py edge cases."""

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_add_event_attendees_success(self, mock_client_fn):
        """Test adding attendees to an event."""
        from code_puppy.tools.msgraph.calendar_attendees import (
            msgraph_add_event_attendees,
        )

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "event-123",
            "subject": "Test Meeting",
            "attendees": [],
        }
        mock_client.patch.return_value = {
            "id": "event-123",
            "attendees": [{"emailAddress": {"address": "new@walmart.com"}}],
        }

        mock_context = MagicMock()
        result = msgraph_add_event_attendees(
            mock_context,
            event_id="event-123",
            attendees=["new@walmart.com"],
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_remove_event_attendee_success(self, mock_client_fn):
        """Test removing an attendee from an event."""
        from code_puppy.tools.msgraph.calendar_attendees import (
            msgraph_remove_event_attendee,
        )

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "event-123",
            "subject": "Test Meeting",
            "attendees": [
                {"emailAddress": {"address": "keep@walmart.com"}},
                {"emailAddress": {"address": "remove@walmart.com"}},
            ],
        }
        mock_client.patch.return_value = {
            "id": "event-123",
            "attendees": [
                {"emailAddress": {"address": "keep@walmart.com"}},
            ],
        }

        mock_context = MagicMock()
        result = msgraph_remove_event_attendee(
            mock_context,
            event_id="event-123",
            attendee_email="remove@walmart.com",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_search_events_success(self, mock_client_fn):
        """Test searching for events."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_search_events

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Team Standup",
                    "start": {"dateTime": "2025-12-18T10:00:00"},
                    "end": {"dateTime": "2025-12-18T10:30:00"},
                },
            ]
        }

        mock_context = MagicMock()
        result = msgraph_search_events(
            mock_context,
            query="Standup",
        )

        assert result["success"] is True
        assert len(result["events"]) == 1

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_respond_to_event_accept(self, mock_client_fn):
        """Test responding to an event invitation."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_respond_to_event

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {}

        mock_context = MagicMock()
        result = msgraph_respond_to_event(
            mock_context,
            event_id="event-123",
            response="accept",
        )

        assert result["success"] is True


class TestCalendarSharedHelpers:
    """Test calendar_shared.py edge cases."""

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_get_user_calendar_events_success(self, mock_client_fn):
        """Test getting another user's calendar events."""
        from code_puppy.tools.msgraph.calendar_shared import (
            msgraph_get_user_calendar_events,
        )

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "User's Meeting",
                    "start": {"dateTime": "2025-12-18T10:00:00"},
                },
            ]
        }

        mock_context = MagicMock()
        result = msgraph_get_user_calendar_events(
            mock_context,
            user_email="user@walmart.com",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_get_schedule_success(self, mock_client_fn):
        """Test getting schedule availability."""
        from code_puppy.tools.msgraph.calendar_shared import msgraph_get_schedule

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {
            "value": [
                {
                    "scheduleId": "user@walmart.com",
                    "availabilityView": "0000000000",
                    "scheduleItems": [],
                }
            ]
        }

        mock_context = MagicMock()
        result = msgraph_get_schedule(
            mock_context,
            schedules=["user@walmart.com"],
            start_time="2025-12-18T08:00:00Z",
            end_time="2025-12-18T18:00:00Z",
        )

        assert result["success"] is True


class TestMailExtendedHelpers:
    """Test mail_extended.py edge cases."""

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_move_message_success(self, mock_client_fn):
        """Test moving a message to a folder."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_move_message

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {
            "id": "new-msg-id",
            "parentFolderId": "target-folder",
        }

        mock_context = MagicMock()
        result = msgraph_move_message(
            mock_context,
            message_id="msg-123",
            destination_folder="folder-456",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_archive_message_success(self, mock_client_fn):
        """Test archiving a message."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_archive_message

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        # First call gets archive folder, second moves message
        mock_client.get.return_value = {
            "value": [{"id": "archive-folder-id", "displayName": "Archive"}]
        }
        mock_client.post.return_value = {"id": "archived-msg"}

        mock_context = MagicMock()
        result = msgraph_archive_message(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_mark_as_read_success(self, mock_client_fn):
        """Test marking a message as read."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_mark_as_read

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.patch.return_value = {"isRead": True}

        mock_context = MagicMock()
        result = msgraph_mark_as_read(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_mark_as_unread_success(self, mock_client_fn):
        """Test marking a message as unread."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_mark_as_unread

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.patch.return_value = {"isRead": False}

        mock_context = MagicMock()
        result = msgraph_mark_as_unread(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_forward_message_success(self, mock_client_fn):
        """Test forwarding a message."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_forward_message

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {}

        mock_context = MagicMock()
        result = msgraph_forward_message(
            mock_context,
            message_id="msg-123",
            to_recipients=["recipient@walmart.com"],
            comment="FYI",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_delete_message_success(self, mock_client_fn):
        """Test deleting a message."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_delete_message

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.delete.return_value = {}

        mock_context = MagicMock()
        result = msgraph_delete_message(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_list_attachments_success(self, mock_client_fn):
        """Test listing message attachments."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_list_attachments

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "value": [
                {"id": "att-1", "name": "document.pdf", "size": 1024},
            ]
        }

        mock_context = MagicMock()
        result = msgraph_list_attachments(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is True
        assert len(result["attachments"]) == 1

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_get_attachment_success(self, mock_client_fn):
        """Test getting a specific attachment."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_get_attachment

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "att-1",
            "name": "document.pdf",
            "contentBytes": "base64content",
        }

        mock_context = MagicMock()
        result = msgraph_get_attachment(
            mock_context,
            message_id="msg-123",
            attachment_id="att-1",
        )

        assert result["success"] is True
