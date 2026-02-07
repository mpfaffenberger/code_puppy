"""ServiceNow User and Group tools.

Tools for searching users, groups, and managing memberships.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success

from ._common import (
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# Search Assignment Groups
# ============================================================================


def servicenow_search_assignment_groups(
    ctx: RunContext,
    query: str,
    limit: int = 25,
) -> dict:
    """Search for ITIL assignment groups.

    Args:
        ctx: PydanticAI run context
        query: Search query for group name
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of matching groups.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW SEARCH GROUPS [/bold white on blue] "
            f"\U0001F465 [bold cyan]{query}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_assignment_groups(query=query, limit=limit)

        groups = []
        for group in result.get("result", []):
            def get_display(field):
                val = group.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            groups.append({
                "sys_id": get_display("sys_id") or group.get("sys_id", ""),
                "name": get_display("name"),
                "description": get_display("description"),
                "manager": get_display("manager"),
                "email": get_display("email"),
            })

        emit_success(f"Found {len(groups)} group(s)")

        return {
            "success": True,
            "groups": groups,
            "total_count": len(groups),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_search_assignment_groups(agent: Any) -> Tool:
    """Register the servicenow_search_assignment_groups tool with a PydanticAI agent."""
    return agent.tool(servicenow_search_assignment_groups)


# ============================================================================
# Search Users
# ============================================================================


def servicenow_search_users(
    ctx: RunContext,
    query: str,
    limit: int = 25,
) -> dict:
    """Search for users by name, email, or username.

    Args:
        ctx: PydanticAI run context
        query: Search query (name, email, or username)
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of matching users.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW SEARCH USERS [/bold white on blue] "
            f"\U0001F464 [bold cyan]{query}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_users(query=query, limit=limit)

        users = []
        for user in result.get("result", []):
            def get_display(field):
                val = user.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            users.append({
                "sys_id": get_display("sys_id") or user.get("sys_id", ""),
                "user_name": get_display("user_name"),
                "name": get_display("name"),
                "email": get_display("email"),
                "title": get_display("title"),
                "department": get_display("department"),
                "manager": get_display("manager"),
            })

        emit_success(f"Found {len(users)} user(s)")

        return {
            "success": True,
            "users": users,
            "total_count": len(users),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_search_users(agent: Any) -> Tool:
    """Register the servicenow_search_users tool with a PydanticAI agent."""
    return agent.tool(servicenow_search_users)


# ============================================================================
# Get User Groups
# ============================================================================


def servicenow_get_user_groups(
    ctx: RunContext,
    user_id: str,
    limit: int = 50,
) -> dict:
    """Get groups that a user belongs to.

    Args:
        ctx: PydanticAI run context
        user_id: Username or sys_id
        limit: Maximum results (default: 50)

    Returns:
        Dict containing list of groups the user belongs to.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW USER GROUPS [/bold white on blue] "
            f"\U0001F465 [bold cyan]Groups for: {user_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_user_groups(user_id=user_id, limit=limit)

        groups = []
        for membership in result.get("result", []):
            group_info = membership.get("group", {})
            if isinstance(group_info, dict):
                groups.append({
                    "sys_id": group_info.get("value", ""),
                    "name": group_info.get("display_value", ""),
                })

        emit_success(f"Found {len(groups)} group(s) for user {user_id}")

        return {
            "success": True,
            "user": user_id,
            "groups": groups,
            "total_count": len(groups),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_user_groups(agent: Any) -> Tool:
    """Register the servicenow_get_user_groups tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_user_groups)


# ============================================================================
# Get Group Members
# ============================================================================


def servicenow_get_group_members(
    ctx: RunContext,
    group_id: str,
    limit: int = 100,
) -> dict:
    """Get members of a group.

    Args:
        ctx: PydanticAI run context
        group_id: Group name or sys_id
        limit: Maximum results (default: 100)

    Returns:
        Dict containing list of group members.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GROUP MEMBERS [/bold white on blue] "
            f"\U0001F465 [bold cyan]Members of: {group_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_group_members(group_id=group_id, limit=limit)

        members = []
        for membership in result.get("result", []):
            user_info = membership.get("user", {})
            if isinstance(user_info, dict):
                members.append({
                    "sys_id": user_info.get("value", ""),
                    "name": user_info.get("display_value", ""),
                })
            elif user_info:
                members.append({
                    "sys_id": user_info,
                    "name": "(name not available)",
                })

        emit_success(f"Found {len(members)} member(s) in group {group_id}")

        return {
            "success": True,
            "group": group_id,
            "members": members,
            "total_count": len(members),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_group_members(agent: Any) -> Tool:
    """Register the servicenow_get_group_members tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_group_members)
