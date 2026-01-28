"""Power BI Dashboard tools.

Dashboards are collections of tiles that visualize data from
multiple reports and datasets.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.powerbi.common import get_powerbi_client, handle_powerbi_error


# =============================================================================
# DASHBOARD TOOLS
# =============================================================================


def powerbi_list_dashboards(
    ctx: RunContext,
    workspace_id: str | None = None,
    top: int = 100,
) -> dict:
    """List Power BI dashboards.

    Args:
        workspace_id: Optional workspace ID. If not specified, lists dashboards
            from "My Workspace".
        top: Maximum number of dashboards to return (default: 100).

    Returns:
        Dict with success=True and list of dashboards, or error details.

    Example:
        # List dashboards in My Workspace
        powerbi_list_dashboards()

        # List dashboards in a specific workspace
        powerbi_list_dashboards(workspace_id="abc-123-def")
    """
    workspace_label = f"workspace {workspace_id[:8]}..." if workspace_id else "My Workspace"
    
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📊 [bold cyan]Listing dashboards in {workspace_label}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        if workspace_id:
            endpoint = f"/groups/{workspace_id}/dashboards"
        else:
            endpoint = "/dashboards"
        
        response = client.get(endpoint, params={"$top": top})
        dashboards = response.get("value", [])
        
        emit_success(f"Found {len(dashboards)} dashboards")
        
        formatted = []
        for dash in dashboards:
            formatted.append({
                "id": dash.get("id"),
                "name": dash.get("displayName"),
                "web_url": dash.get("webUrl"),
                "embed_url": dash.get("embedUrl"),
                "is_read_only": dash.get("isReadOnly", False),
            })
        
        return {
            "success": True,
            "count": len(formatted),
            "workspace_id": workspace_id,
            "dashboards": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_dashboards(agent: Any) -> Tool:
    """Register the powerbi_list_dashboards tool."""
    return agent.tool(powerbi_list_dashboards)


def powerbi_get_dashboard(
    ctx: RunContext,
    dashboard_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get details of a specific Power BI dashboard.

    Args:
        dashboard_id: The ID of the dashboard to retrieve.
        workspace_id: Optional workspace ID containing the dashboard.

    Returns:
        Dict with dashboard details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📊 [bold cyan]Getting dashboard: {dashboard_id[:8]}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        if workspace_id:
            endpoint = f"/groups/{workspace_id}/dashboards/{dashboard_id}"
        else:
            endpoint = f"/dashboards/{dashboard_id}"
        
        response = client.get(endpoint)
        
        emit_success(f"Got dashboard: {response.get('displayName', 'Unknown')}")
        
        return {
            "success": True,
            "dashboard": {
                "id": response.get("id"),
                "name": response.get("displayName"),
                "web_url": response.get("webUrl"),
                "embed_url": response.get("embedUrl"),
                "is_read_only": response.get("isReadOnly", False),
            },
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_dashboard(agent: Any) -> Tool:
    """Register the powerbi_get_dashboard tool."""
    return agent.tool(powerbi_get_dashboard)


def powerbi_list_dashboard_tiles(
    ctx: RunContext,
    dashboard_id: str,
    workspace_id: str | None = None,
) -> dict:
    """List tiles in a Power BI dashboard.

    Tiles are the individual visualizations on a dashboard.

    Args:
        dashboard_id: The ID of the dashboard.
        workspace_id: Optional workspace ID containing the dashboard.

    Returns:
        Dict with list of dashboard tiles.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"🖼️ [bold cyan]Listing dashboard tiles...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        if workspace_id:
            endpoint = f"/groups/{workspace_id}/dashboards/{dashboard_id}/tiles"
        else:
            endpoint = f"/dashboards/{dashboard_id}/tiles"
        
        response = client.get(endpoint)
        tiles = response.get("value", [])
        
        emit_success(f"Found {len(tiles)} tiles")
        
        formatted = []
        for tile in tiles:
            formatted.append({
                "id": tile.get("id"),
                "title": tile.get("title"),
                "report_id": tile.get("reportId"),
                "dataset_id": tile.get("datasetId"),
                "embed_url": tile.get("embedUrl"),
                "row_span": tile.get("rowSpan"),
                "col_span": tile.get("colSpan"),
            })
        
        return {
            "success": True,
            "count": len(formatted),
            "dashboard_id": dashboard_id,
            "tiles": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_dashboard_tiles(agent: Any) -> Tool:
    """Register the powerbi_list_dashboard_tiles tool."""
    return agent.tool(powerbi_list_dashboard_tiles)
