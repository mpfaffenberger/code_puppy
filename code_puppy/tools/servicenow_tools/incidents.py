"""ServiceNow Incident Management tools.

Tools for creating, viewing, updating, and managing incidents.
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
# Create Incident
# ============================================================================


def servicenow_create_incident(
    ctx: RunContext,
    short_description: str,
    description: str = "",
    urgency: int = 3,
    impact: int = 3,
    category: str = "",
    subcategory: str = "",
    assignment_group: str = "",
    assigned_to: str = "",
    caller_id: str = "",
    contact_type: str = "",
    cmdb_ci: str = "",
    additional_fields: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Create a new incident in ServiceNow.

    Args:
        ctx: PydanticAI run context
        short_description: Brief summary of the incident (required, max 160 chars)
        description: Detailed description of the issue
        urgency: 1=High, 2=Medium, 3=Low (default: 3)
        impact: 1=High, 2=Medium, 3=Low (default: 3)
        category: Incident category (e.g., "Software", "Hardware", "Network")
        subcategory: Incident subcategory
        assignment_group: ITIL group name or sys_id to assign the incident to
        assigned_to: Username or sys_id of the person to assign to
        caller_id: Who reported the incident (defaults to current user)
        contact_type: How the incident was reported (phone, email, self-service, chat)
        cmdb_ci: Configuration item (application/server) affected
        additional_fields: Any additional ServiceNow incident fields
        dry_run: If True, preview the incident without creating it

    Returns:
        Dict containing:
            - success (bool): Whether the incident was created
            - incident_number (str): The incident number (e.g., INC0012345)
            - sys_id (str): The incident sys_id
            - url (str): Direct link to the incident
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if creation failed
    """
    mode_label = "DRY RUN" if dry_run else "CREATE INCIDENT"
    emit_info(
        Text.from_markup(
            f"\n[bold white on red] SERVICENOW {mode_label} [/bold white on red] "
            f"\U0001f6a8 [bold cyan]{short_description[:50]}...[/bold cyan]"
        )
    )

    # In dry_run mode, just return what would be created
    if dry_run:
        urgency_labels = {1: "1 (High)", 2: "2 (Medium)", 3: "3 (Low)"}
        impact_labels = {1: "1 (High)", 2: "2 (Medium)", 3: "3 (Low)"}

        emit_success("Dry run complete - incident NOT created")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually create the incident.",
            "preview": {
                "short_description": short_description,
                "description": description or "(not provided)",
                "urgency": urgency_labels.get(urgency, str(urgency)),
                "impact": impact_labels.get(impact, str(impact)),
                "category": category or "(not specified)",
                "subcategory": subcategory or "(not specified)",
                "assignment_group": assignment_group or "(not assigned)",
                "assigned_to": assigned_to or "(not assigned)",
                "caller_id": caller_id or "(current user)",
                "contact_type": contact_type or "(not specified)",
                "cmdb_ci": cmdb_ci or "(not specified)",
            },
        }

    try:
        client = get_servicenow_client()
        result = client.create_incident(
            short_description=short_description,
            description=description,
            urgency=urgency,
            impact=impact,
            category=category,
            subcategory=subcategory,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            caller_id=caller_id,
            contact_type=contact_type,
            cmdb_ci=cmdb_ci,
            additional_fields=additional_fields,
        )

        incident_data = result.get("result", {})
        incident_number = incident_data.get("number", "")
        sys_id = incident_data.get("sys_id", "")
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}"

        emit_success(f"Created incident: {incident_number}")

        return {
            "success": True,
            "dry_run": False,
            "incident_number": incident_number,
            "sys_id": sys_id,
            "url": url,
            "message": f"Successfully created incident {incident_number}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_create_incident(agent: Any) -> Tool:
    """Register the servicenow_create_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_create_incident)


# ============================================================================
# Get Incident
# ============================================================================


def servicenow_get_incident(
    ctx: RunContext,
    incident_id: str,
) -> dict:
    """Get incident details by incident number or sys_id.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number (e.g., INC0012345) or sys_id

    Returns:
        Dict containing full incident details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET INCIDENT [/bold white on blue] "
            f"\U0001f4cb [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_incident(incident_id)

        incident_data = result.get("result", {})

        # Handle list response
        if isinstance(incident_data, list):
            if not incident_data:
                return {
                    "success": False,
                    "error": f"Incident not found: {incident_id}",
                    "error_type": "not_found",
                }
            incident_data = incident_data[0]

        if not incident_data:
            return {
                "success": False,
                "error": f"Incident not found: {incident_id}",
                "error_type": "not_found",
            }

        # Extract display values where available
        def get_display(field):
            val = incident_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = incident_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved incident: {number}")

        return {
            "success": True,
            "sys_id": sys_id,
            "number": number,
            "short_description": get_display("short_description"),
            "description": get_display("description"),
            "state": get_display("state"),
            "priority": get_display("priority"),
            "urgency": get_display("urgency"),
            "impact": get_display("impact"),
            "category": get_display("category"),
            "subcategory": get_display("subcategory"),
            "assignment_group": get_display("assignment_group"),
            "assigned_to": get_display("assigned_to"),
            "caller": get_display("caller_id"),
            "opened_at": get_display("opened_at"),
            "updated_at": get_display("sys_updated_on"),
            "resolved_at": get_display("resolved_at"),
            "close_code": get_display("close_code"),
            "close_notes": get_display("close_notes"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_incident(agent: Any) -> Tool:
    """Register the servicenow_get_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_incident)


# ============================================================================
# List My Incidents
# ============================================================================


def servicenow_list_my_incidents(
    ctx: RunContext,
    state: str = "",
    limit: int = 25,
) -> dict:
    """List incidents I've opened or am assigned to.

    Args:
        ctx: PydanticAI run context
        state: Filter by state (e.g., 'new', 'in_progress', 'resolved', 'closed')
        limit: Maximum number of results (default: 25)

    Returns:
        Dict containing list of incidents.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] SERVICENOW MY INCIDENTS [/bold white on blue] "
            "\U0001f4cb [bold cyan]Fetching...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_my_incidents(state=state, limit=limit)

        incidents = []
        for inc in result.get("result", []):

            def get_display(field):
                val = inc.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            incidents.append(
                {
                    "number": get_display("number"),
                    "short_description": get_display("short_description"),
                    "state": get_display("state"),
                    "priority": get_display("priority"),
                    "assignment_group": get_display("assignment_group"),
                    "assigned_to": get_display("assigned_to"),
                    "opened_at": get_display("opened_at"),
                }
            )

        emit_success(f"Found {len(incidents)} incident(s)")

        return {
            "success": True,
            "incidents": incidents,
            "total_count": len(incidents),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_my_incidents(agent: Any) -> Tool:
    """Register the servicenow_list_my_incidents tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_incidents)


# ============================================================================
# Add Incident Comment
# ============================================================================


def servicenow_add_incident_comment(
    ctx: RunContext,
    incident_id: str,
    comment: str,
    is_work_note: bool = False,
    dry_run: bool = False,
) -> dict:
    """Add a comment or work note to an incident.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        comment: The comment text to add
        is_work_note: If True, adds as internal work note. If False, visible to caller.
        dry_run: If True, preview without adding

    Returns:
        Dict with success status.
    """
    note_type = "work note" if is_work_note else "comment"
    mode_label = "DRY RUN" if dry_run else f"ADD {note_type.upper()}"

    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW {mode_label} [/bold white on green] "
            f"\U0001f4ac [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success(f"Dry run complete - {note_type} NOT added")
        return {
            "success": True,
            "dry_run": True,
            "message": f"This is a preview. Set dry_run=False to actually add the {note_type}.",
            "preview": {
                "incident_id": incident_id,
                "comment": comment,
                "type": note_type,
            },
        }

    try:
        client = get_servicenow_client()
        client.add_incident_comment(
            incident_id=incident_id,
            comment=comment,
            is_work_note=is_work_note,
        )

        emit_success(f"Added {note_type} to {incident_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully added {note_type} to {incident_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_add_incident_comment(agent: Any) -> Tool:
    """Register the servicenow_add_incident_comment tool with a PydanticAI agent."""
    return agent.tool(servicenow_add_incident_comment)


# ============================================================================
# Reassign Incident
# ============================================================================


def servicenow_reassign_incident(
    ctx: RunContext,
    incident_id: str,
    assignment_group: str = "",
    assigned_to: str = "",
    work_notes: str = "",
    dry_run: bool = False,
) -> dict:
    """Reassign an incident to a different group or person.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number (e.g., INC0012345) or sys_id
        assignment_group: New assignment group name or sys_id
        assigned_to: New assignee username or sys_id
        work_notes: Optional work note explaining the reassignment
        dry_run: If True, preview the reassignment without actually doing it

    Returns:
        Dict containing:
            - success (bool): Whether the reassignment succeeded
            - incident_number (str): The incident number
            - new_assignment_group (str): The new assignment group
            - new_assigned_to (str): The new assignee
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if reassignment failed
    """
    mode_label = "DRY RUN" if dry_run else "REASSIGN"
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW {mode_label} [/bold white on purple] "
            f"\U0001f504 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    if not assignment_group and not assigned_to:
        return {
            "success": False,
            "error": "Must provide at least one of: assignment_group or assigned_to",
            "error_type": "validation",
        }

    reassign_fields = {}
    if assignment_group:
        reassign_fields["assignment_group"] = assignment_group
    if assigned_to:
        reassign_fields["assigned_to"] = assigned_to
    if work_notes:
        reassign_fields["work_notes"] = work_notes

    if dry_run:
        emit_success("Dry run complete - incident NOT reassigned")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually reassign the incident.",
            "preview": {
                "incident_id": incident_id,
                "assignment_group": assignment_group or "(not changed)",
                "assigned_to": assigned_to or "(not changed)",
                "work_notes": work_notes or "(none)",
            },
        }

    try:
        client = get_servicenow_client()

        # Get incident sys_id if we have a number
        if incident_id.upper().startswith("INC"):
            incident_result = client.get_incident(incident_id)
            results = incident_result.get("result", [])
            if isinstance(results, list):
                if not results:
                    return {
                        "success": False,
                        "error": f"Incident not found: {incident_id}",
                        "error_type": "not_found",
                    }
                incident_sys_id = (
                    results[0].get("sys_id", {}).get("value", results[0].get("sys_id"))
                )
                incident_number = (
                    results[0]
                    .get("number", {})
                    .get("value", results[0].get("number", incident_id))
                )
            else:
                incident_sys_id = results.get("sys_id", {}).get(
                    "value", results.get("sys_id")
                )
                incident_number = results.get("number", {}).get(
                    "value", results.get("number", incident_id)
                )
        else:
            incident_sys_id = incident_id
            incident_number = incident_id

        # Perform the reassignment via update_incident
        result = client.update_incident(
            incident_id=incident_sys_id,
            updates=reassign_fields,
        )

        updated_data = result.get("result", {})

        def get_display(field):
            val = updated_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        emit_success(f"Reassigned incident: {incident_number}")

        return {
            "success": True,
            "dry_run": False,
            "incident_number": incident_number,
            "message": f"Successfully reassigned {incident_number}",
            "new_assignment_group": get_display("assignment_group"),
            "new_assigned_to": get_display("assigned_to"),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_reassign_incident(agent: Any) -> Tool:
    """Register the servicenow_reassign_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_reassign_incident)


# ============================================================================
# Resolve Incident
# ============================================================================


def servicenow_resolve_incident(
    ctx: RunContext,
    incident_id: str,
    resolution_code: str,
    resolution_notes: str,
    dry_run: bool = False,
) -> dict:
    """Resolve an incident.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        resolution_code: Resolution code (e.g., 'Solved', 'Solved Remotely', 'Not Solved')
        resolution_notes: Description of how the incident was resolved
        dry_run: If True, preview without resolving

    Returns:
        Dict with success status and updated incident details.
    """
    mode_label = "DRY RUN" if dry_run else "RESOLVE"
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW {mode_label} [/bold white on green] "
            f"\u2705 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - incident NOT resolved")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually resolve the incident.",
            "preview": {
                "incident_id": incident_id,
                "resolution_code": resolution_code,
                "resolution_notes": resolution_notes,
            },
        }

    try:
        client = get_servicenow_client()
        client.resolve_incident(
            incident_id=incident_id,
            resolution_code=resolution_code,
            resolution_notes=resolution_notes,
        )

        emit_success(f"Resolved incident: {incident_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully resolved {incident_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_resolve_incident(agent: Any) -> Tool:
    """Register the servicenow_resolve_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_resolve_incident)


# ============================================================================
# Close Incident
# ============================================================================


def servicenow_close_incident(
    ctx: RunContext,
    incident_id: str,
    close_code: str = "Solved",
    close_notes: str = "",
    dry_run: bool = False,
) -> dict:
    """Close an incident.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        close_code: Close code (default: 'Solved')
        close_notes: Closure notes
        dry_run: If True, preview without closing

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "CLOSE"
    emit_info(
        Text.from_markup(
            f"\n[bold white on gray] SERVICENOW {mode_label} [/bold white on gray] "
            f"\U0001f512 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - incident NOT closed")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually close the incident.",
            "preview": {
                "incident_id": incident_id,
                "close_code": close_code,
                "close_notes": close_notes or "(none)",
            },
        }

    try:
        client = get_servicenow_client()
        client.close_incident(
            incident_id=incident_id,
            close_code=close_code,
            close_notes=close_notes,
        )

        emit_success(f"Closed incident: {incident_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully closed {incident_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_close_incident(agent: Any) -> Tool:
    """Register the servicenow_close_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_close_incident)


# ============================================================================
# Reopen Incident
# ============================================================================


def servicenow_reopen_incident(
    ctx: RunContext,
    incident_id: str,
    reason: str,
    dry_run: bool = False,
) -> dict:
    """Reopen a closed incident.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        reason: Reason for reopening the incident
        dry_run: If True, preview without reopening

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "REOPEN"
    emit_info(
        Text.from_markup(
            f"\n[bold white on yellow] SERVICENOW {mode_label} [/bold white on yellow] "
            f"\U0001f513 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - incident NOT reopened")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually reopen the incident.",
            "preview": {
                "incident_id": incident_id,
                "reason": reason,
            },
        }

    try:
        client = get_servicenow_client()
        client.reopen_incident(
            incident_id=incident_id,
            reason=reason,
        )

        emit_success(f"Reopened incident: {incident_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully reopened {incident_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_reopen_incident(agent: Any) -> Tool:
    """Register the servicenow_reopen_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_reopen_incident)


# ============================================================================
# Get Incident History
# ============================================================================


def servicenow_get_incident_history(
    ctx: RunContext,
    incident_id: str,
    limit: int = 50,
) -> dict:
    """Get the audit/activity history for an incident.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        limit: Maximum number of history entries (default: 50)

    Returns:
        Dict containing the history entries.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW INCIDENT HISTORY [/bold white on blue] "
            f"\U0001f4dc [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_incident_history(
            incident_id=incident_id,
            limit=limit,
        )

        history = []
        for entry in result.get("result", []):

            def get_display(field):
                val = entry.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            history.append(
                {
                    "field": get_display("fieldname"),
                    "old_value": get_display("oldvalue"),
                    "new_value": get_display("newvalue"),
                    "user": get_display("user"),
                    "timestamp": get_display("sys_created_on"),
                }
            )

        emit_success(f"Found {len(history)} history entries")

        return {
            "success": True,
            "incident_id": incident_id,
            "history": history,
            "total_count": len(history),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_incident_history(agent: Any) -> Tool:
    """Register the servicenow_get_incident_history tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_incident_history)


# ============================================================================
# Link Incidents
# ============================================================================


def servicenow_link_incidents(
    ctx: RunContext,
    parent_incident_id: str,
    child_incident_id: str,
    dry_run: bool = False,
) -> dict:
    """Link a child incident to a parent incident.

    Args:
        ctx: PydanticAI run context
        parent_incident_id: Parent incident number or sys_id
        child_incident_id: Child incident number or sys_id
        dry_run: If True, preview without linking

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "LINK INCIDENTS"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW {mode_label} [/bold white on blue] "
            f"\U0001f517 [bold cyan]{child_incident_id} -> {parent_incident_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - incidents NOT linked")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually link the incidents.",
            "preview": {
                "parent_incident_id": parent_incident_id,
                "child_incident_id": child_incident_id,
            },
        }

    try:
        client = get_servicenow_client()
        client.link_incidents(
            parent_incident_id=parent_incident_id,
            child_incident_id=child_incident_id,
        )

        emit_success(f"Linked {child_incident_id} to parent {parent_incident_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully linked {child_incident_id} to {parent_incident_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_link_incidents(agent: Any) -> Tool:
    """Register the servicenow_link_incidents tool with a PydanticAI agent."""
    return agent.tool(servicenow_link_incidents)
