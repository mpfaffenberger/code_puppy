"""ServiceNow Generic Task tools.

Tools for viewing and managing tasks across different tables.
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
# List My Tasks
# ============================================================================


def servicenow_list_my_tasks(
    ctx: RunContext,
    table: str = "task",
    state: str = "",
    limit: int = 25,
) -> dict:
    """List tasks assigned to me.

    Args:
        ctx: PydanticAI run context
        table: Task table to query (default: 'task' for all)
            Common tables:
            - task: All tasks
            - incident: Incidents only
            - change_task: Change tasks only
            - sc_task: Catalog tasks only
        state: Filter by state
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of tasks.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW MY TASKS [/bold white on blue] "
            f"\U0001f4cb [bold cyan]Table: {table}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_my_tasks(table=table, state=state, limit=limit)

        tasks = []
        for task in result.get("result", []):

            def get_display(field):
                val = task.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            tasks.append(
                {
                    "number": get_display("number"),
                    "short_description": get_display("short_description"),
                    "state": get_display("state"),
                    "priority": get_display("priority"),
                    "assignment_group": get_display("assignment_group"),
                    "class": get_display("sys_class_name"),
                    "updated": get_display("sys_updated_on"),
                }
            )

        emit_success(f"Found {len(tasks)} task(s)")

        return {
            "success": True,
            "tasks": tasks,
            "total_count": len(tasks),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_my_tasks(agent: Any) -> Tool:
    """Register the servicenow_list_my_tasks tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_tasks)


# ============================================================================
# Get Task
# ============================================================================


def servicenow_get_task(
    ctx: RunContext,
    task_id: str,
    table: str = "task",
) -> dict:
    """Get task details.

    Args:
        ctx: PydanticAI run context
        task_id: Task number or sys_id
        table: Task table (default: task)

    Returns:
        Dict containing task details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET TASK [/bold white on blue] "
            f"\U0001f4cb [bold cyan]{task_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_task(task_id=task_id, table=table)

        task_data = result.get("result", {})

        if isinstance(task_data, list):
            if not task_data:
                return {
                    "success": False,
                    "error": f"Task not found: {task_id}",
                    "error_type": "not_found",
                }
            task_data = task_data[0]

        def get_display(field):
            val = task_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = task_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved task: {number}")

        return {
            "success": True,
            "sys_id": sys_id,
            "number": number,
            "short_description": get_display("short_description"),
            "description": get_display("description"),
            "state": get_display("state"),
            "priority": get_display("priority"),
            "assignment_group": get_display("assignment_group"),
            "assigned_to": get_display("assigned_to"),
            "class": get_display("sys_class_name"),
            "opened_at": get_display("opened_at"),
            "due_date": get_display("due_date"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri={table}.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_task(agent: Any) -> Tool:
    """Register the servicenow_get_task tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_task)


# ============================================================================
# Update Task
# ============================================================================


def servicenow_update_task(
    ctx: RunContext,
    task_id: str,
    updates: dict,
    table: str = "task",
    dry_run: bool = False,
) -> dict:
    """Update a task.

    Args:
        ctx: PydanticAI run context
        task_id: Task sys_id
        updates: Dictionary of fields to update
        table: Task table (default: task)
        dry_run: If True, preview without updating

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "UPDATE TASK"
    emit_info(
        Text.from_markup(
            f"\n[bold white on orange1] SERVICENOW {mode_label} [/bold white on orange1] "
            f"\U0001f4dd [bold cyan]{task_id[:20]}...[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - task NOT updated")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually update.",
            "preview": {
                "task_id": task_id,
                "table": table,
                "updates": updates,
            },
        }

    try:
        client = get_servicenow_client()
        client.update_task(task_id=task_id, updates=updates, table=table)

        emit_success(f"Updated task: {task_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully updated {task_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_update_task(agent: Any) -> Tool:
    """Register the servicenow_update_task tool with a PydanticAI agent."""
    return agent.tool(servicenow_update_task)


# ============================================================================
# Close Task
# ============================================================================


def servicenow_close_task(
    ctx: RunContext,
    task_id: str,
    close_notes: str = "",
    table: str = "task",
    dry_run: bool = False,
) -> dict:
    """Close a task.

    Args:
        ctx: PydanticAI run context
        task_id: Task sys_id
        close_notes: Closure notes
        table: Task table (default: task)
        dry_run: If True, preview without closing

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "CLOSE TASK"
    emit_info(
        Text.from_markup(
            f"\n[bold white on gray] SERVICENOW {mode_label} [/bold white on gray] "
            f"\U0001f512 [bold cyan]{task_id[:20]}...[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - task NOT closed")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually close.",
            "preview": {
                "task_id": task_id,
                "table": table,
                "close_notes": close_notes or "(none)",
            },
        }

    try:
        client = get_servicenow_client()
        client.close_task(task_id=task_id, close_notes=close_notes, table=table)

        emit_success(f"Closed task: {task_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully closed {task_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_close_task(agent: Any) -> Tool:
    """Register the servicenow_close_task tool with a PydanticAI agent."""
    return agent.tool(servicenow_close_task)
