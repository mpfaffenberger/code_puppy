"""Power BI Report tools.

Reports are the primary way users interact with data in Power BI.
They contain visualizations, pages, and can be connected to datasets.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.powerbi.common import get_powerbi_client, handle_powerbi_error


# =============================================================================
# REPORT TOOLS
# =============================================================================


def powerbi_list_reports(
    ctx: RunContext,
    workspace_id: str | None = None,
    top: int = 100,
    skip: int = 0,
) -> dict:
    """List Power BI reports.

    Supports pagination via top/skip parameters. Check 'has_more' in the response
    to determine if additional pages exist, and use 'next_skip' for the next request.

    Args:
        workspace_id: Optional workspace ID. If not specified, lists reports
            from "My Workspace".
        top: Maximum number of reports to return (default: 100).
        skip: Number of reports to skip for pagination (default: 0).

    Returns:
        Dict with success=True and list of reports, plus pagination metadata:
        - count: Number of reports returned in this page
        - reports: List of report objects
        - has_more: True if there may be more results (returned count == top)
        - next_skip: The skip value to use for the next page (if has_more is True)
        - top_used: The top value used for this request
        - skip_used: The skip value used for this request

    Example:
        # List first page of reports in My Workspace
        powerbi_list_reports()

        # Get next page
        powerbi_list_reports(skip=100)

        # List reports in a specific workspace
        powerbi_list_reports(workspace_id="abc-123-def")
    """
    workspace_label = (
        f"workspace {workspace_id[:8]}..." if workspace_id else "My Workspace"
    )

    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📊 [bold cyan]Listing reports in {workspace_label}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/reports"
        else:
            endpoint = "/reports"

        response = client.get(endpoint, params={"$top": top, "$skip": skip})
        reports = response.get("value", [])

        # Determine if there are more results
        has_more = len(reports) == top
        next_skip = skip + len(reports) if has_more else None

        emit_success(f"Found {len(reports)} reports (skip={skip}, has_more={has_more})")

        formatted = []
        for report in reports:
            formatted.append(
                {
                    "id": report.get("id"),
                    "name": report.get("name"),
                    "report_type": report.get("reportType"),
                    "web_url": report.get("webUrl"),
                    "dataset_id": report.get("datasetId"),
                    "embed_url": report.get("embedUrl"),
                }
            )

        return {
            "success": True,
            "count": len(formatted),
            "workspace_id": workspace_id,
            "reports": formatted,
            # Pagination metadata
            "has_more": has_more,
            "next_skip": next_skip,
            "top_used": top,
            "skip_used": skip,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_reports(agent: Any) -> Tool:
    """Register the powerbi_list_reports tool."""
    return agent.tool(powerbi_list_reports)


def powerbi_get_report(
    ctx: RunContext,
    report_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get details of a specific Power BI report.

    Args:
        report_id: The ID of the report to retrieve.
        workspace_id: Optional workspace ID containing the report.

    Returns:
        Dict with report details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📊 [bold cyan]Getting report: {report_id[:8]}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/reports/{report_id}"
        else:
            endpoint = f"/reports/{report_id}"

        response = client.get(endpoint)

        emit_success(f"Got report: {response.get('name', 'Unknown')}")

        return {
            "success": True,
            "report": {
                "id": response.get("id"),
                "name": response.get("name"),
                "report_type": response.get("reportType"),
                "web_url": response.get("webUrl"),
                "dataset_id": response.get("datasetId"),
                "embed_url": response.get("embedUrl"),
                "created_date_time": response.get("createdDateTime"),
                "modified_date_time": response.get("modifiedDateTime"),
            },
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_report(agent: Any) -> Tool:
    """Register the powerbi_get_report tool."""
    return agent.tool(powerbi_get_report)


def powerbi_list_report_pages(
    ctx: RunContext,
    report_id: str,
    workspace_id: str | None = None,
) -> dict:
    """List pages in a Power BI report.

    Args:
        report_id: The ID of the report.
        workspace_id: Optional workspace ID containing the report.

    Returns:
        Dict with list of report pages.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "📄 [bold cyan]Listing report pages...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/reports/{report_id}/pages"
        else:
            endpoint = f"/reports/{report_id}/pages"

        response = client.get(endpoint)
        pages = response.get("value", [])

        emit_success(f"Found {len(pages)} pages")

        formatted = []
        for page in pages:
            formatted.append(
                {
                    "name": page.get("name"),
                    "display_name": page.get("displayName"),
                    "order": page.get("order"),
                }
            )

        return {
            "success": True,
            "count": len(formatted),
            "pages": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_report_pages(agent: Any) -> Tool:
    """Register the powerbi_list_report_pages tool."""
    return agent.tool(powerbi_list_report_pages)


def powerbi_clone_report(
    ctx: RunContext,
    report_id: str,
    new_name: str,
    target_workspace_id: str | None = None,
    target_dataset_id: str | None = None,
    source_workspace_id: str | None = None,
) -> dict:
    """Clone a Power BI report.

    Args:
        report_id: The ID of the report to clone.
        new_name: Name for the cloned report.
        target_workspace_id: Optional target workspace for the clone.
        target_dataset_id: Optional target dataset for the clone.
        source_workspace_id: Optional source workspace containing the report.

    Returns:
        Dict with cloned report details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📋 [bold cyan]Cloning report as '{new_name}'...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if source_workspace_id:
            endpoint = f"/groups/{source_workspace_id}/reports/{report_id}/Clone"
        else:
            endpoint = f"/reports/{report_id}/Clone"

        body = {"name": new_name}
        if target_workspace_id:
            body["targetWorkspaceId"] = target_workspace_id
        if target_dataset_id:
            body["targetModelId"] = target_dataset_id

        response = client.post(endpoint, json=body)

        emit_success(f"Cloned report: {response.get('name', new_name)}")

        return {
            "success": True,
            "cloned_report": {
                "id": response.get("id"),
                "name": response.get("name"),
                "web_url": response.get("webUrl"),
            },
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_clone_report(agent: Any) -> Tool:
    """Register the powerbi_clone_report tool."""
    return agent.tool(powerbi_clone_report)
