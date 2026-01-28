"""Microsoft Graph Planner tools.

Provides tools for:
- Listing Planner plans
- Getting plan details
- Listing buckets in a plan
- Listing tasks
- Getting task details
- Creating tasks
- Updating tasks
- Deleting tasks

Note: Planner PATCH and DELETE operations require the If-Match header
with the resource's @odata.etag value.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    truncate_list_response,
    MAX_RESPONSE_CHARS,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_plan(plan: dict) -> dict:
    """Format a plan for display.

    Args:
        plan: Raw plan data from MS Graph API.

    Returns:
        Formatted plan dict with key fields.
    """
    return {
        "id": plan.get("id"),
        "title": plan.get("title"),
        "owner": plan.get("owner"),
        "created_by": plan.get("createdBy", {}).get("user", {}).get("id"),
        "created_datetime": plan.get("createdDateTime"),
    }


def _format_bucket(bucket: dict) -> dict:
    """Format a bucket for display.

    Args:
        bucket: Raw bucket data from MS Graph API.

    Returns:
        Formatted bucket dict with key fields.
    """
    return {
        "id": bucket.get("id"),
        "name": bucket.get("name"),
        "order_hint": bucket.get("orderHint"),
        "plan_id": bucket.get("planId"),
    }


def _format_task(task: dict) -> dict:
    """Format a task for display.

    Args:
        task: Raw task data from MS Graph API.

    Returns:
        Formatted task dict with key fields.
    """
    # Map priority values to labels
    priority_map = {
        1: "urgent",
        3: "important",
        5: "medium",
        9: "low",
    }
    priority_value = task.get("priority", 5)
    priority_label = priority_map.get(priority_value, f"priority-{priority_value}")

    # Get assignments (dict of user_id -> assignment info)
    assignments_raw = task.get("assignments", {})
    assigned_to = list(assignments_raw.keys())

    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "bucket_id": task.get("bucketId"),
        "plan_id": task.get("planId"),
        "percent_complete": task.get("percentComplete", 0),
        "priority": priority_value,
        "priority_label": priority_label,
        "due_date": task.get("dueDateTime"),
        "start_date": task.get("startDateTime"),
        "created_datetime": task.get("createdDateTime"),
        "completed_datetime": task.get("completedDateTime"),
        "assigned_to": assigned_to,
        "has_description": task.get("hasDescription", False),
        "checklist_item_count": task.get("checklistItemCount", 0),
        "active_checklist_item_count": task.get("activeChecklistItemCount", 0),
        "etag": task.get("@odata.etag"),
    }


def _format_task_preview(task: dict) -> dict:
    """Format a task for list/preview display.

    Args:
        task: Raw task data from MS Graph API.

    Returns:
        Formatted task dict with preview fields.
    """
    priority_map = {
        1: "urgent",
        3: "important",
        5: "medium",
        9: "low",
    }
    priority_value = task.get("priority", 5)
    priority_label = priority_map.get(priority_value, f"priority-{priority_value}")

    return {
        "id": task.get("id"),
        "title": task.get("title"),
        "bucket_id": task.get("bucketId"),
        "percent_complete": task.get("percentComplete", 0),
        "priority": priority_value,
        "priority_label": priority_label,
        "due_date": task.get("dueDateTime"),
        "assigned_to": list(task.get("assignments", {}).keys()),
    }


# =============================================================================
# LIST PLANS TOOL
# =============================================================================


def msgraph_list_plans(ctx: RunContext, group_id: str | None = None) -> dict:
    """List Planner plans.

    Args:
        group_id: Optional group/team ID to filter plans (if None, lists all user's plans).

    Returns:
        Dict with success, plans list (id, title, owner), or error.
    """
    if group_id:
        emit_info(
            Text.from_markup(
                "\n[bold white on blue] MS GRAPH [/bold white on blue] "
                f"📋 [bold cyan]Listing plans for group: {group_id[:20]}...[/bold cyan]"
            )
        )
    else:
        emit_info(
            Text.from_markup(
                "\n[bold white on blue] MS GRAPH [/bold white on blue] "
                "📋 [bold cyan]Listing user's Planner plans[/bold cyan]"
            )
        )

    try:
        client = get_msgraph_client()

        if group_id:
            endpoint = f"/groups/{group_id}/planner/plans"
        else:
            endpoint = "/me/planner/plans"

        response = client.get(endpoint)
        plans_data = response.get("value", [])

        plans = [_format_plan(p) for p in plans_data]
        total_count = len(plans)

        emit_success(f"Found {total_count} plan(s)")

        return {
            "success": True,
            "plans": plans,
            "total_count": total_count,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_plans(agent: Any) -> Tool:
    """Register the msgraph_list_plans tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_plans)


