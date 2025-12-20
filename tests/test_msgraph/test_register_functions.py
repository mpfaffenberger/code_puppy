"""Tests for all register_* functions in msgraph module.

These are boilerplate functions that register tools with PydanticAI agents.
We test them all in one place to ensure 100% coverage.

Note: Some register functions use agent.tool(func) and some use agent.tool()(func).
We handle both patterns in the tests.
"""

from unittest.mock import MagicMock


def make_mock_agent_decorator_style():
    """Create mock agent for decorator-style: agent.tool()(func)."""
    mock_agent = MagicMock()
    mock_tool_decorator = MagicMock()
    mock_tool = MagicMock()
    mock_tool_decorator.return_value = mock_tool
    mock_agent.tool.return_value = mock_tool_decorator
    return mock_agent


def make_mock_agent_direct_style():
    """Create mock agent for direct-style: agent.tool(func)."""
    mock_agent = MagicMock()
    mock_tool = MagicMock()
    mock_agent.tool.return_value = mock_tool
    return mock_agent


class TestCalendarRegisterFunctions:
    """Test register functions in calendar.py."""

    def test_register_msgraph_list_events(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_list_events,
            msgraph_list_events,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_events(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_events)

    def test_register_msgraph_get_event(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_get_event,
            msgraph_get_event,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_get_event(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_get_event)

    def test_register_msgraph_create_event(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_create_event,
            msgraph_create_event,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_create_event(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_create_event)

    def test_register_msgraph_update_event(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_update_event,
            msgraph_update_event,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_update_event(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_update_event)

    def test_register_msgraph_delete_event(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_delete_event,
            msgraph_delete_event,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_delete_event(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_delete_event)

    def test_register_msgraph_get_availability(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_get_availability,
            msgraph_get_availability,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_get_availability(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_get_availability)

    def test_register_msgraph_list_calendars(self):
        from code_puppy.tools.msgraph.calendar import (
            register_msgraph_list_calendars,
            msgraph_list_calendars,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_calendars(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_calendars)


class TestCalendarAttendeesRegisterFunctions:
    """Test register functions in calendar_attendees.py (uses decorator style)."""

    def test_register_msgraph_add_event_attendees(self):
        from code_puppy.tools.msgraph.calendar_attendees import (
            register_msgraph_add_event_attendees,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_add_event_attendees(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_remove_event_attendee(self):
        from code_puppy.tools.msgraph.calendar_attendees import (
            register_msgraph_remove_event_attendee,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_remove_event_attendee(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_search_events(self):
        from code_puppy.tools.msgraph.calendar_attendees import (
            register_msgraph_search_events,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_search_events(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_respond_to_event(self):
        from code_puppy.tools.msgraph.calendar_attendees import (
            register_msgraph_respond_to_event,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_respond_to_event(mock_agent)
        mock_agent.tool.assert_called_once()


class TestCalendarSharedRegisterFunctions:
    """Test register functions in calendar_shared.py (uses decorator style)."""

    def test_register_msgraph_list_shared_calendars(self):
        from code_puppy.tools.msgraph.calendar_shared import (
            register_msgraph_list_shared_calendars,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_list_shared_calendars(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_user_calendar_events(self):
        from code_puppy.tools.msgraph.calendar_shared import (
            register_msgraph_get_user_calendar_events,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_user_calendar_events(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_find_meeting_times(self):
        from code_puppy.tools.msgraph.calendar_shared import (
            register_msgraph_find_meeting_times,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_find_meeting_times(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_schedule(self):
        from code_puppy.tools.msgraph.calendar_shared import (
            register_msgraph_get_schedule,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_schedule(mock_agent)
        mock_agent.tool.assert_called_once()


class TestMailRegisterFunctions:
    """Test register functions in mail.py."""

    def test_register_msgraph_list_messages(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_list_messages,
            msgraph_list_messages,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_messages(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_messages)

    def test_register_msgraph_get_message(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_get_message,
            msgraph_get_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_get_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_get_message)

    def test_register_msgraph_send_mail(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_send_mail,
            msgraph_send_mail,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_send_mail(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_send_mail)

    def test_register_msgraph_reply_to_message(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_reply_to_message,
            msgraph_reply_to_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_reply_to_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_reply_to_message)

    def test_register_msgraph_search_mail(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_search_mail,
            msgraph_search_mail,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_search_mail(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_search_mail)

    def test_register_msgraph_list_mail_folders(self):
        from code_puppy.tools.msgraph.mail import (
            register_msgraph_list_mail_folders,
            msgraph_list_mail_folders,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_mail_folders(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_mail_folders)


class TestMailExtendedRegisterFunctions:
    """Test register functions in mail_extended.py."""

    def test_register_msgraph_move_message(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_move_message,
            msgraph_move_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_move_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_move_message)

    def test_register_msgraph_archive_message(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_archive_message,
            msgraph_archive_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_archive_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_archive_message)

    def test_register_msgraph_mark_as_read(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_mark_as_read,
            msgraph_mark_as_read,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_mark_as_read(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_mark_as_read)

    def test_register_msgraph_mark_as_unread(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_mark_as_unread,
            msgraph_mark_as_unread,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_mark_as_unread(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_mark_as_unread)

    def test_register_msgraph_forward_message(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_forward_message,
            msgraph_forward_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_forward_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_forward_message)

    def test_register_msgraph_delete_message(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_delete_message,
            msgraph_delete_message,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_delete_message(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_delete_message)

    def test_register_msgraph_list_attachments(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_list_attachments,
            msgraph_list_attachments,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_attachments(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_attachments)

    def test_register_msgraph_get_attachment(self):
        from code_puppy.tools.msgraph.mail_extended import (
            register_msgraph_get_attachment,
            msgraph_get_attachment,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_get_attachment(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_get_attachment)


class TestMeetingHealthRegisterFunctions:
    """Test register functions in meeting_health.py (uses decorator style)."""

    def test_register_msgraph_analyze_meeting_health(self):
        from code_puppy.tools.msgraph.meeting_health import (
            register_msgraph_analyze_meeting_health,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_analyze_meeting_health(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_meeting_responses(self):
        from code_puppy.tools.msgraph.meeting_health import (
            register_msgraph_get_meeting_responses,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_meeting_responses(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_find_pending_rsvps(self):
        from code_puppy.tools.msgraph.meeting_health import (
            register_msgraph_find_pending_rsvps,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_find_pending_rsvps(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_find_my_pending_responses(self):
        from code_puppy.tools.msgraph.meeting_health import (
            register_msgraph_find_my_pending_responses,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_find_my_pending_responses(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_suggest_reschedule(self):
        from code_puppy.tools.msgraph.meeting_health import (
            register_msgraph_suggest_reschedule,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_suggest_reschedule(mock_agent)
        mock_agent.tool.assert_called_once()


class TestPresenceRegisterFunctions:
    """Test register functions in presence.py (uses decorator style)."""

    def test_register_msgraph_get_my_presence(self):
        from code_puppy.tools.msgraph.presence import (
            register_msgraph_get_my_presence,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_my_presence(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_user_presence(self):
        from code_puppy.tools.msgraph.presence import (
            register_msgraph_get_user_presence,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_user_presence(mock_agent)
        mock_agent.tool.assert_called_once()


class TestTodoRegisterFunctions:
    """Test register functions in todo.py (uses decorator style)."""

    def test_register_msgraph_list_todo_lists(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_list_todo_lists

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_list_todo_lists(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_todo_list(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_get_todo_list

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_todo_list(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_create_todo_list(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_create_todo_list

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_create_todo_list(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_delete_todo_list(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_delete_todo_list

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_delete_todo_list(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_list_todo_tasks(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_list_todo_tasks

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_list_todo_tasks(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_get_todo_task(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_get_todo_task

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_get_todo_task(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_create_todo_task(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_create_todo_task

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_create_todo_task(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_update_todo_task(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_update_todo_task

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_update_todo_task(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_complete_todo_task(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_complete_todo_task

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_complete_todo_task(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_delete_todo_task(self):
        from code_puppy.tools.msgraph.todo import register_msgraph_delete_todo_task

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_delete_todo_task(mock_agent)
        mock_agent.tool.assert_called_once()


class TestSharepointRegisterFunctions:
    """Test register functions in sharepoint.py."""

    def test_register_msgraph_list_sites(self):
        from code_puppy.tools.msgraph.sharepoint import (
            register_msgraph_list_sites,
            msgraph_list_sites,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_sites(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_sites)

    def test_register_msgraph_get_site(self):
        from code_puppy.tools.msgraph.sharepoint import (
            register_msgraph_get_site,
            msgraph_get_site,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_get_site(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_get_site)

    def test_register_msgraph_list_site_drives(self):
        from code_puppy.tools.msgraph.sharepoint import (
            register_msgraph_list_site_drives,
            msgraph_list_site_drives,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_site_drives(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_site_drives)

    def test_register_msgraph_list_site_items(self):
        from code_puppy.tools.msgraph.sharepoint import (
            register_msgraph_list_site_items,
            msgraph_list_site_items,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_list_site_items(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_list_site_items)

    def test_register_msgraph_search_sharepoint(self):
        from code_puppy.tools.msgraph.sharepoint import (
            register_msgraph_search_sharepoint,
            msgraph_search_sharepoint,
        )

        mock_agent = MagicMock()
        mock_agent.tool.return_value = MagicMock()
        register_msgraph_search_sharepoint(mock_agent)
        mock_agent.tool.assert_called_once_with(msgraph_search_sharepoint)


class TestWorkflowsRegisterFunctions:
    """Test register functions in workflows.py (uses decorator style)."""

    def test_register_msgraph_prepare_meeting_brief(self):
        from code_puppy.tools.msgraph.workflows import (
            register_msgraph_prepare_meeting_brief,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_prepare_meeting_brief(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_daily_digest(self):
        from code_puppy.tools.msgraph.workflows import register_msgraph_daily_digest

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_daily_digest(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_smart_schedule(self):
        from code_puppy.tools.msgraph.workflows import register_msgraph_smart_schedule

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_smart_schedule(mock_agent)
        mock_agent.tool.assert_called_once()


class TestWorkflowsEaRegisterFunctions:
    """Test register functions in workflows_ea.py (uses decorator style)."""

    def test_register_msgraph_prep_one_on_one(self):
        from code_puppy.tools.msgraph.workflows_ea import (
            register_msgraph_prep_one_on_one,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_prep_one_on_one(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_standup_prep(self):
        from code_puppy.tools.msgraph.workflows_ea import register_msgraph_standup_prep

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_standup_prep(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_performance_summary(self):
        from code_puppy.tools.msgraph.workflows_ea import (
            register_msgraph_performance_summary,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_performance_summary(mock_agent)
        mock_agent.tool.assert_called_once()


class TestWorkflowsMeetingRegisterFunctions:
    """Test register functions in workflows_meeting.py (uses decorator style)."""

    def test_register_msgraph_email_meeting_attendees(self):
        from code_puppy.tools.msgraph.workflows_meeting import (
            register_msgraph_email_meeting_attendees,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_email_meeting_attendees(mock_agent)
        mock_agent.tool.assert_called_once()

    def test_register_msgraph_nudge_non_responders(self):
        from code_puppy.tools.msgraph.workflows_meeting import (
            register_msgraph_nudge_non_responders,
        )

        mock_agent = make_mock_agent_decorator_style()
        register_msgraph_nudge_non_responders(mock_agent)
        mock_agent.tool.assert_called_once()
