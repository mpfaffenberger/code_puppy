"""ServiceNow Change Management tools.

Tools for creating, viewing, and managing change requests.
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
# Create Change
# ============================================================================


def servicenow_create_change(
    ctx: RunContext,
    short_description: str,
    description: str = "",
    change_type: str = "normal",
    category: str = "",
    assignment_group: str = "",
    assigned_to: str = "",
    start_date: str = "",
    end_date: str = "",
    risk: str = "",
    impact: str = "",
    additional_fields: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Create a new change request.

    Args:
        ctx: PydanticAI run context
        short_description: Brief summary of the change (required)
        description: Detailed description
        change_type: Type of change - 'normal', 'standard', 'emergency' (default: normal)
        category: Change category
        assignment_group: Group responsible for the change
        assigned_to: Person assigned to implement
        start_date: Planned start date (YYYY-MM-DD HH:MM:SS)
        end_date: Planned end date (YYYY-MM-DD HH:MM:SS)
        risk: Risk level - 'high', 'moderate', 'low'
        impact: Impact level - 'high', 'medium', 'low'
        additional_fields: Any additional ServiceNow fields
        dry_run: If True, preview without creating

    Returns:
        Dict containing created change details or preview.
    """
    mode_label = "DRY RUN" if dry_run else "CREATE CHANGE"
    emit_info(
        Text.from_markup(
            f"\n[bold white on orange1] SERVICENOW {mode_label} [/bold white on orange1] "
            f"\U0001F504 [bold cyan]{short_description[:50]}...[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - change NOT created")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually create the change.",
            "preview": {
                "short_description": short_description,
                "description": description or "(not provided)",
                "change_type": change_type,
                "category": category or "(not specified)",
                "assignment_group": assignment_group or "(not assigned)",
                "assigned_to": assigned_to or "(not assigned)",
                "start_date": start_date or "(not specified)",
                "end_date": end_date or "(not specified)",
                "risk": risk or "(not specified)",
                "impact": impact or "(not specified)",
            },
        }

    try:
        client = get_servicenow_client()
        result = client.create_change(
            short_description=short_description,
            description=description,
            change_type=change_type,
            category=category,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            start_date=start_date,
            end_date=end_date,
            risk=risk,
            impact=impact,
            additional_fields=additional_fields,
        )

        change_data = result.get("result", {})
        change_number = change_data.get("number", "")
        sys_id = change_data.get("sys_id", "")
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=change_request.do?sys_id={sys_id}"

        emit_success(f"Created change: {change_number}")

        return {
            "success": True,
            "dry_run": False,
            "change_number": change_number,
            "sys_id": sys_id,
            "url": url,
            "message": f"Successfully created change {change_number}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_create_change(agent: Any) -> Tool:
    """Register the servicenow_create_change tool with a PydanticAI agent."""
    return agent.tool(servicenow_create_change)


# ============================================================================
# Get Change
# ============================================================================


def servicenow_get_change(
    ctx: RunContext,
    change_id: str,
) -> dict:
    """Get change request details.

    Args:
        ctx: PydanticAI run context
        change_id: Change number (CHG0012345) or sys_id

    Returns:
        Dict containing change details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET CHANGE [/bold white on blue] "
            f"\U0001F4CB [bold cyan]{change_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_change(change_id)

        change_data = result.get("result", {})
        
        if isinstance(change_data, list):
            if not change_data:
                return {
                    "success": False,
                    "error": f"Change not found: {change_id}",
                    "error_type": "not_found",
                }
            change_data = change_data[0]

        def get_display(field):
            val = change_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = change_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved change: {number}")

        return {
            "success": True,
            "sys_id": sys_id,
            "number": number,
            "short_description": get_display("short_description"),
            "description": get_display("description"),
            "state": get_display("state"),
            "type": get_display("type"),
            "category": get_display("category"),
            "risk": get_display("risk"),
            "impact": get_display("impact"),
            "priority": get_display("priority"),
            "assignment_group": get_display("assignment_group"),
            "assigned_to": get_display("assigned_to"),
            "start_date": get_display("start_date"),
            "end_date": get_display("end_date"),
            "opened_at": get_display("opened_at"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=change_request.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_change(agent: Any) -> Tool:
    """Register the servicenow_get_change tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_change)


# ============================================================================
# List My Changes
# ============================================================================


