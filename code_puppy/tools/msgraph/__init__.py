"""Microsoft Graph API tools for Code Puppy.

Organized by API category:
- users.py: User profiles, org hierarchy, directory search
- mail.py: Outlook mail operations
- calendar.py: Calendar events and scheduling
- onedrive.py: File storage and sharing
- teams.py: Teams channels, messaging, and online meetings
- sharepoint.py: SharePoint sites and content
- planner.py: Task and project management
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

# Common (generic API request, authentication, and utilities)
from code_puppy.tools.msgraph.common import (
    register_msgraph_api_request,
    register_msgraph_authenticate,
    # Truncation utilities (10,000 char limit)
    truncate_content,
    truncate_list_response,
    apply_response_limit,
    MAX_RESPONSE_CHARS,
)

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
    # Calendar
    "msgraph_list_events": register_msgraph_list_events,
    "msgraph_get_event": register_msgraph_get_event,
    "msgraph_create_event": register_msgraph_create_event,
    "msgraph_update_event": register_msgraph_update_event,
    "msgraph_delete_event": register_msgraph_delete_event,
    "msgraph_get_availability": register_msgraph_get_availability,
    "msgraph_list_calendars": register_msgraph_list_calendars,
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
    # Generic API request (fallback for any endpoint)
    "msgraph_api_request": register_msgraph_api_request,
    # Authentication tool (for handling 401 errors)
    "msgraph_authenticate": register_msgraph_authenticate,
}
