"""Microsoft To Do tools for Code Puppy.

Provides tools for managing personal tasks in Microsoft To Do,
which is separate from Planner (team task management).

To Do API: https://docs.microsoft.com/en-us/graph/api/resources/todo-overview
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import get_msgraph_client, _handle_msgraph_error


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_todo_list(data: dict) -> dict:
    """Format a To Do list response."""
    return {
        "id": data.get("id"),
        "display_name": data.get("displayName"),
        "is_owner": data.get("isOwner", True),
        "is_shared": data.get("isShared", False),
        "wellknown_list_name": data.get(
            "wellknownListName"
        ),  # e.g., "defaultList", "flaggedEmails"
    }


def _format_todo_task(data: dict) -> dict:
    """Format a To Do task response."""
    body = data.get("body", {})
    due = data.get("dueDateTime", {})
    completed = data.get("completedDateTime", {})

    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "status": data.get(
            "status"
        ),  # notStarted, inProgress, completed, waitingOnOthers, deferred
        "importance": data.get("importance"),  # low, normal, high
        "is_reminder_on": data.get("isReminderOn", False),
        "body": body.get("content") if body else None,
        "body_type": body.get("contentType") if body else None,
        "due_date": due.get("dateTime") if due else None,
        "due_timezone": due.get("timeZone") if due else None,
        "completed_date": completed.get("dateTime") if completed else None,
        "created_datetime": data.get("createdDateTime"),
        "last_modified": data.get("lastModifiedDateTime"),
    }


# =============================================================================
# TO DO LIST TOOLS
# =============================================================================


def msgraph_list_todo_lists(ctx: RunContext) -> dict:
    """List all To Do task lists.

    Returns:
        Dict with success, lists array, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "✅ [bold cyan]Listing To Do task lists[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get("/me/todo/lists")
        lists_data = response.get("value", [])

        lists = [_format_todo_list(lst) for lst in lists_data]
        emit_success(f"Found {len(lists)} To Do list(s)")

        return {
            "success": True,
            "lists": lists,
            "total_count": len(lists),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_todo_lists(agent: Any) -> Tool:
    """Register the msgraph_list_todo_lists tool."""
    return agent.tool(msgraph_list_todo_lists)


def msgraph_get_todo_list(ctx: RunContext, list_id: str) -> dict:
    """Get a specific To Do list by ID.

    Args:
        list_id: The To Do list ID.

    Returns:
        Dict with success, list details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✅ [bold cyan]Getting To Do list: {list_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get(f"/me/todo/lists/{list_id}")

        list_data = _format_todo_list(response)
        emit_success(f"Retrieved list: {list_data.get('display_name')}")

        return {
            "success": True,
            "list": list_data,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_todo_list(agent: Any) -> Tool:
    """Register the msgraph_get_todo_list tool."""
    return agent.tool(msgraph_get_todo_list)


def msgraph_create_todo_list(ctx: RunContext, display_name: str) -> dict:
    """Create a new To Do task list.

    Args:
        display_name: Name for the new list.

    Returns:
        Dict with success, created list, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✅ [bold cyan]Creating To Do list: {display_name}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.post("/me/todo/lists", json={"displayName": display_name})

        list_data = _format_todo_list(response)
        emit_success(f"Created list: {list_data.get('display_name')}")

        return {
            "success": True,
            "list": list_data,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_todo_list(agent: Any) -> Tool:
    """Register the msgraph_create_todo_list tool."""
    return agent.tool(msgraph_create_todo_list)


def msgraph_delete_todo_list(ctx: RunContext, list_id: str) -> dict:
    """Delete a To Do task list.

    Args:
        list_id: The To Do list ID to delete.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🗑️ [bold cyan]Deleting To Do list: {list_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        client.delete(f"/me/todo/lists/{list_id}")

        emit_success("List deleted successfully")

        return {
            "success": True,
            "message": "To Do list deleted",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_todo_list(agent: Any) -> Tool:
    """Register the msgraph_delete_todo_list tool."""
    return agent.tool(msgraph_delete_todo_list)


# =============================================================================
# TO DO TASK TOOLS
# =============================================================================


def msgraph_list_todo_tasks(
    ctx: RunContext,
    list_id: str,
    include_completed: bool = False,
    limit: int = 50,
) -> dict:
    """List tasks in a To Do list.

    Args:
        list_id: The To Do list ID.
        include_completed: If True, include completed tasks.
        limit: Maximum tasks to return.

    Returns:
        Dict with success, tasks array, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✅ [bold cyan]Listing To Do tasks (limit: {limit})[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        params = {"$top": limit}
        if not include_completed:
            params["$filter"] = "status ne 'completed'"

        response = client.get(f"/me/todo/lists/{list_id}/tasks", params=params)
        tasks_data = response.get("value", [])

        tasks = [_format_todo_task(t) for t in tasks_data]
        emit_success(f"Found {len(tasks)} task(s)")

        return {
            "success": True,
            "tasks": tasks,
            "total_count": len(tasks),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_todo_tasks(agent: Any) -> Tool:
    """Register the msgraph_list_todo_tasks tool."""
    return agent.tool(msgraph_list_todo_tasks)


def msgraph_get_todo_task(ctx: RunContext, list_id: str, task_id: str) -> dict:
    """Get a specific To Do task.

    Args:
        list_id: The To Do list ID.
        task_id: The task ID.

    Returns:
        Dict with success, task details, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "✅ [bold cyan]Getting To Do task[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get(f"/me/todo/lists/{list_id}/tasks/{task_id}")

        task_data = _format_todo_task(response)
        emit_success(f"Retrieved task: {task_data.get('title')}")

        return {
            "success": True,
            "task": task_data,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_todo_task(agent: Any) -> Tool:
    """Register the msgraph_get_todo_task tool."""
    return agent.tool(msgraph_get_todo_task)


def msgraph_create_todo_task(
    ctx: RunContext,
    list_id: str,
    title: str,
    body: str | None = None,
    due_date: str | None = None,
    importance: str = "normal",
) -> dict:
    """Create a new To Do task.

    Args:
        list_id: The To Do list ID.
        title: Task title.
        body: Optional task body/notes.
        due_date: Optional due date (ISO format, e.g., "2025-12-25").
        importance: low, normal, or high.

    Returns:
        Dict with success, created task, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✅ [bold cyan]Creating To Do task: {title}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        task_data: dict[str, Any] = {
            "title": title,
            "importance": importance,
        }

        if body:
            task_data["body"] = {
                "content": body,
                "contentType": "text",
            }

        if due_date:
            task_data["dueDateTime"] = {
                "dateTime": due_date + "T00:00:00",
                "timeZone": "UTC",
            }

        response = client.post(f"/me/todo/lists/{list_id}/tasks", json=task_data)

        task = _format_todo_task(response)
        emit_success(f"Created task: {task.get('title')}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_todo_task(agent: Any) -> Tool:
    """Register the msgraph_create_todo_task tool."""
    return agent.tool(msgraph_create_todo_task)


def msgraph_update_todo_task(
    ctx: RunContext,
    list_id: str,
    task_id: str,
    title: str | None = None,
    body: str | None = None,
    due_date: str | None = None,
    importance: str | None = None,
    status: str | None = None,
) -> dict:
    """Update a To Do task.

    Args:
        list_id: The To Do list ID.
        task_id: The task ID.
        title: New title (optional).
        body: New body/notes (optional).
        due_date: New due date (optional).
        importance: New importance: low, normal, high (optional).
        status: New status: notStarted, inProgress, completed (optional).

    Returns:
        Dict with success, updated task, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "✅ [bold cyan]Updating To Do task[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        update_data: dict[str, Any] = {}

        if title:
            update_data["title"] = title
        if importance:
            update_data["importance"] = importance
        if status:
            update_data["status"] = status
        if body:
            update_data["body"] = {
                "content": body,
                "contentType": "text",
            }
        if due_date:
            update_data["dueDateTime"] = {
                "dateTime": due_date + "T00:00:00",
                "timeZone": "UTC",
            }

        response = client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}", json=update_data
        )

        task = _format_todo_task(response)
        emit_success(f"Updated task: {task.get('title')}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_update_todo_task(agent: Any) -> Tool:
    """Register the msgraph_update_todo_task tool."""
    return agent.tool(msgraph_update_todo_task)


def msgraph_complete_todo_task(ctx: RunContext, list_id: str, task_id: str) -> dict:
    """Mark a To Do task as completed.

    Args:
        list_id: The To Do list ID.
        task_id: The task ID.

    Returns:
        Dict with success, updated task, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "✅ [bold cyan]Completing To Do task[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.patch(
            f"/me/todo/lists/{list_id}/tasks/{task_id}", json={"status": "completed"}
        )

        task = _format_todo_task(response)
        emit_success(f"Completed task: {task.get('title')}")

        return {
            "success": True,
            "task": task,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_complete_todo_task(agent: Any) -> Tool:
    """Register the msgraph_complete_todo_task tool."""
    return agent.tool(msgraph_complete_todo_task)


def msgraph_delete_todo_task(ctx: RunContext, list_id: str, task_id: str) -> dict:
    """Delete a To Do task.

    Args:
        list_id: The To Do list ID.
        task_id: The task ID.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🗑️ [bold cyan]Deleting To Do task[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        client.delete(f"/me/todo/lists/{list_id}/tasks/{task_id}")

        emit_success("Task deleted successfully")

        return {
            "success": True,
            "message": "To Do task deleted",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_todo_task(agent: Any) -> Tool:
    """Register the msgraph_delete_todo_task tool."""
    return agent.tool(msgraph_delete_todo_task)
