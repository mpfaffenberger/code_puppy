"""Microsoft Graph user and organizational hierarchy tools.

Provides tools for:
- Getting current user profile
- Getting user profiles by ID or email
- Searching users in the directory
- Getting manager information
- Getting direct reports
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    truncate_list_response,
    MAX_RESPONSE_CHARS,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_user(user_data: dict) -> dict:
    """Format a user response for cleaner output.

    Args:
        user_data: Raw user data from MS Graph API.

    Returns:
        Formatted user dict with key fields.
    """
    return {
        "id": user_data.get("id"),
        "display_name": user_data.get("displayName"),
        "mail": user_data.get("mail"),
        "user_principal_name": user_data.get("userPrincipalName"),
        "job_title": user_data.get("jobTitle"),
        "department": user_data.get("department"),
        "office_location": user_data.get("officeLocation"),
        "mobile_phone": user_data.get("mobilePhone"),
        "business_phones": user_data.get("businessPhones", []),
    }


# =============================================================================
# GET ME TOOL
# =============================================================================


def msgraph_get_me(ctx: RunContext) -> dict:
    """Get the current authenticated user's profile.

    Returns:
        Dict with success, user (display_name, mail, job_title, etc.), or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "👤 [bold cyan]Getting current user profile[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        user_data = client.get("/me")
        user = _format_user(user_data)

        emit_success(f"Retrieved profile for: {user['display_name']}")

        return {
            "success": True,
            "user": user,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_me(agent: Any) -> Tool:
    """Register the msgraph_get_me tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_me)


# =============================================================================
# GET USER TOOL
# =============================================================================


def msgraph_get_user(ctx: RunContext, user_id: str) -> dict:
    """Get a user's profile by ID or email (UPN).

    Args:
        user_id: User ID (GUID) or email address (user principal name).

    Returns:
        Dict with success, user info, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"👤 [bold cyan]Getting user: {user_id}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        user_data = client.get(f"/users/{user_id}")
        user = _format_user(user_data)

        emit_success(f"Retrieved profile for: {user['display_name']}")

        return {
            "success": True,
            "user": user,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_user(agent: Any) -> Tool:
    """Register the msgraph_get_user tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_user)


# =============================================================================
# SEARCH USERS TOOL
# =============================================================================


def msgraph_search_users(
    ctx: RunContext, query: str, limit: int = 10, item_offset: int = 0
) -> dict:
    """Search for users in the directory.

    Args:
        query: Search query (matches displayName, mail, etc.).
        limit: Maximum results (default 10).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, users list, total_count, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching users: '{query}'[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Use $filter with startswith for common search patterns
        # Also use $search for broader matches (requires ConsistencyLevel header)
        # For simplicity, we use $filter with startswith on displayName
        params = {
            "$filter": f"startswith(displayName, '{query}') or "
            f"startswith(mail, '{query}') or "
            f"startswith(userPrincipalName, '{query}')",
            "$top": limit,
        }

        response = client.get("/users", params=params)
        users_data = response.get("value", [])

        users = [_format_user(u) for u in users_data]

        # Apply list truncation
        list_result = truncate_list_response(
            users, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(
            f"Found {list_result['items_returned']} user(s) matching '{query}'"
        )

        result = {
            "success": True,
            "users": list_result["items"],
            "total_count": len(users),
            "query": query,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_users(agent: Any) -> Tool:
    """Register the msgraph_search_users tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_search_users)


# =============================================================================
# GET MANAGER TOOL
# =============================================================================


def msgraph_get_manager(ctx: RunContext, user_id: str = "me") -> dict:
    """Get a user's manager.

    Args:
        user_id: User ID, email, or "me" for current user (default: "me").

    Returns:
        Dict with success, manager info, or error.
    """
    target = "current user" if user_id == "me" else user_id
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"👔 [bold cyan]Getting manager for: {target}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        endpoint = f"/users/{user_id}/manager" if user_id != "me" else "/me/manager"
        manager_data = client.get(endpoint)
        manager = _format_user(manager_data)

        emit_success(f"Manager: {manager['display_name']}")

        return {
            "success": True,
            "manager": manager,
            "user_id": user_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_manager(agent: Any) -> Tool:
    """Register the msgraph_get_manager tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_manager)


# =============================================================================
# GET DIRECT REPORTS TOOL
# =============================================================================


def msgraph_get_direct_reports(
    ctx: RunContext, user_id: str = "me", limit: int = 50, item_offset: int = 0
) -> dict:
    """Get a user's direct reports.

    Args:
        user_id: User ID, email, or "me" for current user (default: "me").
        limit: Maximum results (default 50).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, direct_reports list, count, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    target = "current user" if user_id == "me" else user_id
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"👥 [bold cyan]Getting direct reports for: {target}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        endpoint = (
            f"/users/{user_id}/directReports"
            if user_id != "me"
            else "/me/directReports"
        )
        params = {"$top": limit}

        response = client.get(endpoint, params=params)
        reports_data = response.get("value", [])

        direct_reports = [_format_user(r) for r in reports_data]

        # Apply list truncation
        list_result = truncate_list_response(
            direct_reports, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Found {list_result['items_returned']} direct report(s)")

        result = {
            "success": True,
            "direct_reports": list_result["items"],
            "count": len(direct_reports),
            "user_id": user_id,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_direct_reports(agent: Any) -> Tool:
    """Register the msgraph_get_direct_reports tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_direct_reports)