def servicenow_list_my_changes(
    ctx: RunContext,
    state: str = "",
    limit: int = 25,
) -> dict:
    """List change requests I'm involved in.

    Args:
        ctx: PydanticAI run context
        state: Filter by state (e.g., 'new', 'assess', 'authorize', 'scheduled', 'implement', 'review', 'closed')
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of changes.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW MY CHANGES [/bold white on blue] "
            f"\U0001F504 [bold cyan]Fetching...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_my_changes(state=state, limit=limit)

        changes = []
        for chg in result.get("result", []):
            def get_display(field):
                val = chg.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            changes.append({
                "number": get_display("number"),
                "short_description": get_display("short_description"),
                "state": get_display("state"),
                "type": get_display("type"),
                "risk": get_display("risk"),
                "assignment_group": get_display("assignment_group"),
                "start_date": get_display("start_date"),
                "end_date": get_display("end_date"),
            })

        emit_success(f"Found {len(changes)} change(s)")

        return {
            "success": True,
            "changes": changes,
            "total_count": len(changes),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_my_changes(agent: Any) -> Tool:
    """Register the servicenow_list_my_changes tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_changes)


# ============================================================================
# Add Change Task
# ============================================================================


def servicenow_add_change_task(
    ctx: RunContext,
    change_id: str,
    short_description: str,
    description: str = "",
    assignment_group: str = "",
    assigned_to: str = "",
    planned_start: str = "",
    planned_end: str = "",
    dry_run: bool = False,
) -> dict:
    """Add a task to a change request.

    Args:
        ctx: PydanticAI run context
        change_id: Change number or sys_id
        short_description: Task summary
        description: Task details
        assignment_group: Group to assign the task to
        assigned_to: Person to assign the task to
        planned_start: Planned start date
        planned_end: Planned end date
        dry_run: If True, preview without creating

    Returns:
        Dict containing created task details.
    """
    mode_label = "DRY RUN" if dry_run else "ADD CHANGE TASK"
    emit_info(
        Text.from_markup(
            f"\n[bold white on orange1] SERVICENOW {mode_label} [/bold white on orange1] "
            f"\U0001F4DD [bold cyan]{change_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - task NOT created")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually create the task.",
            "preview": {
                "change_id": change_id,
                "short_description": short_description,
                "description": description or "(not provided)",
                "assignment_group": assignment_group or "(not assigned)",
                "assigned_to": assigned_to or "(not assigned)",
            },
        }

    try:
        client = get_servicenow_client()
        result = client.add_change_task(
            change_id=change_id,
            short_description=short_description,
            description=description,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            planned_start=planned_start,
            planned_end=planned_end,
        )

        task_data = result.get("result", {})
        task_number = task_data.get("number", "")
        sys_id = task_data.get("sys_id", "")

        emit_success(f"Created change task: {task_number}")

        return {
            "success": True,
            "dry_run": False,
            "task_number": task_number,
            "sys_id": sys_id,
            "message": f"Successfully created change task {task_number}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_add_change_task(agent: Any) -> Tool:
    """Register the servicenow_add_change_task tool with a PydanticAI agent."""
    return agent.tool(servicenow_add_change_task)


# ============================================================================
# List Change Tasks
# ============================================================================


def servicenow_list_change_tasks(
    ctx: RunContext,
    change_id: str,
) -> dict:
    """List tasks for a change request.

    Args:
        ctx: PydanticAI run context
        change_id: Change number or sys_id

    Returns:
        Dict containing list of change tasks.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW CHANGE TASKS [/bold white on blue] "
            f"\U0001F4DD [bold cyan]{change_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_change_tasks(change_id)

        tasks = []
        for task in result.get("result", []):
            def get_display(field):
                val = task.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            tasks.append({
                "number": get_display("number"),
                "short_description": get_display("short_description"),
                "state": get_display("state"),
                "assignment_group": get_display("assignment_group"),
                "assigned_to": get_display("assigned_to"),
                "order": get_display("order"),
            })

        emit_success(f"Found {len(tasks)} task(s) for {change_id}")

        return {
            "success": True,
            "change_id": change_id,
            "tasks": tasks,
            "total_count": len(tasks),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_change_tasks(agent: Any) -> Tool:
    """Register the servicenow_list_change_tasks tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_change_tasks)
