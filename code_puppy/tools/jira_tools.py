"""Jira integration tools for Code Puppy.

Provides tools for searching, reading, creating, and updating Jira issues.
These tools are automatically available to agents when registered.

Example:
    # Agent can naturally say:
    # "Find open stories in the PROJ project"
    # "What's the status of PROJ-123?"
    # "Create a story for implementing user login"
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.jira_client import (
    JiraAPIError,
    JiraAuthError,
    JiraClient,
    JiraError,
    JiraNotFoundError,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_jira_client() -> JiraClient:
    """Get a Jira client instance."""
    return JiraClient()


def _handle_jira_error(e: Exception) -> dict[str, Any]:
    """Convert Jira exceptions to structured error responses."""
    if isinstance(e, JiraAuthError):
        error_msg = f"Authentication failed: {e}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
            "suggestion": "Run /jira_auth to refresh your session.",
        }
    elif isinstance(e, JiraNotFoundError):
        error_msg = f"Not found: {e}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, JiraAPIError):
        error_msg = f"API error: {e}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
    elif isinstance(e, JiraError):
        error_msg = f"Jira error: {e}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "jira",
        }
    else:
        error_msg = f"Unexpected error: {e}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
        }


def _format_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Format a Jira issue for readable output."""
    fields = issue.get("fields", {})
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "priority": fields.get("priority", {}).get("name"),
        "assignee": fields.get("assignee", {}).get("displayName")
        if fields.get("assignee")
        else None,
        "reporter": fields.get("reporter", {}).get("displayName")
        if fields.get("reporter")
        else None,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "description": fields.get("description"),
        "labels": fields.get("labels", []),
        "project": fields.get("project", {}).get("key"),
    }


def _format_issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    """Format a Jira issue for search results (minimal fields)."""
    fields = issue.get("fields", {})
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "assignee": fields.get("assignee", {}).get("displayName")
        if fields.get("assignee")
        else None,
    }


# =============================================================================
# JIRA SEARCH TOOL
# =============================================================================


