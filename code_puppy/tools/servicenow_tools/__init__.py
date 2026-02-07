"""ServiceNow Tools Package.

This package provides a comprehensive set of tools for interacting with
Walmart's ServiceNow instance, organized by functional area.

Modules:
    - kb: Knowledge Base search and reading
    - incidents: Incident creation, viewing, and management
    - catalog: Service Catalog browsing and requests
    - users_groups: User and group management
    - changes: Change request management
    - problems: Problem record management
    - ritm: Request Item (RITM) tracking
    - cmdb: Configuration Management Database
    - approvals: Approval management
    - tasks: Generic task management
    - sla: SLA status and definitions
    - attachments: Attachment management
    - auth: Authentication
"""

# Common utilities
from ._common import (
    SERVICENOW_BASE_URL,
    MAX_CHARACTER_LIMIT,
    get_servicenow_client,
    handle_servicenow_error,
    convert_html_to_markdown,
    clean_text,
    analyze_automation_feasibility,
)

# Knowledge Base
from .kb import (
    servicenow_kb_search,
    servicenow_kb_read_article,
    servicenow_kb_search_by_category,
    register_servicenow_kb_search,
    register_servicenow_kb_read_article,
    register_servicenow_kb_search_by_category,
)

# Incidents
from .incidents import (
    servicenow_create_incident,
    servicenow_get_incident,
    servicenow_list_my_incidents,
    servicenow_add_incident_comment,
    servicenow_reassign_incident,
    servicenow_resolve_incident,
    servicenow_close_incident,
    servicenow_reopen_incident,
    servicenow_get_incident_history,
    servicenow_link_incidents,
    register_servicenow_create_incident,
    register_servicenow_get_incident,
    register_servicenow_list_my_incidents,
    register_servicenow_add_incident_comment,
    register_servicenow_reassign_incident,
    register_servicenow_resolve_incident,
    register_servicenow_close_incident,
    register_servicenow_reopen_incident,
    register_servicenow_get_incident_history,
    register_servicenow_link_incidents,
)

# Service Catalog
from .catalog import (
    servicenow_list_catalog_items,
    servicenow_get_catalog_item_details,
    servicenow_submit_catalog_request,
    servicenow_get_request_status,
    register_servicenow_list_catalog_items,
    register_servicenow_get_catalog_item_details,
    register_servicenow_submit_catalog_request,
    register_servicenow_get_request_status,
)

# Users and Groups
from .users_groups import (
    servicenow_search_assignment_groups,
    servicenow_search_users,
    servicenow_get_user_groups,
    servicenow_get_group_members,
    register_servicenow_search_assignment_groups,
    register_servicenow_search_users,
    register_servicenow_get_user_groups,
    register_servicenow_get_group_members,
)

# Changes
from .changes import (
    servicenow_create_change,
    servicenow_get_change,
    servicenow_list_my_changes,
    servicenow_add_change_task,
    servicenow_list_change_tasks,
    register_servicenow_create_change,
    register_servicenow_get_change,
    register_servicenow_list_my_changes,
    register_servicenow_add_change_task,
    register_servicenow_list_change_tasks,
)

# Problems
from .problems import (
    servicenow_create_problem,
    servicenow_get_problem,
    servicenow_list_problems,
    servicenow_link_incident_to_problem,
    register_servicenow_create_problem,
    register_servicenow_get_problem,
    register_servicenow_list_problems,
    register_servicenow_link_incident_to_problem,
)

# Request Items (RITM)
from .ritm import (
    servicenow_get_ritm,
    servicenow_list_my_ritms,
    servicenow_add_ritm_comment,
    register_servicenow_get_ritm,
    register_servicenow_list_my_ritms,
    register_servicenow_add_ritm_comment,
)

# CMDB
from .cmdb import (
    servicenow_search_cmdb,
    servicenow_get_cmdb_item,
    servicenow_get_cmdb_relationships,
    servicenow_list_cmdb_classes,
    register_servicenow_search_cmdb,
    register_servicenow_get_cmdb_item,
    register_servicenow_get_cmdb_relationships,
    register_servicenow_list_cmdb_classes,
)

# Approvals
from .approvals import (
    servicenow_list_my_approvals,
    servicenow_approve,
    servicenow_reject,
    register_servicenow_list_my_approvals,
    register_servicenow_approve,
    register_servicenow_reject,
)

# Tasks
from .tasks import (
    servicenow_list_my_tasks,
    servicenow_get_task,
    servicenow_update_task,
    servicenow_close_task,
    register_servicenow_list_my_tasks,
    register_servicenow_get_task,
    register_servicenow_update_task,
    register_servicenow_close_task,
)

# SLA
from .sla import (
    servicenow_get_sla_status,
    servicenow_list_sla_definitions,
    register_servicenow_get_sla_status,
    register_servicenow_list_sla_definitions,
)

# Attachments
from .attachments import (
    servicenow_list_attachments,
    servicenow_download_attachment,
    servicenow_upload_attachment,
    register_servicenow_list_attachments,
    register_servicenow_download_attachment,
    register_servicenow_upload_attachment,
)

# Authentication
from .auth import (
    servicenow_authenticate,
    register_servicenow_authenticate,
)


