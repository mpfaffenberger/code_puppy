"""Power BI Workspace tools.

Workspaces (also called Groups) are containers for reports, datasets,
dashboards, and dataflows in Power BI.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.powerbi.common import get_powerbi_client, handle_powerbi_error


# =============================================================================
# WORKSPACE TOOLS
# =============================================================================


def powerbi_list_workspaces(
    ctx: RunContext,
    top: int = 100,
    skip: int = 0,
    filter_query: str | None = None,
) -> dict:
    """List all Power BI workspaces (groups) the user has access to.

    Args:
        top: Maximum number of workspaces to return (default: 100, max: 5000).
        skip: Number of workspaces to skip for pagination.
        filter_query: Optional OData filter (e.g., "contains(name,'Sales')").

    Returns:
        Dict with success=True and list of workspaces, or error details.

    Example:
        # List all workspaces
        powerbi_list_workspaces()

        # Filter by name
        powerbi_list_workspaces(filter_query="contains(name,'Analytics')")
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "📂 [bold cyan]Listing workspaces...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        params = {"$top": top, "$skip": skip}
        if filter_query:
            params["$filter"] = filter_query
        
        response = client.get("/groups", params=params)
        workspaces = response.get("value", [])
        
        emit_success(f"Found {len(workspaces)} workspaces")
        
        # Format workspaces for readability
        formatted = []
        for ws in workspaces:
            formatted.append({
                "id": ws.get("id"),
                "name": ws.get("name"),
                "type": ws.get("type"),
                "is_read_only": ws.get("isReadOnly", False),
                "capacity_id": ws.get("capacityId"),
            })
        
        return {
            "success": True,
            "count": len(formatted),
            "workspaces": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_workspaces(agent: Any) -> Tool:
    """Register the powerbi_list_workspaces tool."""
    return agent.tool(powerbi_list_workspaces)


def powerbi_get_workspace(
    ctx: RunContext,
    workspace_id: str,
) -> dict:
    """Get details of a specific Power BI workspace.

    Args:
        workspace_id: The ID of the workspace to retrieve.

    Returns:
        Dict with workspace details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📂 [bold cyan]Getting workspace: {workspace_id[:8]}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        response = client.get(f"/groups/{workspace_id}")
        
        emit_success(f"Got workspace: {response.get('name', 'Unknown')}")
        
        return {
            "success": True,
            "workspace": {
                "id": response.get("id"),
                "name": response.get("name"),
                "type": response.get("type"),
                "is_read_only": response.get("isReadOnly", False),
                "capacity_id": response.get("capacityId"),
            },
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_workspace(agent: Any) -> Tool:
    """Register the powerbi_get_workspace tool."""
    return agent.tool(powerbi_get_workspace)


def powerbi_list_workspace_users(
    ctx: RunContext,
    workspace_id: str,
) -> dict:
    """List users with access to a Power BI workspace.

    Args:
        workspace_id: The ID of the workspace.

    Returns:
        Dict with list of users and their access rights.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"👥 [bold cyan]Listing workspace users...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        response = client.get(f"/groups/{workspace_id}/users")
        users = response.get("value", [])
        
        emit_success(f"Found {len(users)} users")
        
        formatted = []
        for user in users:
            formatted.append({
                "email": user.get("emailAddress"),
                "display_name": user.get("displayName"),
                "access_right": user.get("groupUserAccessRight"),
                "principal_type": user.get("principalType"),
            })
        
        return {
            "success": True,
            "count": len(formatted),
            "users": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_workspace_users(agent: Any) -> Tool:
    """Register the powerbi_list_workspace_users tool."""
    return agent.tool(powerbi_list_workspace_users)