# =============================================================================
# GET PLAN TOOL
# =============================================================================


def msgraph_get_plan(ctx: RunContext, plan_id: str) -> dict:
    """Get details about a Planner plan.

    Args:
        plan_id: The plan ID.

    Returns:
        Dict with success, plan details, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Getting plan: {plan_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/planner/plans/{plan_id}"
        plan_data = client.get(endpoint)
        plan = _format_plan(plan_data)

        emit_success(f"Retrieved plan: {plan['title']}")

        return {
            "success": True,
            "plan": plan,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_plan(agent: Any) -> Tool:
    """Register the msgraph_get_plan tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_plan)


# =============================================================================
# LIST BUCKETS TOOL
# =============================================================================


def msgraph_list_buckets(ctx: RunContext, plan_id: str) -> dict:
    """List buckets in a Planner plan.

    Args:
        plan_id: The plan ID.

    Returns:
        Dict with success, buckets list (id, name, orderHint), or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Listing buckets for plan: {plan_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/planner/plans/{plan_id}/buckets"
        response = client.get(endpoint)
        buckets_data = response.get("value", [])

        buckets = [_format_bucket(b) for b in buckets_data]
        total_count = len(buckets)

        emit_success(f"Found {total_count} bucket(s)")

        return {
            "success": True,
            "buckets": buckets,
            "total_count": total_count,
            "plan_id": plan_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_buckets(agent: Any) -> Tool:
    """Register the msgraph_list_buckets tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_buckets)


# =============================================================================
# LIST TASKS TOOL
# =============================================================================


def msgraph_list_tasks(
    ctx: RunContext,
    plan_id: str,
    bucket_id: str | None = None,
    limit: int = 50,
    item_offset: int = 0,
) -> dict:
    """List tasks in a Planner plan.

    Args:
        plan_id: The plan ID.
        bucket_id: Optional bucket ID to filter tasks.
        limit: Maximum tasks to return (default 50).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, tasks list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    if bucket_id:
        emit_info(
            Text.from_markup(
                "\n[bold white on blue] MS GRAPH [/bold white on blue] "
                f"📋 [bold cyan]Listing tasks in bucket: {bucket_id[:20]}...[/bold cyan]"
            )
        )
    else:
        emit_info(
            Text.from_markup(
                "\n[bold white on blue] MS GRAPH [/bold white on blue] "
                f"📋 [bold cyan]Listing tasks in plan: {plan_id[:20]}...[/bold cyan]"
            )
        )

    try:
        client = get_msgraph_client()

        endpoint = f"/planner/plans/{plan_id}/tasks"
        params: dict[str, Any] = {"$top": limit}

        response = client.get(endpoint, params=params)
        tasks_data = response.get("value", [])

        # Filter by bucket_id if provided
        if bucket_id:
            tasks_data = [t for t in tasks_data if t.get("bucketId") == bucket_id]

        tasks = [_format_task_preview(t) for t in tasks_data]

        # Apply list truncation
        list_result = truncate_list_response(
            tasks, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Found {list_result['items_returned']} task(s)")

        result = {
            "success": True,
            "tasks": list_result["items"],
            "total_count": len(tasks),
            "plan_id": plan_id,
            "bucket_id": bucket_id,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_tasks(agent: Any) -> Tool:
    """Register the msgraph_list_tasks tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_tasks)


# =============================================================================
# GET TASK TOOL
# =============================================================================


def msgraph_get_task(ctx: RunContext, task_id: str) -> dict:
    """Get details about a Planner task.

    Args:
        task_id: The task ID.

    Returns:
        Dict with success, task details, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Getting task: {task_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/planner/tasks/{task_id}"
        task_data = client.get(endpoint)
        task = _format_task(task_data)

        emit_success(f"Retrieved task: {task['title']}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_task(agent: Any) -> Tool:
    """Register the msgraph_get_task tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_task)


# =============================================================================
# CREATE TASK TOOL
# =============================================================================


