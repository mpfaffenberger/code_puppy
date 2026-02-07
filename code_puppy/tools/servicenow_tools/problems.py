"""ServiceNow Problem Management tools.

Tools for creating, viewing, and managing problem records.
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
# Create Problem
# ============================================================================


def servicenow_create_problem(
    ctx: RunContext,
    short_description: str,
    description: str = "",
    category: str = "",
    subcategory: str = "",
    assignment_group: str = "",
    assigned_to: str = "",
    urgency: int = 3,
    impact: int = 3,
    additional_fields: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Create a new problem record.

    Args:
        ctx: PydanticAI run context
        short_description: Brief summary of the problem (required)
        description: Detailed description
        category: Problem category
        subcategory: Problem subcategory
        assignment_group: Group to assign to
        assigned_to: Person to assign to
        urgency: Urgency level (1=High, 2=Medium, 3=Low)
        impact: Impact level (1=High, 2=Medium, 3=Low)
        additional_fields: Any additional fields
        dry_run: If True, preview without creating

    Returns:
        Dict containing created problem details.
    """
    mode_label = "DRY RUN" if dry_run else "CREATE PROBLEM"
    emit_info(
        Text.from_markup(
            f"\n[bold white on red] SERVICENOW {mode_label} [/bold white on red] "
            f"\U0001f6a8 [bold cyan]{short_description[:50]}...[/bold cyan]"
        )
    )

    if dry_run:
        urgency_labels = {1: "1 (High)", 2: "2 (Medium)", 3: "3 (Low)"}
        impact_labels = {1: "1 (High)", 2: "2 (Medium)", 3: "3 (Low)"}

        emit_success("Dry run complete - problem NOT created")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually create the problem.",
            "preview": {
                "short_description": short_description,
                "description": description or "(not provided)",
                "category": category or "(not specified)",
                "subcategory": subcategory or "(not specified)",
                "assignment_group": assignment_group or "(not assigned)",
                "assigned_to": assigned_to or "(not assigned)",
                "urgency": urgency_labels.get(urgency, str(urgency)),
                "impact": impact_labels.get(impact, str(impact)),
            },
        }

    try:
        client = get_servicenow_client()
        result = client.create_problem(
            short_description=short_description,
            description=description,
            category=category,
            subcategory=subcategory,
            assignment_group=assignment_group,
            assigned_to=assigned_to,
            urgency=urgency,
            impact=impact,
            additional_fields=additional_fields,
        )

        problem_data = result.get("result", {})
        problem_number = problem_data.get("number", "")
        sys_id = problem_data.get("sys_id", "")
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=problem.do?sys_id={sys_id}"

        emit_success(f"Created problem: {problem_number}")

        return {
            "success": True,
            "dry_run": False,
            "problem_number": problem_number,
            "sys_id": sys_id,
            "url": url,
            "message": f"Successfully created problem {problem_number}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_create_problem(agent: Any) -> Tool:
    """Register the servicenow_create_problem tool with a PydanticAI agent."""
    return agent.tool(servicenow_create_problem)


# ============================================================================
# Get Problem
# ============================================================================


def servicenow_get_problem(
    ctx: RunContext,
    problem_id: str,
) -> dict:
    """Get problem record details.

    Args:
        ctx: PydanticAI run context
        problem_id: Problem number (PRB0012345) or sys_id

    Returns:
        Dict containing problem details.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET PROBLEM [/bold white on blue] "
            f"\U0001f4cb [bold cyan]{problem_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_problem(problem_id)

        problem_data = result.get("result", {})

        if isinstance(problem_data, list):
            if not problem_data:
                return {
                    "success": False,
                    "error": f"Problem not found: {problem_id}",
                    "error_type": "not_found",
                }
            problem_data = problem_data[0]

        def get_display(field):
            val = problem_data.get(field, {})
            if isinstance(val, dict):
                return val.get("display_value", val.get("value", ""))
            return val or ""

        number = get_display("number")
        sys_id = problem_data.get("sys_id", {})
        if isinstance(sys_id, dict):
            sys_id = sys_id.get("value", "")

        emit_success(f"Retrieved problem: {number}")

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
            "opened_at": get_display("opened_at"),
            "root_cause": get_display("cause_notes"),
            "workaround": get_display("workaround"),
            "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=problem.do?sys_id={sys_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_get_problem(agent: Any) -> Tool:
    """Register the servicenow_get_problem tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_problem)


# ============================================================================
# List Problems
# ============================================================================


def servicenow_list_problems(
    ctx: RunContext,
    query: str = "",
    state: str = "",
    assignment_group: str = "",
    limit: int = 25,
) -> dict:
    """Search/list problem records.

    Args:
        ctx: PydanticAI run context
        query: Search query for short_description
        state: Filter by state
        assignment_group: Filter by assignment group
        limit: Maximum results (default: 25)

    Returns:
        Dict containing list of problems.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW LIST PROBLEMS [/bold white on blue] "
            f"\U0001f6a8 [bold cyan]{query or 'All'}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_problems(
            query=query,
            state=state,
            assignment_group=assignment_group,
            limit=limit,
        )

        problems = []
        for prob in result.get("result", []):

            def get_display(field):
                val = prob.get(field, {})
                if isinstance(val, dict):
                    return val.get("display_value", val.get("value", ""))
                return val or ""

            problems.append(
                {
                    "number": get_display("number"),
                    "short_description": get_display("short_description"),
                    "state": get_display("state"),
                    "priority": get_display("priority"),
                    "assignment_group": get_display("assignment_group"),
                    "assigned_to": get_display("assigned_to"),
                }
            )

        emit_success(f"Found {len(problems)} problem(s)")

        return {
            "success": True,
            "problems": problems,
            "total_count": len(problems),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_list_problems(agent: Any) -> Tool:
    """Register the servicenow_list_problems tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_problems)


# ============================================================================
# Link Incident to Problem
# ============================================================================


def servicenow_link_incident_to_problem(
    ctx: RunContext,
    incident_id: str,
    problem_id: str,
    dry_run: bool = False,
) -> dict:
    """Link an incident to a problem record.

    Args:
        ctx: PydanticAI run context
        incident_id: Incident number or sys_id
        problem_id: Problem number or sys_id
        dry_run: If True, preview without linking

    Returns:
        Dict with success status.
    """
    mode_label = "DRY RUN" if dry_run else "LINK TO PROBLEM"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW {mode_label} [/bold white on blue] "
            f"\U0001f517 [bold cyan]{incident_id} -> {problem_id}[/bold cyan]"
        )
    )

    if dry_run:
        emit_success("Dry run complete - NOT linked")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually link.",
            "preview": {
                "incident_id": incident_id,
                "problem_id": problem_id,
            },
        }

    try:
        client = get_servicenow_client()
        client.link_incident_to_problem(
            incident_id=incident_id,
            problem_id=problem_id,
        )

        emit_success(f"Linked {incident_id} to problem {problem_id}")

        return {
            "success": True,
            "dry_run": False,
            "message": f"Successfully linked {incident_id} to {problem_id}",
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_link_incident_to_problem(agent: Any) -> Tool:
    """Register the servicenow_link_incident_to_problem tool with a PydanticAI agent."""
    return agent.tool(servicenow_link_incident_to_problem)
