"""ServiceNow Request Item (RITM) tools.

Tools for viewing and managing request items.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success

from ._common import (
    SERVICENOW_BASE_URL,
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# Get RITM
# ============================================================================


def servicenow_get_ritm(
    ctx: RunContext,
    ritm_id: str,
) -> dict:
    """Get request item (RITM) details.

    Args:
        ctx: PydanticAI run context
        ritm_id: RITM number (RITM0012345) or sys_id

    Returns:
        Dict containing RITM details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW GET RITM [/bold white on purple] "
            f"\U0001F4CB [bold cyan]{ritm_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_ritm(ritm_id)

        ritm_data = result.get("result", {})
        
        if isinstance(ritm_data, list):
            if not ritm_data:
                return {
                    "success": False,
                    "error": f"RITM not found: {ritm_id}",
                    "error_type": "not_found",
                }
            ritm_data = ritm_data[0]

        def get_display(field):
            val = ritm_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = ritm_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved RITM: {number}")

        return {
            "success": True,
            "sys_id": sys_id,
            "number": number,
            "short_description": get_display("short_description"),
            "state": get_display("state"),
            "stage": get_display("stage"),
            "catalog_item": get_display("cat_item"),
            "request": get_display("request"),
            "requested_for": get_display("requested_for"),
            "assignment_group": get_display("assignment_group"),
            "assigned_to": get_display("assigned_to"),
            "opened_at": get_display("opened_at"),
            "due_date": get_display("due_date"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=sc_req_item.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_ritm(agent: Any) -> Tool:
    """Register the servicenow_get_ritm tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_ritm)


# ============================================================================
# List My RITMs
# ============================================================================


def servicenow_list_my_ritms(
    ctx: RunContext,
    state: str = "",
    limit: int = 25,
) -> dict:
    """List my request items.

    Args:
        ctx: PydanticAI run context
        state: Filter by state
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of RITMs.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW MY RITMS [/bold white on purple] "
            f"\U0001F4E6 [bold cyan]Fetching...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_my_ritms(state=state, limit=limit)

        ritms = []
        for ritm in result.get("result", []):
            def get_display(field):
                val = ritm.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            ritms.append({
                "number": get_display("number"),
                "short_description": get_display("short_description"),
                "state": get_display("state"),
                "catalog_item": get_display("cat_item"),
                "assignment_group": get_display("assignment_group"),
                "opened_at": get_display("opened_at"),
            })

        emit_success(f"Found {len(ritms)} RITM(s)")

        return {
            "success": True,
            "ritms": ritms,
            "total_count": len(ritms),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_my_ritms(agent: Any) -> Tool:
    """Register the servicenow_list_my_ritms tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_ritms)


# ============================================================================
# Add RITM Comment
# ============================================================================


def servicenow_add_ritm_comment(
    ctx: RunContext,
    ritm_id: str,
    comment: str,
    is_work_note: bool = False,
    dry_run: bool = False,
) -> dict:
    """Add a comment or work note to a request item.

    Args:
        ctx: PydanticAI run context
        ritm_id: RITM number or sys_id
        comment: The comment text
        is_work_note: If True, adds as work note (internal)
        dry_run: If True, preview without adding

    Returns:
        Dict with success status.
    """
    note_type = "work note" if is_work_note else "comment"
    mode_label = "DRY RUN" if dry_run else f"ADD {note_type.upper()}"
    
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW {mode_label} [/bold white on green] "
            f"\U0001F4AC [bold cyan]{ritm_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success(f"Dry run complete - {note_type} NOT added")
        return {
            "success": True,
            "dry_run": True,
            "message": f"This is a preview. Set dry_run=False to actually add the {note_type}.",
            "preview": {
                "ritm_id": ritm_id,
                "comment": comment,
                "type": note_type,
            },
        }

    try:
        client = get_servicenow_client()
        result = client.add_ritm_comment(
            ritm_id=ritm_id,
            comment=comment,
            is_work_note=is_work_note,
        )

        emit_success(f"Added {note_type} to {ritm_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully added {note_type} to {ritm_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_add_ritm_comment(agent: Any) -> Tool:
    """Register the servicenow_add_ritm_comment tool with a PydanticAI agent."""
    return agent.tool(servicenow_add_ritm_comment)
