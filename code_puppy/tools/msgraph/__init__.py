"""Microsoft Graph API tools for Code Puppy.

Organized by API category:
- users.py: User profiles, org hierarchy, directory search
- mail.py: Outlook mail operations
- mail_extended.py: Extended mail operations (move, archive, attachments)
- calendar.py: Calendar events and scheduling
- calendar_shared.py: Shared calendar access and meeting time finder
- calendar_attendees.py: Attendee management (add/remove) and event search
- meeting_health.py: Proactive meeting health monitoring and remediation
- onedrive.py: File storage and sharing
- teams.py: Teams channels, messaging, and online meetings
- sharepoint.py: SharePoint sites and content
- planner.py: Task and project management
- todo.py: Personal task management (Microsoft To Do)
- presence.py: Teams presence/availability status
"""

# Users
from code_puppy.tools.msgraph.users import (
    register_msgraph_get_me,
    register_msgraph_get_user,
    register_msgraph_search_users,
    register_msgraph_get_manager,
    register_msgraph_get_direct_reports,
)

# Mail
from code_puppy.tools.msgraph.mail import (
    register_msgraph_list_messages,
    register_msgraph_get_message,
    register_msgraph_send_mail,
    register_msgraph_reply_to_message,
    register_msgraph_search_mail,
    register_msgraph_list_mail_folders,
)

# Extended Mail (granular operations)
from code_puppy.tools.msgraph.mail_extended import (
    register_msgraph_move_message,
    register_msgraph_archive_message,
    register_msgraph_mark_as_read,
    register_msgraph_mark_as_unread,
    register_msgraph_forward_message,
    register_msgraph_delete_message,
    register_msgraph_list_attachments,
    register_msgraph_get_attachment,
)

# Calendar
from code_puppy.tools.msgraph.calendar import (
    register_msgraph_list_events,
    register_msgraph_get_event,
    register_msgraph_create_event,
    register_msgraph_update_event,
    register_msgraph_delete_event,
    register_msgraph_get_availability,
    register_msgraph_list_calendars,
)

# Shared Calendar
from code_puppy.tools.msgraph.calendar_shared import (
    register_msgraph_list_shared_calendars,
    register_msgraph_get_user_calendar_events,
    register_msgraph_find_meeting_times,
    register_msgraph_get_schedule,
)

# Calendar Attendee Management
from code_puppy.tools.msgraph.calendar_attendees import (
    register_msgraph_add_event_attendees,
    register_msgraph_remove_event_attendee,
    register_msgraph_search_events,
    register_msgraph_respond_to_event,
)

# OneDrive
from code_puppy.tools.msgraph.onedrive import (
    register_msgraph_list_drive_items,
    register_msgraph_get_drive_item,
    register_msgraph_download_file,
    register_msgraph_upload_file,
    register_msgraph_create_folder,
    register_msgraph_share_file,
    register_msgraph_search_files,
    register_msgraph_delete_drive_item,
)

# Teams
from code_puppy.tools.msgraph.teams import (
    register_msgraph_list_teams,
    register_msgraph_get_team,
    register_msgraph_list_channels,
    register_msgraph_get_channel,
    register_msgraph_list_channel_messages,
    register_msgraph_send_channel_message,
    register_msgraph_create_online_meeting,
    register_msgraph_list_chats,
    register_msgraph_send_chat_message,
    register_msgraph_send_direct_message,
)

# SharePoint
from code_puppy.tools.msgraph.sharepoint import (
    register_msgraph_list_sites,
    register_msgraph_get_site,
    register_msgraph_list_site_drives,
    register_msgraph_list_site_items,
    register_msgraph_search_sharepoint,
)

# Planner
from code_puppy.tools.msgraph.planner import (
    register_msgraph_list_plans,
    register_msgraph_get_plan,
    register_msgraph_list_buckets,
    register_msgraph_list_tasks,
    register_msgraph_get_task,
    register_msgraph_create_task,
    register_msgraph_update_task,
    register_msgraph_delete_task,
)

# To Do (personal task management)
from code_puppy.tools.msgraph.todo import (
    register_msgraph_list_todo_lists,
    register_msgraph_get_todo_list,
    register_msgraph_create_todo_list,
    register_msgraph_delete_todo_list,
    register_msgraph_list_todo_tasks,
    register_msgraph_get_todo_task,
    register_msgraph_create_todo_task,
    register_msgraph_update_todo_task,
    register_msgraph_complete_todo_task,
    register_msgraph_delete_todo_task,
)

# Presence
from code_puppy.tools.msgraph.presence import (
    register_msgraph_get_my_presence,
    register_msgraph_get_user_presence,
)

# Meeting Health (proactive monitoring)
from code_puppy.tools.msgraph.meeting_health import (
    register_msgraph_analyze_meeting_health,
    register_msgraph_get_meeting_responses,
    register_msgraph_find_pending_rsvps,
    register_msgraph_find_my_pending_responses,
    register_msgraph_suggest_reschedule,
)

# Common (generic API request)
from code_puppy.tools.msgraph.common import register_msgraph_api_request

