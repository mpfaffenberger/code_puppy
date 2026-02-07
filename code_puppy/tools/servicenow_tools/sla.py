"""ServiceNow SLA Management tools.

Tools for viewing SLA status and definitions.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success

from ._common import (
    get_servicenow_client,
    handle_servicenow_error,
)


# ============================================================================
# Get SLA Status
# ============================================================================


def servicenow_get_sla_status(
    ctx: RunContext,
    task_id: str,
) -> dict:
    """Get SLA status for a task (incident, change, etc.).

    Args:
        ctx: PydanticAI run context
        task_id: Task sys_id

    Returns:
        Dict containing SLA records for the task.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW SLA STATUS [/bold white on blue] "
            f"\u23f1 [bold cyan]{task_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_sla_status(task_id)

        slas = []
        for sla in result.get("result", []):
            def get_display(field):
                val = sla.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            slas.append({
                "sla_name": get_display("sla"),
                "stage": get_display("stage"),
                "has_breached": get_display("has_breached"),
                "breach_time": get_display("planned_end_time"),
                "percentage": get_display("percentage"),
                "business_duration": get_display("business_duration"),
                "start_time": get_display("start_time"),
                "end_time": get_display("end_time"),
            })

        emit_success(f"Found {len(slas)} SLA record(s)")

        return {
            "success": True,
            "task_id": task_id,
            "sla_records": slas,
            "total_count": len(slas),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_sla_status(agent: Any) -> Tool:
    """Register the servicenow_get_sla_status tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_sla_status)


# ============================================================================
# List SLA Definitions
# ============================================================================


def servicenow_list_sla_definitions(
    ctx: RunContext,
    limit: int = 50,
) -> dict:
    """List available SLA definitions.

    Args:
        ctx: PydanticAI run context
        limit: Maximum results (default: 50)

    Returns:
        Dict containing SLA definitions.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW SLA DEFINITIONS [/bold white on blue] "
            f"\u23f1 [bold cyan]Listing...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_sla_definitions(limit=limit)

        definitions = []
        for sla in result.get("result", []):
            def get_display(field):
                val = sla.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            definitions.append({
                "sys_id": sla.get("sys_id", ""),
                "name": get_display("name"),
                "duration": get_display("duration"),
                "schedule": get_display("schedule"),
                "active": get_display("active"),
            })

        emit_success(f"Found {len(definitions)} SLA definition(s)")

        return {
            "success": True,
            "definitions": definitions,
            "total_count": len(definitions),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_sla_definitions(agent: Any) -> Tool:
    """Register the servicenow_list_sla_definitions tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_sla_definitions)