def jira_search(
    ctx: RunContext,
    jql: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Search Jira issues using JQL (Jira Query Language).

    Args:
        ctx: PydanticAI run context.
        jql: JQL query string. Examples:
            - "project = PROJ" (all issues in project)
            - "project = PROJ AND status = Open" (open issues)
            - "assignee = currentUser()" (my issues)
            - "created >= -7d" (created in last 7 days)
            - "text ~ 'login'" (contains 'login')
        max_results: Maximum number of results (default: 20, max: 50).

    Returns:
        Dict with success status and list of formatted issues.

    Example JQL patterns:
        - Open bugs: "project = PROJ AND type = Bug AND status = Open"
        - My tasks: "assignee = currentUser() AND status != Done"
        - Recent: "project = PROJ AND created >= -7d ORDER BY created DESC"
        - By label: "project = PROJ AND labels = 'urgent'"
    """
    emit_info(
        f"\n[bold white on blue] JIRA SEARCH [/bold white on blue] "
        f"🔍 [bold cyan]{jql}[/bold cyan]"
    )

    try:
        with JiraClient() as client:
            # Cap max_results at 50 to avoid huge responses
            effective_max = min(max_results, 50)

            results = client.search_issues(
                jql=jql,
                max_results=effective_max,
                fields=["summary", "status", "issuetype", "assignee", "priority"],
            )

            issues = results.get("issues", [])
            total = results.get("total", len(issues))

            formatted_issues = [_format_issue_summary(issue) for issue in issues]

            emit_success(f"Found {total} issue(s), returning {len(formatted_issues)}")

            return {
                "success": True,
                "issues": formatted_issues,
                "total": total,
                "returned": len(formatted_issues),
                "jql": jql,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_search(agent: Any) -> Tool:
    """Register the jira_search tool with a PydanticAI agent."""
    return agent.tool(jira_search)


# =============================================================================
# JIRA GET ISSUE TOOL
# =============================================================================


def jira_get_issue(
    ctx: RunContext,
    issue_key: str,
) -> dict[str, Any]:
    """Get detailed information about a specific Jira issue.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").

    Returns:
        Dict with success status and full issue details.
    """
    emit_info(
        f"\n[bold white on blue] JIRA GET ISSUE [/bold white on blue] "
        f"📋 [bold cyan]{issue_key}[/bold cyan]"
    )

    try:
        with JiraClient() as client:
            issue = client.get_issue(issue_key)
            formatted = _format_issue(issue)

            emit_success(f"Retrieved issue: {issue_key}")

            return {
                "success": True,
                "issue": formatted,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_get_issue(agent: Any) -> Tool:
    """Register the jira_get_issue tool with a PydanticAI agent."""
    return agent.tool(jira_get_issue)


# =============================================================================
# JIRA CREATE ISSUE TOOL
# =============================================================================


def jira_create_issue(
    ctx: RunContext,
    project_key: str,
    issue_type: str,
    summary: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new Jira issue.

    Args:
        ctx: PydanticAI run context.
        project_key: Project key (e.g., "PROJ").
        issue_type: Issue type (e.g., "Story", "Bug", "Task", "Epic").
        summary: Issue title/summary.
        description: Detailed description (optional).

    Returns:
        Dict with success status and created issue key.
    """
    emit_info(
        f"\n[bold white on blue] JIRA CREATE ISSUE [/bold white on blue] "
        f"➕ [bold cyan]{project_key}[/bold cyan] - {issue_type}"
    )

    try:
        with JiraClient() as client:
            result = client.create_issue(
                project_key=project_key,
                issue_type=issue_type,
                summary=summary,
                description=description,
            )

            issue_key = result.get("key")
            emit_success(f"Created issue: {issue_key}")

            return {
                "success": True,
                "issue_key": issue_key,
                "issue_id": result.get("id"),
                "summary": summary,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_create_issue(agent: Any) -> Tool:
    """Register the jira_create_issue tool with a PydanticAI agent."""
    return agent.tool(jira_create_issue)


# =============================================================================
# JIRA ADD COMMENT TOOL
# =============================================================================


def jira_add_comment(
    ctx: RunContext,
    issue_key: str,
    comment: str,
) -> dict[str, Any]:
    """Add a comment to a Jira issue.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        comment: Comment text to add.

    Returns:
        Dict with success status.
    """
    emit_info(
        f"\n[bold white on blue] JIRA ADD COMMENT [/bold white on blue] "
        f"💬 [bold cyan]{issue_key}[/bold cyan]"
    )

    try:
        with JiraClient() as client:
            result = client.add_comment(issue_key, comment)
            comment_id = result.get("id")

            emit_success(f"Added comment to {issue_key}")

            return {
                "success": True,
                "issue_key": issue_key,
                "comment_id": comment_id,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_add_comment(agent: Any) -> Tool:
    """Register the jira_add_comment tool with a PydanticAI agent."""
    return agent.tool(jira_add_comment)


# =============================================================================
# JIRA UPDATE ISSUE TOOL
# =============================================================================


def jira_update_issue(
    ctx: RunContext,
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    assignee: str | None = None,
) -> dict[str, Any]:
    """Update fields on a Jira issue.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        summary: New summary/title (optional).
        description: New description (optional).
        assignee: New assignee username (optional).

    Returns:
        Dict with success status.
    """
    emit_info(
        f"\n[bold white on blue] JIRA UPDATE ISSUE [/bold white on blue] "
        f"✏️ [bold cyan]{issue_key}[/bold cyan]"
    )

    try:
        fields: dict[str, Any] = {}
        if summary:
            fields["summary"] = summary
        if description:
            fields["description"] = description
        if assignee:
            fields["assignee"] = {"name": assignee}

        if not fields:
            return {
                "success": False,
                "error": "No fields provided to update",
                "error_type": "validation",
            }

        with JiraClient() as client:
            client.update_issue(issue_key, fields=fields)

            emit_success(f"Updated issue: {issue_key}")

            return {
                "success": True,
                "issue_key": issue_key,
                "updated_fields": list(fields.keys()),
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_update_issue(agent: Any) -> Tool:
    """Register the jira_update_issue tool with a PydanticAI agent."""
    return agent.tool(jira_update_issue)


# =============================================================================
# JIRA TRANSITION ISSUE TOOL
# =============================================================================


def jira_transition_issue(
    ctx: RunContext,
    issue_key: str,
    status_name: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Transition a Jira issue to a new status.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        status_name: Target status name (e.g., "In Progress", "Done").
        comment: Optional comment to add with the transition.

    Returns:
        Dict with success status and available transitions if failed.
    """
    emit_info(
        f"\n[bold white on blue] JIRA TRANSITION [/bold white on blue] "
        f"🔄 [bold cyan]{issue_key}[/bold cyan] → {status_name}"
    )

    try:
        with JiraClient() as client:
            # Get available transitions
            transitions_data = client.get_transitions(issue_key)
            transitions = transitions_data.get("transitions", [])

            # Find matching transition (case-insensitive)
            target_transition = None
            for t in transitions:
                if t["name"].lower() == status_name.lower():
                    target_transition = t
                    break

            if not target_transition:
                available = [t["name"] for t in transitions]
                emit_warning(
                    f"Status '{status_name}' not available. "
                    f"Available: {', '.join(available)}"
                )
                return {
                    "success": False,
                    "error": f"Status '{status_name}' is not a valid transition",
                    "error_type": "invalid_transition",
                    "available_transitions": available,
                }

            # Execute transition
            client.transition_issue(
                issue_key,
                target_transition["id"],
                comment=comment,
            )

            emit_success(f"Transitioned {issue_key} to '{status_name}'")

            return {
                "success": True,
                "issue_key": issue_key,
                "new_status": status_name,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_transition_issue(agent: Any) -> Tool:
    """Register the jira_transition_issue tool with a PydanticAI agent."""
    return agent.tool(jira_transition_issue)


# =============================================================================
# JIRA GET COMMENTS TOOL
# =============================================================================


def jira_get_comments(
    ctx: RunContext,
    issue_key: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Get comments on a Jira issue.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        max_results: Maximum number of comments to return.

    Returns:
        Dict with success status and list of comments.
    """
    emit_info(
        f"\n[bold white on blue] JIRA GET COMMENTS [/bold white on blue] "
        f"💬 [bold cyan]{issue_key}[/bold cyan]"
    )

    try:
        with JiraClient() as client:
            result = client.get_comments(issue_key, max_results=max_results)
            comments = result.get("comments", [])

            formatted_comments = [
                {
                    "id": c.get("id"),
                    "author": c.get("author", {}).get("displayName"),
                    "body": c.get("body"),
                    "created": c.get("created"),
                }
                for c in comments
            ]

            emit_success(f"Retrieved {len(formatted_comments)} comment(s)")

            return {
                "success": True,
                "issue_key": issue_key,
                "comments": formatted_comments,
                "total": result.get("total", len(formatted_comments)),
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_get_comments(agent: Any) -> Tool:
    """Register the jira_get_comments tool with a PydanticAI agent."""
    return agent.tool(jira_get_comments)
