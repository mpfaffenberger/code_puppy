"""Microsoft Graph Presence tools.

Provides tools for checking user availability status in Teams.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import get_msgraph_client, _handle_msgraph_error


def _format_presence(data: dict) -> dict:
    """Format a presence response."""
    return {
        "id": data.get("id"),
        "availability": data.get("availability"),  # Available, Busy, Away, etc.
        "activity": data.get("activity"),  # InACall, InAMeeting, Presenting, etc.
        "status_message": data.get("statusMessage", {})
        .get("message", {})
        .get("content"),
    }


def msgraph_get_my_presence(ctx: RunContext) -> dict:
    """Get your current Teams presence/availability status.

    Returns:
        Dict with success, presence info, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🟢 [bold cyan]Getting your presence status[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get("/me/presence")

        presence = _format_presence(response)
        emit_success(f"Status: {presence.get('availability')}")

        return {
            "success": True,
            "presence": presence,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_my_presence(agent: Any) -> Tool:
    """Register the msgraph_get_my_presence tool."""
    return agent.tool(msgraph_get_my_presence)


def msgraph_get_user_presence(ctx: RunContext, user_id: str) -> dict:
    """Get another user's Teams presence/availability status.

    Args:
        user_id: User ID or email address.

    Returns:
        Dict with success, presence info, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🟢 [bold cyan]Getting presence for {user_id}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get(f"/users/{user_id}/presence")

        presence = _format_presence(response)
        emit_success(f"Status: {presence.get('availability')}")

        return {
            "success": True,
            "user_id": user_id,
            "presence": presence,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_user_presence(agent: Any) -> Tool:
    """Register the msgraph_get_user_presence tool."""
    return agent.tool(msgraph_get_user_presence)