# Convenience dict for bulk registration
MSGRAPH_TOOLS = {
    # Users
    "msgraph_get_me": register_msgraph_get_me,
    "msgraph_get_user": register_msgraph_get_user,
    "msgraph_search_users": register_msgraph_search_users,
    "msgraph_get_manager": register_msgraph_get_manager,
    "msgraph_get_direct_reports": register_msgraph_get_direct_reports,
    # Mail
    "msgraph_list_messages": register_msgraph_list_messages,
    "msgraph_get_message": register_msgraph_get_message,
    "msgraph_send_mail": register_msgraph_send_mail,
    "msgraph_reply_to_message": register_msgraph_reply_to_message,
    "msgraph_search_mail": register_msgraph_search_mail,
    "msgraph_list_mail_folders": register_msgraph_list_mail_folders,
    # Extended Mail
    "msgraph_move_message": register_msgraph_move_message,
    "msgraph_archive_message": register_msgraph_archive_message,
    "msgraph_mark_as_read": register_msgraph_mark_as_read,
    "msgraph_mark_as_unread": register_msgraph_mark_as_unread,
    "msgraph_forward_message": register_msgraph_forward_message,
    "msgraph_delete_message": register_msgraph_delete_message,
    "msgraph_list_attachments": register_msgraph_list_attachments,
    "msgraph_get_attachment": register_msgraph_get_attachment,
    # Calendar
    "msgraph_list_events": register_msgraph_list_events,
    "msgraph_get_event": register_msgraph_get_event,
    "msgraph_create_event": register_msgraph_create_event,
    "msgraph_update_event": register_msgraph_update_event,
    "msgraph_delete_event": register_msgraph_delete_event,
    "msgraph_get_availability": register_msgraph_get_availability,
    "msgraph_list_calendars": register_msgraph_list_calendars,
    # Shared Calendar
    "msgraph_list_shared_calendars": register_msgraph_list_shared_calendars,
    "msgraph_get_user_calendar_events": register_msgraph_get_user_calendar_events,
    "msgraph_find_meeting_times": register_msgraph_find_meeting_times,
    "msgraph_get_schedule": register_msgraph_get_schedule,
    # Calendar Attendee Management
    "msgraph_add_event_attendees": register_msgraph_add_event_attendees,
    "msgraph_remove_event_attendee": register_msgraph_remove_event_attendee,
    "msgraph_search_events": register_msgraph_search_events,
    "msgraph_respond_to_event": register_msgraph_respond_to_event,
    # OneDrive
    "msgraph_list_drive_items": register_msgraph_list_drive_items,
    "msgraph_get_drive_item": register_msgraph_get_drive_item,
    "msgraph_download_file": register_msgraph_download_file,
    "msgraph_upload_file": register_msgraph_upload_file,
    "msgraph_create_folder": register_msgraph_create_folder,
    "msgraph_share_file": register_msgraph_share_file,
    "msgraph_search_files": register_msgraph_search_files,
    "msgraph_delete_drive_item": register_msgraph_delete_drive_item,
    # Teams
    "msgraph_list_teams": register_msgraph_list_teams,
    "msgraph_get_team": register_msgraph_get_team,
    "msgraph_list_channels": register_msgraph_list_channels,
    "msgraph_get_channel": register_msgraph_get_channel,
    "msgraph_list_channel_messages": register_msgraph_list_channel_messages,
    "msgraph_send_channel_message": register_msgraph_send_channel_message,
    "msgraph_create_online_meeting": register_msgraph_create_online_meeting,
    "msgraph_list_chats": register_msgraph_list_chats,
    "msgraph_send_chat_message": register_msgraph_send_chat_message,
    "msgraph_send_direct_message": register_msgraph_send_direct_message,
    # SharePoint
    "msgraph_list_sites": register_msgraph_list_sites,
    "msgraph_get_site": register_msgraph_get_site,
    "msgraph_list_site_drives": register_msgraph_list_site_drives,
    "msgraph_list_site_items": register_msgraph_list_site_items,
    "msgraph_search_sharepoint": register_msgraph_search_sharepoint,
    # Planner
    "msgraph_list_plans": register_msgraph_list_plans,
    "msgraph_get_plan": register_msgraph_get_plan,
    "msgraph_list_buckets": register_msgraph_list_buckets,
    "msgraph_list_tasks": register_msgraph_list_tasks,
    "msgraph_get_task": register_msgraph_get_task,
    "msgraph_create_task": register_msgraph_create_task,
    "msgraph_update_task": register_msgraph_update_task,
    "msgraph_delete_task": register_msgraph_delete_task,
    # To Do (personal task management)
    "msgraph_list_todo_lists": register_msgraph_list_todo_lists,
    "msgraph_get_todo_list": register_msgraph_get_todo_list,
    "msgraph_create_todo_list": register_msgraph_create_todo_list,
    "msgraph_delete_todo_list": register_msgraph_delete_todo_list,
    "msgraph_list_todo_tasks": register_msgraph_list_todo_tasks,
    "msgraph_get_todo_task": register_msgraph_get_todo_task,
    "msgraph_create_todo_task": register_msgraph_create_todo_task,
    "msgraph_update_todo_task": register_msgraph_update_todo_task,
    "msgraph_complete_todo_task": register_msgraph_complete_todo_task,
    "msgraph_delete_todo_task": register_msgraph_delete_todo_task,
    # Presence
    "msgraph_get_my_presence": register_msgraph_get_my_presence,
    "msgraph_get_user_presence": register_msgraph_get_user_presence,
    # Meeting Health (proactive monitoring)
    "msgraph_analyze_meeting_health": register_msgraph_analyze_meeting_health,
    "msgraph_get_meeting_responses": register_msgraph_get_meeting_responses,
    "msgraph_find_pending_rsvps": register_msgraph_find_pending_rsvps,
    "msgraph_find_my_pending_responses": register_msgraph_find_my_pending_responses,
    "msgraph_suggest_reschedule": register_msgraph_suggest_reschedule,
    # Generic API request (fallback for any endpoint)
    "msgraph_api_request": register_msgraph_api_request,
}