# All registration functions for easy access
ALL_REGISTRATION_FUNCTIONS = {
    # Knowledge Base
    "servicenow_kb_search": register_servicenow_kb_search,
    "servicenow_kb_read_article": register_servicenow_kb_read_article,
    "servicenow_kb_search_by_category": register_servicenow_kb_search_by_category,
    # Incidents
    "servicenow_create_incident": register_servicenow_create_incident,
    "servicenow_get_incident": register_servicenow_get_incident,
    "servicenow_list_my_incidents": register_servicenow_list_my_incidents,
    "servicenow_add_incident_comment": register_servicenow_add_incident_comment,
    "servicenow_reassign_incident": register_servicenow_reassign_incident,
    "servicenow_resolve_incident": register_servicenow_resolve_incident,
    "servicenow_close_incident": register_servicenow_close_incident,
    "servicenow_reopen_incident": register_servicenow_reopen_incident,
    "servicenow_get_incident_history": register_servicenow_get_incident_history,
    "servicenow_link_incidents": register_servicenow_link_incidents,
    # Service Catalog
    "servicenow_list_catalog_items": register_servicenow_list_catalog_items,
    "servicenow_get_catalog_item_details": register_servicenow_get_catalog_item_details,
    "servicenow_submit_catalog_request": register_servicenow_submit_catalog_request,
    "servicenow_get_request_status": register_servicenow_get_request_status,
    # Users/Groups
    "servicenow_search_assignment_groups": register_servicenow_search_assignment_groups,
    "servicenow_search_users": register_servicenow_search_users,
    "servicenow_get_user_groups": register_servicenow_get_user_groups,
    "servicenow_get_group_members": register_servicenow_get_group_members,
    # Changes
    "servicenow_create_change": register_servicenow_create_change,
    "servicenow_get_change": register_servicenow_get_change,
    "servicenow_list_my_changes": register_servicenow_list_my_changes,
    "servicenow_add_change_task": register_servicenow_add_change_task,
    "servicenow_list_change_tasks": register_servicenow_list_change_tasks,
    # Problems
    "servicenow_create_problem": register_servicenow_create_problem,
    "servicenow_get_problem": register_servicenow_get_problem,
    "servicenow_list_problems": register_servicenow_list_problems,
    "servicenow_link_incident_to_problem": register_servicenow_link_incident_to_problem,
    # RITM
    "servicenow_get_ritm": register_servicenow_get_ritm,
    "servicenow_list_my_ritms": register_servicenow_list_my_ritms,
    "servicenow_add_ritm_comment": register_servicenow_add_ritm_comment,
    # CMDB
    "servicenow_search_cmdb": register_servicenow_search_cmdb,
    "servicenow_get_cmdb_item": register_servicenow_get_cmdb_item,
    "servicenow_get_cmdb_relationships": register_servicenow_get_cmdb_relationships,
    "servicenow_list_cmdb_classes": register_servicenow_list_cmdb_classes,
    # Approvals
    "servicenow_list_my_approvals": register_servicenow_list_my_approvals,
    "servicenow_approve": register_servicenow_approve,
    "servicenow_reject": register_servicenow_reject,
    # Tasks
    "servicenow_list_my_tasks": register_servicenow_list_my_tasks,
    "servicenow_get_task": register_servicenow_get_task,
    "servicenow_update_task": register_servicenow_update_task,
    "servicenow_close_task": register_servicenow_close_task,
    # SLA
    "servicenow_get_sla_status": register_servicenow_get_sla_status,
    "servicenow_list_sla_definitions": register_servicenow_list_sla_definitions,
    # Attachments
    "servicenow_list_attachments": register_servicenow_list_attachments,
    "servicenow_download_attachment": register_servicenow_download_attachment,
    "servicenow_upload_attachment": register_servicenow_upload_attachment,
    # Authentication
    "servicenow_authenticate": register_servicenow_authenticate,
}

__all__ = [
    # Constants
    "SERVICENOW_BASE_URL",
    "MAX_CHARACTER_LIMIT",
    # Common utilities
    "get_servicenow_client",
    "handle_servicenow_error",
    "convert_html_to_markdown",
    "clean_text",
    "analyze_automation_feasibility",
    # All tool functions
    "servicenow_kb_search",
    "servicenow_kb_read_article",
    "servicenow_kb_search_by_category",
    "servicenow_create_incident",
    "servicenow_get_incident",
    "servicenow_list_my_incidents",
    "servicenow_add_incident_comment",
    "servicenow_reassign_incident",
    "servicenow_resolve_incident",
    "servicenow_close_incident",
    "servicenow_reopen_incident",
    "servicenow_get_incident_history",
    "servicenow_link_incidents",
    "servicenow_list_catalog_items",
    "servicenow_get_catalog_item_details",
    "servicenow_submit_catalog_request",
    "servicenow_get_request_status",
    "servicenow_search_assignment_groups",
    "servicenow_search_users",
    "servicenow_get_user_groups",
    "servicenow_get_group_members",
    "servicenow_create_change",
    "servicenow_get_change",
    "servicenow_list_my_changes",
    "servicenow_add_change_task",
    "servicenow_list_change_tasks",
    "servicenow_create_problem",
    "servicenow_get_problem",
    "servicenow_list_problems",
    "servicenow_link_incident_to_problem",
    "servicenow_get_ritm",
    "servicenow_list_my_ritms",
    "servicenow_add_ritm_comment",
    "servicenow_search_cmdb",
    "servicenow_get_cmdb_item",
    "servicenow_get_cmdb_relationships",
    "servicenow_list_cmdb_classes",
    "servicenow_list_my_approvals",
    "servicenow_approve",
    "servicenow_reject",
    "servicenow_list_my_tasks",
    "servicenow_get_task",
    "servicenow_update_task",
    "servicenow_close_task",
    "servicenow_get_sla_status",
    "servicenow_list_sla_definitions",
    "servicenow_list_attachments",
    "servicenow_download_attachment",
    "servicenow_upload_attachment",
    "servicenow_authenticate",
    # Registration functions
    "ALL_REGISTRATION_FUNCTIONS",
]
