"""Tests for edge cases in msgraph modules to reach 100% coverage.

These tests target specific branches and edge conditions.
"""

from unittest.mock import MagicMock, patch


class TestCalendarEdgeCases:
    """Test edge cases in calendar.py."""

    @patch("code_puppy.tools.msgraph.calendar.get_msgraph_client")
    def test_get_availability_more_than_3_emails(self, mock_client_fn):
        """Test get_availability with more than 3 emails shows truncated list."""
        from code_puppy.tools.msgraph.calendar import msgraph_get_availability

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {
            "value": [
                {"scheduleId": "user1@walmart.com", "availabilityView": "0000"},
                {"scheduleId": "user2@walmart.com", "availabilityView": "0000"},
                {"scheduleId": "user3@walmart.com", "availabilityView": "0000"},
                {"scheduleId": "user4@walmart.com", "availabilityView": "0000"},
                {"scheduleId": "user5@walmart.com", "availabilityView": "0000"},
            ]
        }

        mock_context = MagicMock()
        result = msgraph_get_availability(
            mock_context,
            emails=[
                "user1@walmart.com",
                "user2@walmart.com",
                "user3@walmart.com",
                "user4@walmart.com",
                "user5@walmart.com",
            ],
            start="2025-12-18T08:00:00Z",
            end="2025-12-18T18:00:00Z",
        )

        assert result["success"] is True


class TestMailEdgeCases:
    """Test edge cases in mail.py."""

    @patch("code_puppy.tools.msgraph.mail.get_msgraph_client")
    def test_list_messages_with_folder(self, mock_client_fn):
        """Test listing messages with a specific folder."""
        from code_puppy.tools.msgraph.mail import msgraph_list_messages

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "value": [
                {
                    "id": "msg-1",
                    "subject": "Test",
                    "from": {"emailAddress": {"address": "sender@walmart.com"}},
                    "receivedDateTime": "2025-12-18T10:00:00Z",
                }
            ]
        }

        mock_context = MagicMock()
        result = msgraph_list_messages(
            mock_context,
            folder="Drafts",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.mail.get_msgraph_client")
    def test_send_mail_with_cc_and_bcc(self, mock_client_fn):
        """Test sending mail with CC and BCC recipients."""
        from code_puppy.tools.msgraph.mail import msgraph_send_mail

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {}

        mock_context = MagicMock()
        result = msgraph_send_mail(
            mock_context,
            to=["recipient@walmart.com"],
            subject="Test",
            body="Test body",
            cc=["cc@walmart.com"],
            bcc=["bcc@walmart.com"],
        )

        assert result["success"] is True


class TestCalendarAttendeesEdgeCases:
    """Test edge cases in calendar_attendees.py."""

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_add_attendees_with_optional_flag(self, mock_client_fn):
        """Test adding optional attendees."""
        from code_puppy.tools.msgraph.calendar_attendees import (
            msgraph_add_event_attendees,
        )

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "event-123",
            "subject": "Meeting",
            "attendees": [],
        }
        mock_client.patch.return_value = {
            "id": "event-123",
            "attendees": [
                {
                    "emailAddress": {"address": "optional@walmart.com"},
                    "type": "optional",
                }
            ],
        }

        mock_context = MagicMock()
        result = msgraph_add_event_attendees(
            mock_context,
            event_id="event-123",
            attendees=["optional@walmart.com"],
            attendee_type="optional",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_search_events_with_date_range(self, mock_client_fn):
        """Test searching events with specific date range."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_search_events

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "value": [
                {
                    "id": "event-1",
                    "subject": "Team Meeting",
                    "start": {"dateTime": "2025-12-18T10:00:00"},
                    "end": {"dateTime": "2025-12-18T11:00:00"},
                }
            ]
        }

        mock_context = MagicMock()
        result = msgraph_search_events(
            mock_context,
            query="Team",
            days_ahead=7,
            days_back=14,
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_respond_to_event_with_message(self, mock_client_fn):
        """Test responding to event with a message."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_respond_to_event

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {}

        mock_context = MagicMock()
        result = msgraph_respond_to_event(
            mock_context,
            event_id="event-123",
            response="tentative",
            comment="I might be late",
        )

        assert result["success"] is True


class TestTodoEdgeCases:
    """Test edge cases in todo.py."""

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_create_task_with_due_date(self, mock_client_fn):
        """Test creating task with due date."""
        from code_puppy.tools.msgraph.todo import msgraph_create_todo_task

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {
            "id": "task-123",
            "title": "Test Task",
            "dueDateTime": {"dateTime": "2025-12-25T00:00:00"},
        }

        mock_context = MagicMock()
        result = msgraph_create_todo_task(
            mock_context,
            list_id="list-123",
            title="Test Task",
            due_date="2025-12-25",
        )

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_update_task_with_importance(self, mock_client_fn):
        """Test updating task with importance."""
        from code_puppy.tools.msgraph.todo import msgraph_update_todo_task

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.patch.return_value = {
            "id": "task-123",
            "title": "Updated Task",
            "importance": "high",
        }

        mock_context = MagicMock()
        result = msgraph_update_todo_task(
            mock_context,
            list_id="list-123",
            task_id="task-123",
            importance="high",
        )

        assert result["success"] is True


class TestCalendarSharedEdgeCases:
    """Test edge cases in calendar_shared.py."""

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_find_meeting_times_with_constraints(self, mock_client_fn):
        """Test finding meeting times with constraints."""
        from code_puppy.tools.msgraph.calendar_shared import msgraph_find_meeting_times

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.post.return_value = {
            "meetingTimeSuggestions": [
                {
                    "confidence": 100,
                    "meetingTimeSlot": {
                        "start": {"dateTime": "2025-12-18T10:00:00"},
                        "end": {"dateTime": "2025-12-18T11:00:00"},
                    },
                }
            ]
        }

        mock_context = MagicMock()
        result = msgraph_find_meeting_times(
            mock_context,
            attendees=["user1@walmart.com", "user2@walmart.com"],
            duration_minutes=60,
            days_ahead=14,
        )

        assert result["success"] is True


class TestTeamsEdgeCases:
    """Test edge cases in teams.py."""

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_team_details(self, mock_client_fn):
        """Test getting team details."""
        from code_puppy.tools.msgraph.teams import msgraph_get_team

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "team-123",
            "displayName": "My Team",
            "description": "Team description",
        }

        mock_context = MagicMock()
        result = msgraph_get_team(mock_context, team_id="team-123")

        assert result["success"] is True

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_get_channel_details(self, mock_client_fn):
        """Test getting channel details."""
        from code_puppy.tools.msgraph.teams import msgraph_get_channel

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.get.return_value = {
            "id": "channel-123",
            "displayName": "General",
            "description": "General channel",
        }

        mock_context = MagicMock()
        result = msgraph_get_channel(
            mock_context,
            team_id="team-123",
            channel_id="channel-123",
        )

        assert result["success"] is True
