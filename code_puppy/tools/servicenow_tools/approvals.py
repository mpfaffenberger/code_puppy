"""ServiceNow Approval tools.

Tools for viewing and managing approvals.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning

from ._common import (
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# List My Approvals
# ============================================================================


def servicenow_list_my_approvals(
    ctx: RunContext,
    state: str = "requested",
    limit: int = 25,
) -> dict:
    """List approvals assigned to me.

    Args:
        ctx: PydanticAI run context
        state: Filter by state - 'requested', 'approved', 'rejected', or '' for all (default: requested)
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of pending approvals.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on yellow] SERVICENOW MY APPROVALS [/bold white on yellow] "
            f"\u2705 [bold cyan]State: {state or 'all'}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_my_approvals(state=state, limit=limit)

        approvals = []
        for appr in result.get("result", []):

            def get_display(field):
                val = appr.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            sys_id = get_display("sys_id") or appr.get("sys_id", "")

            # Get the source document info
            source_table = get_display("source_table")
            document_id = appr.get("document_id", {})
            doc_display = (
                document_id.get("display_value", "")
                if isinstance(document_id, dict)
                else ""
            )
            doc_value = (
                document_id.get("value", "")
                if isinstance(document_id, dict)
                else document_id
            )

            approvals.append(
                {
                    "sys_id": sys_id,
                    "state": get_display("state"),
                    "approver": get_display("approver"),
                    "source_table": source_table,
                    "document_id": doc_value,
                    "document_display": doc_display,
                    "comments": get_display("comments"),
                    "due_date": get_display("due_date"),
                    "created": get_display("sys_created_on"),
                }
            )

        emit_success(f"Found {len(approvals)} approval(s)")

        return {
            "success": True,
            "approvals": approvals,
            "total_count": len(approvals),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_my_approvals(agent: Any) -> Tool:
    """Register the servicenow_list_my_approvals tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_approvals)


# ============================================================================
# Approve
# ============================================================================


def servicenow_approve(
    ctx: RunContext,
    approval_id: str,
    comments: str = "",
    dry_run: bool = False,
) -> dict:
    """Approve an approval record.

    Args:
        ctx: PydanticAI run context
        approval_id: Approval sys_id
        comments: Optional approval comments
        dry_run: If True, preview without approving

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "APPROVE"
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW {mode_label} [/bold white on green] "
            f"\u2705 [bold cyan]{approval_id[:20]}...[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - NOT approved")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually approve.",
            "preview": {
                "approval_id": approval_id,
                "comments": comments or "(none)",
                "action": "approve",
            },
        }

    try:
        client = get_servicenow_client()
        client.approve(approval_id=approval_id, comments=comments)

        emit_success(f"Approved: {approval_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully approved {approval_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_approve(agent: Any) -> Tool:
    """Register the servicenow_approve tool with a PydanticAI agent."""
    return agent.tool(servicenow_approve)


# ============================================================================
# Reject
# ============================================================================


def servicenow_reject(
    ctx: RunContext,
    approval_id: str,
    comments: str,
    dry_run: bool = False,
) -> dict:
    """Reject an approval record.

    Args:
        ctx: PydanticAI run context
        approval_id: Approval sys_id
        comments: Rejection reason (required)
        dry_run: If True, preview without rejecting

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "REJECT"
    emit_info(
        Text.from_markup(
            f"\n[bold white on red] SERVICENOW {mode_label} [/bold white on red] "
            f"\u274c [bold cyan]{approval_id[:20]}...[/bold cyan]"
        )
    )

    if not comments:
        emit_warning("Rejection comments are required")
        return {
            "success": False,
            "error": "Rejection comments are required",
            "error_type": "validation",
        }

    if dry_run:
        emit_success("Dry run complete - NOT rejected")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually reject.",
            "preview": {
                "approval_id": approval_id,
                "comments": comments,
                "action": "reject",
            },
        }

    try:
        client = get_servicenow_client()
        client.reject(approval_id=approval_id, comments=comments)

        emit_success(f"Rejected: {approval_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully rejected {approval_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_reject(agent: Any) -> Tool:
    """Register the servicenow_reject tool with a PydanticAI agent."""
    return agent.tool(servicenow_reject)