def msgraph_create_task(
    ctx: RunContext,
    plan_id: str,
    title: str,
    bucket_id: str | None = None,
    assigned_to: list[str] | None = None,
    due_date: str | None = None,
    priority: int | None = None,
) -> dict:
    """Create a new Planner task.

    Args:
        plan_id: The plan ID.
        title: Task title.
        bucket_id: Optional bucket ID.
        assigned_to: Optional list of user IDs to assign.
        due_date: Optional due date in ISO format.
        priority: Optional priority (1=urgent, 3=important, 5=medium, 9=low).

    Returns:
        Dict with success, created task, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Creating task: {title}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build task payload
        task_payload: dict[str, Any] = {
            "planId": plan_id,
            "title": title,
        }

        if bucket_id:
            task_payload["bucketId"] = bucket_id

        if assigned_to:
            # Assignments is a dict of user_id -> assignment object
            task_payload["assignments"] = {
                user_id: {
                    "@odata.type": "#microsoft.graph.plannerAssignment",
                    "orderHint": " !",
                }
                for user_id in assigned_to
            }

        if due_date:
            task_payload["dueDateTime"] = due_date

        if priority is not None:
            # Validate priority value
            if priority not in (1, 3, 5, 9):
                emit_warning(
                    f"Non-standard priority value {priority}. "
                    "Standard values: 1=urgent, 3=important, 5=medium, 9=low"
                )
            task_payload["priority"] = priority

        # Create the task
        endpoint = "/planner/tasks"
        response = client.post(endpoint, json=task_payload)

        task = _format_task(response)

        emit_success(f"Created task: {title}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_task(agent: Any) -> Tool:
    """Register the msgraph_create_task tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_create_task)


# =============================================================================
# UPDATE TASK TOOL
# =============================================================================


def msgraph_update_task(
    ctx: RunContext,
    task_id: str,
    title: str | None = None,
    percent_complete: int | None = None,
    due_date: str | None = None,
    priority: int | None = None,
) -> dict:
    """Update a Planner task.

    Note: Planner requires an If-Match header with the task's @odata.etag.
    This function fetches the task first to get the current etag.

    Args:
        task_id: The task ID.
        title: New title (optional).
        percent_complete: Completion percentage 0-100 (optional).
        due_date: New due date (optional).
        priority: New priority (optional).

    Returns:
        Dict with success, updated task, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Updating task: {task_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # First, get the task to retrieve its etag
        get_endpoint = f"/planner/tasks/{task_id}"
        current_task = client.get(get_endpoint)
        etag = current_task.get("@odata.etag")

        if not etag:
            return {
                "success": False,
                "error": "Failed to retrieve task etag for update",
                "error_type": "validation",
            }

        # Build update payload (only include provided fields)
        update_payload: dict[str, Any] = {}

        if title is not None:
            update_payload["title"] = title

        if percent_complete is not None:
            if not 0 <= percent_complete <= 100:
                return {
                    "success": False,
                    "error": "percent_complete must be between 0 and 100",
                    "error_type": "validation",
                }
            update_payload["percentComplete"] = percent_complete

        if due_date is not None:
            update_payload["dueDateTime"] = due_date

        if priority is not None:
            if priority not in (1, 3, 5, 9):
                emit_warning(
                    f"Non-standard priority value {priority}. "
                    "Standard values: 1=urgent, 3=important, 5=medium, 9=low"
                )
            update_payload["priority"] = priority

        if not update_payload:
            return {
                "success": False,
                "error": "No fields provided to update",
                "error_type": "validation",
            }

        # Update the task with If-Match header
        patch_endpoint = f"/planner/tasks/{task_id}"
        headers = {"If-Match": etag}
        response = client.patch(patch_endpoint, json=update_payload, headers=headers)

        task = _format_task(response)

        emit_success(f"Updated task: {task['title']}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_update_task(agent: Any) -> Tool:
    """Register the msgraph_update_task tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_update_task)


# =============================================================================
# DELETE TASK TOOL
# =============================================================================


def msgraph_delete_task(ctx: RunContext, task_id: str) -> dict:
    """Delete a Planner task.

    Note: Planner requires an If-Match header with the task's @odata.etag.
    This function fetches the task first to get the current etag.

    Args:
        task_id: The task ID.

    Returns:
        Dict with success, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📋 [bold cyan]Deleting task: {task_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # First, get the task to retrieve its etag
        get_endpoint = f"/planner/tasks/{task_id}"
        current_task = client.get(get_endpoint)
        etag = current_task.get("@odata.etag")

        if not etag:
            return {
                "success": False,
                "error": "Failed to retrieve task etag for deletion",
                "error_type": "validation",
            }

        # Delete the task with If-Match header
        delete_endpoint = f"/planner/tasks/{task_id}"
        headers = {"If-Match": etag}
        client.delete(delete_endpoint, headers=headers)

        emit_success("Task deleted successfully")

        return {
            "success": True,
            "message": "Task deleted successfully",
            "task_id": task_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_task(agent: Any) -> Tool:
    """Register the msgraph_delete_task tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_delete_task)
