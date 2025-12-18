"""Tests for error handling paths in msgraph modules.

These tests cover exception handling and error conditions to achieve 100% coverage.
"""

from unittest.mock import MagicMock, patch
from code_puppy.tools.msgraph.common import MSGraphAuthError


class TestCalendarAttendeeErrors:
    """Test error paths in calendar_attendees.py."""

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_add_event_attendees_error(self, mock_client_fn):
        """Test adding attendees when API fails."""
        from code_puppy.tools.msgraph.calendar_attendees import (
            msgraph_add_event_attendees,
        )

        mock_client_fn.side_effect = MSGraphAuthError("Auth failed")

        mock_context = MagicMock()
        result = msgraph_add_event_attendees(
            mock_context,
            event_id="event-123",
            attendees=["new@walmart.com"],
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_remove_event_attendee_error(self, mock_client_fn):
        """Test removing attendee when API fails."""
        from code_puppy.tools.msgraph.calendar_attendees import (
            msgraph_remove_event_attendee,
        )

        mock_client_fn.side_effect = Exception("Network error")

        mock_context = MagicMock()
        result = msgraph_remove_event_attendee(
            mock_context,
            event_id="event-123",
            attendee_email="remove@walmart.com",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_search_events_error(self, mock_client_fn):
        """Test searching events when API fails."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_search_events

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_search_events(
            mock_context,
            query="test",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_attendees.get_msgraph_client")
    def test_respond_to_event_error(self, mock_client_fn):
        """Test responding to event when API fails."""
        from code_puppy.tools.msgraph.calendar_attendees import msgraph_respond_to_event

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_respond_to_event(
            mock_context,
            event_id="event-123",
            response="accept",
        )

        assert result["success"] is False


class TestCalendarSharedErrors:
    """Test error paths in calendar_shared.py."""

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_list_shared_calendars_error(self, mock_client_fn):
        """Test listing shared calendars when API fails."""
        from code_puppy.tools.msgraph.calendar_shared import (
            msgraph_list_shared_calendars,
        )

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_shared_calendars(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_get_user_calendar_events_error(self, mock_client_fn):
        """Test getting user calendar when API fails."""
        from code_puppy.tools.msgraph.calendar_shared import (
            msgraph_get_user_calendar_events,
        )

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_user_calendar_events(
            mock_context,
            user_email="user@walmart.com",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_find_meeting_times_error(self, mock_client_fn):
        """Test finding meeting times when API fails."""
        from code_puppy.tools.msgraph.calendar_shared import msgraph_find_meeting_times

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_find_meeting_times(
            mock_context,
            attendees=["user@walmart.com"],
            duration_minutes=30,
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar_shared.get_msgraph_client")
    def test_get_schedule_error(self, mock_client_fn):
        """Test getting schedule when API fails."""
        from code_puppy.tools.msgraph.calendar_shared import msgraph_get_schedule

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_schedule(
            mock_context,
            schedules=["user@walmart.com"],
            start_time="2025-12-18T08:00:00Z",
            end_time="2025-12-18T18:00:00Z",
        )

        assert result["success"] is False


class TestMailExtendedErrors:
    """Test error paths in mail_extended.py."""

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_move_message_error(self, mock_client_fn):
        """Test moving message when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_move_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_move_message(
            mock_context,
            message_id="msg-123",
            destination_folder="archive",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_archive_message_error(self, mock_client_fn):
        """Test archiving message when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_archive_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_archive_message(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_mark_as_read_error(self, mock_client_fn):
        """Test marking as read when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_mark_as_read

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_mark_as_read(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_mark_as_unread_error(self, mock_client_fn):
        """Test marking as unread when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_mark_as_unread

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_mark_as_unread(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_forward_message_error(self, mock_client_fn):
        """Test forwarding message when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_forward_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_forward_message(
            mock_context,
            message_id="msg-123",
            to_recipients=["user@walmart.com"],
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_delete_message_error(self, mock_client_fn):
        """Test deleting message when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_delete_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_message(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_list_attachments_error(self, mock_client_fn):
        """Test listing attachments when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_list_attachments

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_attachments(
            mock_context,
            message_id="msg-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail_extended.get_msgraph_client")
    def test_get_attachment_error(self, mock_client_fn):
        """Test getting attachment when API fails."""
        from code_puppy.tools.msgraph.mail_extended import msgraph_get_attachment

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_attachment(
            mock_context,
            message_id="msg-123",
            attachment_id="att-1",
        )

        assert result["success"] is False


class TestPresenceErrors:
    """Test error paths in presence.py."""

    @patch("code_puppy.tools.msgraph.presence.get_msgraph_client")
    def test_get_my_presence_error(self, mock_client_fn):
        """Test getting my presence when API fails."""
        from code_puppy.tools.msgraph.presence import msgraph_get_my_presence

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_my_presence(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.presence.get_msgraph_client")
    def test_get_user_presence_error(self, mock_client_fn):
        """Test getting user presence when API fails."""
        from code_puppy.tools.msgraph.presence import msgraph_get_user_presence

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_user_presence(
            mock_context,
            user_id="user-123",
        )

        assert result["success"] is False


class TestTodoErrors:
    """Test error paths in todo.py."""

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_list_todo_lists_error(self, mock_client_fn):
        """Test listing todo lists when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_list_todo_lists

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_todo_lists(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_get_todo_list_error(self, mock_client_fn):
        """Test getting todo list when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_get_todo_list

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_todo_list(mock_context, list_id="list-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_create_todo_list_error(self, mock_client_fn):
        """Test creating todo list when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_create_todo_list

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_create_todo_list(mock_context, display_name="Test List")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_delete_todo_list_error(self, mock_client_fn):
        """Test deleting todo list when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_delete_todo_list

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_todo_list(mock_context, list_id="list-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_list_todo_tasks_error(self, mock_client_fn):
        """Test listing tasks when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_list_todo_tasks

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_todo_tasks(mock_context, list_id="list-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_get_todo_task_error(self, mock_client_fn):
        """Test getting task when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_get_todo_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_todo_task(
            mock_context,
            list_id="list-123",
            task_id="task-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_create_todo_task_error(self, mock_client_fn):
        """Test creating task when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_create_todo_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_create_todo_task(
            mock_context,
            list_id="list-123",
            title="Test Task",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_update_todo_task_error(self, mock_client_fn):
        """Test updating task when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_update_todo_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_update_todo_task(
            mock_context,
            list_id="list-123",
            task_id="task-123",
            title="Updated",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_complete_todo_task_error(self, mock_client_fn):
        """Test completing task when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_complete_todo_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_complete_todo_task(
            mock_context,
            list_id="list-123",
            task_id="task-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.todo.get_msgraph_client")
    def test_delete_todo_task_error(self, mock_client_fn):
        """Test deleting task when API fails."""
        from code_puppy.tools.msgraph.todo import msgraph_delete_todo_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_todo_task(
            mock_context,
            list_id="list-123",
            task_id="task-123",
        )

        assert result["success"] is False


class TestUsersErrors:
    """Test error paths in users.py."""

    @patch("code_puppy.tools.msgraph.users.get_msgraph_client")
    def test_get_me_error(self, mock_client_fn):
        """Test getting my profile when API fails."""
        from code_puppy.tools.msgraph.users import msgraph_get_me

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_me(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.users.get_msgraph_client")
    def test_get_user_error(self, mock_client_fn):
        """Test getting user when API fails."""
        from code_puppy.tools.msgraph.users import msgraph_get_user

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_user(mock_context, user_id="user-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.users.get_msgraph_client")
    def test_search_users_error(self, mock_client_fn):
        """Test searching users when API fails."""
        from code_puppy.tools.msgraph.users import msgraph_search_users

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_search_users(mock_context, query="test")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.users.get_msgraph_client")
    def test_get_manager_error(self, mock_client_fn):
        """Test getting manager when API fails."""
        from code_puppy.tools.msgraph.users import msgraph_get_manager

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_manager(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.users.get_msgraph_client")
    def test_get_direct_reports_error(self, mock_client_fn):
        """Test getting direct reports when API fails."""
        from code_puppy.tools.msgraph.users import msgraph_get_direct_reports

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_direct_reports(mock_context)

        assert result["success"] is False


class TestTeamsErrors:
    """Test error paths in teams.py."""

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_teams_error(self, mock_client_fn):
        """Test listing teams when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_list_teams

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_teams(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channels_error(self, mock_client_fn):
        """Test listing channels when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_list_channels

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_channels(mock_context, team_id="team-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_channel_messages_error(self, mock_client_fn):
        """Test listing messages when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_list_channel_messages

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_channel_messages(
            mock_context,
            team_id="team-123",
            channel_id="channel-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_channel_message_error(self, mock_client_fn):
        """Test sending channel message when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_send_channel_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_send_channel_message(
            mock_context,
            team_id="team-123",
            channel_id="channel-123",
            content="Test message",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_list_chats_error(self, mock_client_fn):
        """Test listing chats when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_list_chats

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_chats(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_chat_message_error(self, mock_client_fn):
        """Test sending chat message when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_send_chat_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_send_chat_message(
            mock_context,
            chat_id="chat-123",
            content="Test message",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_send_direct_message_error(self, mock_client_fn):
        """Test sending direct message when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_send_direct_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_send_direct_message(
            mock_context,
            user_email="user@walmart.com",
            content="Test message",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.teams.get_msgraph_client")
    def test_create_online_meeting_error(self, mock_client_fn):
        """Test creating online meeting when API fails."""
        from code_puppy.tools.msgraph.teams import msgraph_create_online_meeting

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_create_online_meeting(
            mock_context,
            subject="Test Meeting",
            start="2025-12-18T10:00:00Z",
            end="2025-12-18T11:00:00Z",
        )

        assert result["success"] is False


class TestOneDriveErrors:
    """Test error paths in onedrive.py."""

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_list_drive_items_error(self, mock_client_fn):
        """Test listing drive items when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_list_drive_items

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_drive_items(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_get_drive_item_error(self, mock_client_fn):
        """Test getting drive item when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_get_drive_item

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_drive_item(mock_context, item_id="file-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_download_file_error(self, mock_client_fn):
        """Test downloading file when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_download_file

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_download_file(mock_context, item_id="file-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_search_files_error(self, mock_client_fn):
        """Test searching files when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_search_files

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_search_files(mock_context, query="test")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_create_folder_error(self, mock_client_fn):
        """Test creating folder when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_create_folder

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_create_folder(mock_context, path="/", name="Test Folder")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_delete_drive_item_error(self, mock_client_fn):
        """Test deleting drive item when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_delete_drive_item

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_drive_item(mock_context, item_id="file-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_share_file_error(self, mock_client_fn):
        """Test sharing file when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_share_file

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_share_file(mock_context, item_id="file-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.onedrive.get_msgraph_client")
    def test_upload_file_error(self, mock_client_fn):
        """Test uploading file when API fails."""
        from code_puppy.tools.msgraph.onedrive import msgraph_upload_file

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_upload_file(
            mock_context,
            path="/Documents/test.txt",
            content="Test content",
        )

        assert result["success"] is False


class TestPlannerErrors:
    """Test error paths in planner.py."""

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_list_plans_error(self, mock_client_fn):
        """Test listing plans when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_list_plans

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_plans(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_get_plan_error(self, mock_client_fn):
        """Test getting plan when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_get_plan

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_plan(mock_context, plan_id="plan-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_list_buckets_error(self, mock_client_fn):
        """Test listing buckets when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_list_buckets

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_buckets(mock_context, plan_id="plan-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_list_tasks_error(self, mock_client_fn):
        """Test listing tasks when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_list_tasks

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_list_tasks(mock_context, plan_id="plan-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_get_task_error(self, mock_client_fn):
        """Test getting task when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_get_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_task(mock_context, task_id="task-123")

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_create_task_error(self, mock_client_fn):
        """Test creating task when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_create_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_create_task(
            mock_context,
            plan_id="plan-123",
            bucket_id="bucket-123",
            title="Test Task",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_update_task_error(self, mock_client_fn):
        """Test updating task when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_update_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_update_task(
            mock_context,
            task_id="task-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.planner.get_msgraph_client")
    def test_delete_task_error(self, mock_client_fn):
        """Test deleting task when API fails."""
        from code_puppy.tools.msgraph.planner import msgraph_delete_task

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_task(mock_context, task_id="task-123")

        assert result["success"] is False


class TestCalendarErrors:
    """Test error paths in calendar.py."""

    @patch("code_puppy.tools.msgraph.calendar.get_msgraph_client")
    def test_delete_event_error(self, mock_client_fn):
        """Test deleting event when API fails."""
        from code_puppy.tools.msgraph.calendar import msgraph_delete_event

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_delete_event(mock_context, event_id="event-123")

        assert result["success"] is False


class TestMailErrors:
    """Test error paths in mail.py."""

    @patch("code_puppy.tools.msgraph.mail.get_msgraph_client")
    def test_reply_to_message_error(self, mock_client_fn):
        """Test replying to message when API fails."""
        from code_puppy.tools.msgraph.mail import msgraph_reply_to_message

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_reply_to_message(
            mock_context,
            message_id="msg-123",
            body="Reply text",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.mail.get_msgraph_client")
    def test_search_mail_error(self, mock_client_fn):
        """Test searching mail when API fails."""
        from code_puppy.tools.msgraph.mail import msgraph_search_mail

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_search_mail(mock_context, query="test")

        assert result["success"] is False


class TestWorkflowErrors:
    """Test error paths in workflows.py."""

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_prepare_meeting_brief_error(self, mock_client_fn):
        """Test meeting brief when API fails."""
        from code_puppy.tools.msgraph.workflows import msgraph_prepare_meeting_brief

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_prepare_meeting_brief(
            mock_context,
            event_id="event-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_daily_digest_error(self, mock_client_fn):
        """Test daily digest when API fails."""
        from code_puppy.tools.msgraph.workflows import msgraph_daily_digest

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_daily_digest(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows.get_msgraph_client")
    def test_smart_schedule_error(self, mock_client_fn):
        """Test smart schedule when API fails."""
        from code_puppy.tools.msgraph.workflows import msgraph_smart_schedule

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_smart_schedule(
            mock_context,
            subject="Test Meeting",
            duration_minutes=30,
            attendees=["user@walmart.com"],
        )

        assert result["success"] is False


class TestWorkflowMeetingErrors:
    """Test error paths in workflows_meeting.py."""

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_email_meeting_attendees_error(self, mock_client_fn):
        """Test emailing attendees when API fails."""
        from code_puppy.tools.msgraph.workflows_meeting import (
            msgraph_email_meeting_attendees,
        )

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_email_meeting_attendees(
            mock_context,
            event_id="event-123",
            email_subject="Update",
            email_body="Meeting update",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_meeting.get_msgraph_client")
    def test_nudge_non_responders_error(self, mock_client_fn):
        """Test nudging when API fails."""
        from code_puppy.tools.msgraph.workflows_meeting import (
            msgraph_nudge_non_responders,
        )

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_nudge_non_responders(
            mock_context,
            event_id="event-123",
            email_subject="Reminder",
            email_body="Please respond",
        )

        assert result["success"] is False


class TestWorkflowEaErrors:
    """Test error paths in workflows_ea.py."""

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_prep_one_on_one_error(self, mock_client_fn):
        """Test one-on-one prep when API fails."""
        from code_puppy.tools.msgraph.workflows_ea import msgraph_prep_one_on_one

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_prep_one_on_one(
            mock_context,
            manager_email="user@walmart.com",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_standup_prep_error(self, mock_client_fn):
        """Test standup prep when API fails."""
        from code_puppy.tools.msgraph.workflows_ea import msgraph_standup_prep

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_standup_prep(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.workflows_ea.get_msgraph_client")
    def test_performance_summary_error(self, mock_client_fn):
        """Test performance summary when API fails."""
        from code_puppy.tools.msgraph.workflows_ea import msgraph_performance_summary

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_performance_summary(mock_context)

        assert result["success"] is False


class TestMeetingHealthErrors:
    """Test error paths in meeting_health.py.

    Note: These functions use calendar helpers which call get_msgraph_client
    internally, so we mock at the calendar level.
    """

    @patch("code_puppy.tools.msgraph.meeting_health.get_msgraph_client")
    def test_analyze_meeting_health_error(self, mock_client_fn):
        """Test analyzing meeting when not authenticated."""
        from code_puppy.tools.msgraph.meeting_health import (
            msgraph_analyze_meeting_health,
        )

        # Simulate not being authenticated
        mock_client_fn.return_value = None

        mock_context = MagicMock()
        result = msgraph_analyze_meeting_health(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar.get_msgraph_client")
    def test_get_meeting_responses_error(self, mock_client_fn):
        """Test getting responses when API fails."""
        from code_puppy.tools.msgraph.meeting_health import (
            msgraph_get_meeting_responses,
        )

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_get_meeting_responses(
            mock_context,
            event_id="event-123",
        )

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.meeting_health.get_msgraph_client")
    def test_find_pending_rsvps_error(self, mock_client_fn):
        """Test finding pending RSVPs when not authenticated."""
        from code_puppy.tools.msgraph.meeting_health import msgraph_find_pending_rsvps

        # Simulate not being authenticated
        mock_client_fn.return_value = None

        mock_context = MagicMock()
        result = msgraph_find_pending_rsvps(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.meeting_health.get_msgraph_client")
    def test_find_my_pending_responses_error(self, mock_client_fn):
        """Test finding my pending when not authenticated."""
        from code_puppy.tools.msgraph.meeting_health import (
            msgraph_find_my_pending_responses,
        )

        # Simulate not being authenticated
        mock_client_fn.return_value = None

        mock_context = MagicMock()
        result = msgraph_find_my_pending_responses(mock_context)

        assert result["success"] is False

    @patch("code_puppy.tools.msgraph.calendar.get_msgraph_client")
    def test_suggest_reschedule_error(self, mock_client_fn):
        """Test suggesting reschedule when API fails."""
        from code_puppy.tools.msgraph.meeting_health import msgraph_suggest_reschedule

        mock_client_fn.side_effect = Exception("API error")

        mock_context = MagicMock()
        result = msgraph_suggest_reschedule(
            mock_context,
            event_id="event-123",
        )

        assert result["success"] is False
