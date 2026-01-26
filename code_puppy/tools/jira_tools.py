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

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.jira_client import (
    JiraAPIError,
    JiraAuthError,
    JiraClient,
    JiraError,
    JiraNotFoundError,
)
from code_puppy.plugins.walmart_specific.jira_field_config import (
    get_application_service_field,
    get_epic_link_field,
    get_sprint_field,
    get_story_points_field,
)


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum character limit to prevent context blowout
MAX_CHARACTER_LIMIT = 30000


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_jira_client() -> JiraClient:
    """Get a Jira client instance.

    Returns:
        JiraClient: A configured Jira client ready for API calls.
    """
    return JiraClient()


def _parse_jql_error_suggestion(error_message: str) -> str | None:
    """Parse JQL error messages and return helpful suggestions.

    Args:
        error_message: The error message from Jira API.

    Returns:
        A helpful suggestion string, or None if no suggestion is available.
    """
    error_lower = error_message.lower()

    # Project name vs key confusion
    if "does not exist for the field 'project'" in error_lower:
        return (
            "It looks like you used a project NAME instead of project KEY. "
            "Project keys are short uppercase identifiers (e.g., 'PROJ', 'MYPROJ'). "
            "Use jira_list_projects to discover available project keys."
        )

    # Field doesn't exist
    if "field '" in error_lower and "does not exist" in error_lower:
        return (
            "The field name may be incorrect or need quoting. "
            'Custom fields with spaces need quotes: "Start Date" >= 2025-01-01. '
            "Check the exact field name in Jira."
        )

    # Value parsing issues (often unquoted values with spaces)
    if "error in the jql query" in error_lower or "unable to parse" in error_lower:
        return (
            "JQL syntax error. Common fixes: "
            '1) Quote values with spaces: status = "In Progress" '
            '2) Quote usernames: assignee = "john.doe" '
            "3) Use currentUser() for yourself (no quotes)"
        )

    # Invalid operator
    if "not a valid operator" in error_lower:
        return (
            "Invalid JQL operator. Common operators: "
            "= (equals), != (not equals), ~ (contains), "
            "IN (list), IS EMPTY, IS NOT EMPTY, >=, <="
        )

    # Function usage errors
    if "function" in error_lower and (
        "not found" in error_lower or "invalid" in error_lower
    ):
        return (
            "Check function syntax. Common functions: "
            "currentUser(), now(), startOfDay(), endOfDay(), "
            "startOfWeek(), startOfMonth()"
        )

    return None


def _handle_jira_error(e: Exception) -> dict[str, Any]:
    """Convert Jira exceptions to structured error responses.

    Provides intelligent suggestions based on common JQL errors to help
    users fix their queries.

    Args:
        e: The exception raised during Jira API operations.

    Returns:
        Dict containing:
            - success (bool): Always False for error responses.
            - error (str): Human-readable error message.
            - error_type (str): Category of error (authentication, not_found,
                api_error, jira, unknown).
            - suggestion (str, optional): Helpful suggestion to fix the issue.
    """
    if isinstance(e, JiraAuthError):
        error_msg = f"Authentication failed: {e}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
            "suggestion": "Use jira_authenticate to refresh your session.",
        }
    elif isinstance(e, JiraNotFoundError):
        error_msg = f"Not found: {e}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
            "suggestion": "Check that the issue key or resource exists.",
        }
    elif isinstance(e, JiraAPIError):
        error_msg = f"API error: {e}"
        emit_error(error_msg)

        # Try to provide a helpful suggestion based on the error
        suggestion = _parse_jql_error_suggestion(str(e))

        result: dict[str, Any] = {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
        if suggestion:
            result["suggestion"] = suggestion
            emit_warning(f"💡 Suggestion: {suggestion}")

        return result
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
    """Format a Jira issue for readable output.

    Args:
        issue: Raw Jira issue data from the API.

    Returns:
        Dict containing formatted issue fields:
            - key (str): Issue key (e.g., "PROJ-123").
            - summary (str): Issue title.
            - status (str): Current status name.
            - type (str): Issue type name.
            - priority (str): Priority level.
            - assignee (str | None): Assignee display name.
            - reporter (str | None): Reporter display name.
            - created (str): Creation timestamp.
            - updated (str): Last update timestamp.
            - description (str): Issue description.
            - labels (list[str]): List of labels.
            - components (list[str]): List of component names.
            - epic_link (str | None): Linked epic issue key.
            - sprint (dict | None): Current sprint info (id, name, state).
            - story_points (number | None): Story point estimate.
            - project (str): Project key.
            - application_service (str | None): Application/Service formatted as
                "Level1 -> Level2 -> Level3" (e.g., "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan").
                Falls back to the numeric ID if resolution fails.
    """
    fields = issue.get("fields", {})

    # Extract component names from the components array
    components = [c.get("name") for c in fields.get("components", []) if c.get("name")]

    # Epic link (configurable custom field)
    epic_link = fields.get(get_epic_link_field())

    # Sprint (configurable custom field - returns array of sprint objects)
    sprint_data = fields.get(get_sprint_field())
    sprint = None
    if sprint_data and isinstance(sprint_data, list) and len(sprint_data) > 0:
        # Get the most recent/active sprint (last in list)
        active_sprint = sprint_data[-1]
        if isinstance(active_sprint, dict):
            sprint = {
                "id": active_sprint.get("id"),
                "name": active_sprint.get("name"),
                "state": active_sprint.get("state"),
            }

    # Story Points (configurable custom field)
    story_points = fields.get(get_story_points_field())

    # Application/Service (configurable custom field)
    # Jira always returns either None (not set) or a list with either:
    # - 3 elements: resolved human-readable path ['Level1', 'Level2', 'Level3']
    # - 1 element: raw ID ['2125770'] (if resolution failed)
    application_service_raw = fields.get(get_application_service_field())
    application_service = None
    
    if application_service_raw and isinstance(application_service_raw, list):
        if len(application_service_raw) == 3:
            # Resolved path - format as "Level1 -> Level2 -> Level3"
            application_service = " -> ".join(application_service_raw)
        elif len(application_service_raw) == 1:
            # Raw ID - resolution failed, show the ID
            application_service = str(application_service_raw[0])

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
        "components": components,
        "epic_link": epic_link,
        "sprint": sprint,
        "story_points": story_points,
        "project": fields.get("project", {}).get("key"),
        "application_service": application_service,
    }


def _format_issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    """Format a Jira issue for search results (minimal fields).

    Args:
        issue: Raw Jira issue data from the API.

    Returns:
        Dict containing minimal issue fields for search results:
            - key (str): Issue key (e.g., "PROJ-123").
            - summary (str): Issue title.
            - status (str): Current status name.
            - type (str): Issue type name.
            - assignee (str | None): Assignee display name.
            - sprint (dict | None): Current sprint info (id, name, state).
            - epic_link (str | None): Linked epic issue key.
            - story_points (number | None): Story point estimate.
    """
    fields = issue.get("fields", {})

    # Sprint (configurable custom field - returns array of sprint objects)
    sprint_data = fields.get(get_sprint_field())
    sprint = None
    if sprint_data and isinstance(sprint_data, list) and len(sprint_data) > 0:
        active_sprint = sprint_data[-1]
        if isinstance(active_sprint, dict):
            sprint = {
                "id": active_sprint.get("id"),
                "name": active_sprint.get("name"),
                "state": active_sprint.get("state"),
            }

    return {
        "key": issue.get("key"),
        "summary": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "type": fields.get("issuetype", {}).get("name"),
        "assignee": fields.get("assignee", {}).get("displayName")
        if fields.get("assignee")
        else None,
        "sprint": sprint,
        "epic_link": fields.get(get_epic_link_field()),
        "story_points": fields.get(get_story_points_field()),
    }


def _parse_application_service_input(value: str | list[str]) -> list[str]:
    """Parse application_service input into a 3-element list.
    
    Args:
        value: Either a list of 3 strings or a delimited string.
               Supported delimiters: ' -> ', '.', '/', '|', '>'
               e.g. "Level1 -> Level2 -> Level3" or ["Level1", "Level2", "Level3"]
    
    Returns:
        A list of exactly 3 strings.
    
    Raises:
        ValueError: If the input cannot be parsed into exactly 3 elements.
    """
    if isinstance(value, list):
        if len(value) != 3:
            raise ValueError(
                f"Application/Service must have exactly 3 levels, got {len(value)}"
            )
        return value
    
    if isinstance(value, str):
        # Try different delimiters in order of likelihood
        delimiters = [' -> ', '.', '/', '|', '>']
        for delimiter in delimiters:
            if delimiter in value:
                parts = [part.strip() for part in value.split(delimiter)]
                if len(parts) == 3:
                    return parts
        
        raise ValueError(
            f"Application/Service string must contain exactly 3 levels separated by "
            f"' -> ', '.', '/', '|', or '>'. Got: {value}"
        )
    
    raise ValueError(
        f"Application/Service must be a list or string, got {type(value).__name__}"
    )


def _resolve_application_service_id(client: JiraClient, path: list[str], issue_id: str | None = None) -> str:
    """Resolve the Application/Service path to an ID.

    Args:
        client: The active JiraClient instance.
        path: A list of 3 strings representing the Application/Service path.
              e.g. ["EBS Finance Tech", "AP - Invoices and Payments", "Payables Insights Hub"]
        issue_id: Optional issue ID or key to use as context for fetching options.
                  If not provided, tries to fetch all options (may fail).

    Returns:
        The ID string for the selected option.

    Raises:
        ValueError: If the path is not found or invalid.
    """
    if len(path) != 3:
        raise ValueError("Application/Service path must contain exactly 3 levels.")

    # Fetch options from the nFeed/Elements Connect endpoint
    # If we have an issue_id, use it to get the full options list
    app_service_field = get_application_service_field()
    payload = {
        "customFieldId": app_service_field,
        "userInput": "",
        "view": "EDIT",
        "startIndex": 0,
    }
    
    # Add issue context if available (helps the API return complete results)
    if issue_id:
        payload["fieldContext"] = {"issueKeyOrId": issue_id}
    
    try:
        response = client._make_request(
            "POST",
            "/rest/nfeed/3.0/nFeed/field/input/options",
            json=payload,
        )
    except Exception as e:
        raise ValueError(f"Failed to fetch Application/Service options: {e}") from e

    # Extract options from the response
    options = response.get("options", [])

    for option in options:
        # The 'values' field contains the path strings [Level1, Level2, Level3]
        if option.get("values") == path:
            return str(option.get("id"))

    raise ValueError(f"Application/Service path not found: {path}")


def _resolve_application_service_name(
    client: JiraClient, issue_id: str, field_value: Any
) -> list[str] | None:
    """Resolve the Application/Service ID back to human-readable path.

    Args:
        client: The active JiraClient instance.
        issue_id: The Jira numeric issue ID (e.g., "28750593").
        field_value: The raw field value from Jira API.
                     Could be a dict like {"inputValues": ["20908383"]}
                     or a list like ["20908383"].

    Returns:
        A list of 3 strings representing the path, or None if not found/invalid.
    """
    if not field_value:
        return None

    # Extract the ID from various possible formats
    app_service_id = None
    if isinstance(field_value, dict):
        # Handle {"inputValues": ["20908383"]} format
        input_values = field_value.get("inputValues", [])
        if input_values and len(input_values) > 0:
            app_service_id = str(input_values[0])
    elif isinstance(field_value, list):
        # Handle direct list format ["20908383"]
        if field_value and len(field_value) > 0:
            app_service_id = str(field_value[0])
    elif isinstance(field_value, str):
        # Handle direct ID string
        app_service_id = field_value
    elif isinstance(field_value, (int, float)):
        # Handle numeric ID
        app_service_id = str(field_value)

    if not app_service_id:
        return None

    try:
        # Call the nFeed endpoint to get the human-readable name
        app_service_field = get_application_service_field()
        payload = {
            "customFieldId": app_service_field,
            "userInput": "",
            "view": "EDIT",
            "fieldContext": {"issueKeyOrId": issue_id},
            "startIndex": 0,
        }

        response = client._make_request(
            "POST",
            "/rest/nfeed/3.0/nFeed/field/input/options",
            json=payload,
        )

        # Extract the selected option from the response
        selected_options = response.get("selectedOptions", [])
        if selected_options and len(selected_options) > 0:
            values = selected_options[0].get("values")
            if values and len(values) == 3:
                return values

        # Fallback: search through all options if selectedOptions is empty
        options = response.get("options", [])
        for option in options:
            if str(option.get("id")) == app_service_id:
                values = option.get("values")
                if values and len(values) == 3:
                    return values

        return None
    except Exception:
        # If the lookup fails, return None instead of crashing
        return None


def _truncate_content(
    content: str,
    character_limit: int = 0,
    character_offset: int = 0,
) -> dict[str, Any]:
    """Truncate content with pagination support to prevent context blowout.

    This helper function implements the token guardrail pattern to prevent
    large content from overwhelming the LLM context window. It supports
    pagination through large content via offset and limit parameters.

    Args:
        content: The full content string to potentially truncate.
        character_limit: Maximum characters to return. Use 0 (default) to
            apply MAX_CHARACTER_LIMIT (30000). Values above MAX_CHARACTER_LIMIT
            are clamped to MAX_CHARACTER_LIMIT.
        character_offset: Starting character position for reading. Use this
            to paginate through large content. Negative values are treated as 0.
            Defaults to 0.

    Returns:
        dict[str, Any]: Truncation result containing:
            - content (str): The (possibly truncated) content slice.
            - total_content_length (int): Total length of the full content.
            - content_truncated (bool): True if more content exists beyond
                the returned slice.
            - remaining_content_length (int): Characters remaining after
                this chunk (0 if not truncated).
            - character_offset (int): The effective offset used for this read.
            - character_limit (int): The effective limit used for this read.

    Example:
        >>> result = _truncate_content("Hello, World!", character_limit=5)
        >>> result["content"]
        'Hello'
        >>> result["content_truncated"]
        True
        >>> result["remaining_content_length"]
        8
    """
    if not content:
        return {
            "content": "",
            "total_content_length": 0,
            "content_truncated": False,
            "remaining_content_length": 0,
            "character_offset": 0,
            "character_limit": MAX_CHARACTER_LIMIT,
        }

    total_content_length = len(content)

    # Determine effective limit: 0 means use max, otherwise clamp to max
    effective_limit = (
        MAX_CHARACTER_LIMIT
        if character_limit <= 0
        else min(character_limit, MAX_CHARACTER_LIMIT)
    )

    # Ensure offset is non-negative
    effective_offset = max(0, character_offset)

    # Slice the content
    content_end = effective_offset + effective_limit
    sliced_content = content[effective_offset:content_end]

    # Calculate truncation metadata
    content_truncated = content_end < total_content_length
    remaining_content_length = max(0, total_content_length - content_end)

    return {
        "content": sliced_content,
        "total_content_length": total_content_length,
        "content_truncated": content_truncated,
        "remaining_content_length": remaining_content_length,
        "character_offset": effective_offset,
        "character_limit": effective_limit,
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
        max_results: Maximum number of results to return. Defaults to 20.
            Values above 50 are capped to 50.

    Returns:
        dict[str, Any]: Search results containing:
            - success (bool): Whether the search succeeded.
            - issues (list[dict]): List of formatted issue summaries.
            - total (int): Total number of matching issues.
            - returned (int): Number of issues returned in this response.
            - jql (str): The JQL query used.
            - error (str, optional): Error message if search failed.
            - error_type (str, optional): Error category if search failed.

    Example:
        JQL patterns for common searches:
            - Open bugs: ``"project = PROJ AND type = Bug AND status = Open"``
            - My tasks: ``"assignee = currentUser() AND status != Done"``
            - Recent: ``"project = PROJ AND created >= -7d ORDER BY created DESC"``
            - By label: ``"project = PROJ AND labels = 'urgent'"``
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA SEARCH [/bold white on blue] "
            f"🔍 [bold cyan]{jql}[/bold cyan]"
        )
    )

    try:
        with JiraClient() as client:
            # Cap max_results at 50 to avoid huge responses
            effective_max = min(max_results, 50)

            # Include custom fields for sprint, epic link, and story points
            search_fields = [
                "summary",
                "status",
                "issuetype",
                "assignee",
                "priority",
                get_sprint_field(),
                get_epic_link_field(),
                get_story_points_field(),
            ]

            results = client.search_issues(
                jql=jql,
                max_results=effective_max,
                fields=search_fields,
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
    """Register the jira_search tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
    return agent.tool(jira_search)


# =============================================================================
# JIRA LIST PROJECTS TOOL
# =============================================================================


def jira_list_projects(
    ctx: RunContext,
    search_query: str | None = None,
    max_results: int = 20,
) -> dict[str, Any]:
    """List available Jira projects or search for projects by name.

    Use this tool to discover project KEYS before constructing JQL queries.
    Project keys are short uppercase identifiers (e.g., 'PROJ', 'MYPROJ')
    that should be used in JQL instead of long project names.

    IMPORTANT: When writing JQL, always use the project KEY, not the name:
        - CORRECT: project = PROJ
        - WRONG: project = "My Project Name"

    Args:
        ctx: PydanticAI run context.
        search_query: Optional search string to filter projects by name or key.
            If None, returns all projects (up to max_results).
        max_results: Maximum number of projects to return. Defaults to 20.
            Values above 50 are capped to 50.

    Returns:
        dict[str, Any]: Project list containing:
            - success (bool): Whether the request succeeded.
            - projects (list[dict]): List of projects with key, name, id.
            - total (int): Total number of matching projects.
            - hint (str): Reminder about using project keys in JQL.
            - error (str, optional): Error message if request failed.

    Example:
        # List all accessible projects
        jira_list_projects()

        # Search for projects containing "financial"
        jira_list_projects(search_query="financial")
    """
    action = f"searching for '{search_query}'" if search_query else "listing all"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA PROJECTS [/bold white on blue] "
            f"📊 [bold cyan]{action}[/bold cyan]"
        )
    )

    try:
        with JiraClient() as client:
            effective_max = min(max_results, 50)

            if search_query:
                results = client.search_projects(
                    query=search_query,
                    max_results=effective_max,
                )
            else:
                results = client.list_projects(
                    max_results=effective_max,
                )

            projects = results.get("projects", [])
            total = results.get("total", len(projects))

            emit_success(f"Found {total} project(s), returning {len(projects)}")

            return {
                "success": True,
                "projects": projects,
                "total": total,
                "returned": len(projects),
                "hint": (
                    "Use the 'key' field (e.g., 'PROJ') in JQL queries, "
                    "not the 'name' field. Example: project = PROJ"
                ),
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_list_projects(agent: Any) -> Tool:
    """Register the jira_list_projects tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
    return agent.tool(jira_list_projects)


# =============================================================================
# JIRA GET ISSUE TOOL
# =============================================================================


def jira_get_issue(
    ctx: RunContext,
    issue_key: str,
    character_limit: int = 0,
    character_offset: int = 0,
) -> dict[str, Any]:
    """Get detailed information about a specific Jira issue.

    Use character_limit and character_offset to paginate through large descriptions
    and avoid blowing out the LLM context window.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        character_limit: Maximum characters to return for the description field.
            Use 0 (default) to apply MAX_CHARACTER_LIMIT (30000). Values above
            30000 are clamped to 30000.
        character_offset: Starting character position for reading the description.
            Use this to paginate through large descriptions. Defaults to 0.

    Returns:
        dict[str, Any]: Issue details containing:
            - success (bool): Whether the retrieval succeeded.
            - issue (dict): Formatted issue data with (possibly truncated) description.
            - description_total_length (int): Total length of the full description.
            - description_truncated (bool): True if description was truncated.
            - description_remaining_length (int): Characters remaining after this chunk.
            - character_offset (int): The offset used for this read.
            - character_limit (int): The limit used for this read.
            - error (str, optional): Error message if retrieval failed.
            - error_type (str, optional): Error category if retrieval failed.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA GET ISSUE [/bold white on blue] "
            f"📋 [bold cyan]{issue_key}[/bold cyan]"
        )
    )

    try:
        with JiraClient() as client:
            # Explicitly request custom fields along with standard fields
            issue_fields = [
                "summary",
                "status",
                "issuetype",
                "priority",
                "assignee",
                "reporter",
                "created",
                "updated",
                "description",
                "labels",
                "components",
                "project",
                get_epic_link_field(),
                get_sprint_field(),
                get_story_points_field(),
                get_application_service_field(),
            ]
            issue = client.get_issue(issue_key, fields=issue_fields)
            
            # Resolve Application/Service ID to human-readable path
            app_service_field = get_application_service_field()
            raw_app_service = issue.get("fields", {}).get(app_service_field)
            if raw_app_service:
                try:
                    # Use the numeric issue ID (not the key) for the nFeed API
                    issue_id = issue.get("id")
                    resolved_path = _resolve_application_service_name(
                        client, issue_id, raw_app_service
                    )
                    if resolved_path:
                        # Replace raw value with human-readable path
                        issue["fields"][app_service_field] = resolved_path
                except Exception:
                    # If resolution fails, keep the raw value
                    pass
            
            formatted = _format_issue(issue)

            # Apply truncation guardrails to description
            description = formatted.get("description") or ""
            truncation_info = _truncate_content(
                description,
                character_limit=character_limit,
                character_offset=character_offset,
            )

            # Update formatted issue with truncated description
            formatted["description"] = truncation_info["content"]

            if truncation_info["content_truncated"]:
                emit_success(
                    f"Retrieved issue: {issue_key} "
                    f"(description: chars {truncation_info['character_offset']}-"
                    f"{truncation_info['character_offset'] + len(truncation_info['content'])} "
                    f"of {truncation_info['total_content_length']}, "
                    f"{truncation_info['remaining_content_length']} remaining)"
                )
            else:
                emit_success(f"Retrieved issue: {issue_key}")

            return {
                "success": True,
                "issue": formatted,
                "description_total_length": truncation_info["total_content_length"],
                "description_truncated": truncation_info["content_truncated"],
                "description_remaining_length": truncation_info[
                    "remaining_content_length"
                ],
                "character_offset": truncation_info["character_offset"],
                "character_limit": truncation_info["character_limit"],
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_get_issue(agent: Any) -> Tool:
    """Register the jira_get_issue tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
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
    labels: list[str] | None = None,
    components: list[str] | None = None,
    epic_link: str | None = None,
    sprint_id: int | None = None,
    story_points: int | float | None = None,
    application_service: str | list[str] | None = None,
) -> dict[str, Any]:
    """Create a new Jira issue.

    Args:
        ctx: PydanticAI run context.
        project_key: Project key (e.g., "PROJ").
        issue_type: Issue type name (e.g., "Story", "Bug", "Task", "Epic").
        summary: Issue title/summary.
        description: Detailed description. Defaults to None.
        labels: List of label strings to apply (e.g., ["backend", "urgent"]).
            Defaults to None.
        components: List of component names (e.g., ["API", "Frontend"]).
            Defaults to None.
        epic_link: Epic issue key to link this issue to (e.g., "PROJ-100").
            Only applies to non-Epic issue types. Defaults to None.
        sprint_id: Sprint ID to assign the issue to. Defaults to None.
        story_points: Story point estimate (e.g., 1, 2, 3, 5, 8). Defaults to None.
        application_service: Application/Service field value. Can be either:
            - A list of 3 strings: ["Level1", "Level2", "Level3"]
            - A delimited string: "Level1 -> Level2 -> Level3" (also supports '.', '/', '|', '>')
            e.g. ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"]
            or "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
            Defaults to None.

    Returns:
        dict[str, Any]: Creation result containing:
            - success (bool): Whether the creation succeeded.
            - issue_key (str): The created issue key (e.g., "PROJ-456").
            - issue_id (str): The created issue ID.
            - summary (str): The issue summary that was set.
            - labels (list[str], optional): Labels that were applied.
            - components (list[str], optional): Components that were applied.
            - epic_link (str, optional): Epic that was linked.
            - sprint_id (int, optional): Sprint that was assigned.
            - story_points (number, optional): Story points that were set.
            - application_service (list[str], optional): Application/Service set.
            - error (str, optional): Error message if creation failed.
            - error_type (str, optional): Error category if creation failed.
    """
    # Validate that Story and Bug issue types have application_service
    if issue_type in ["Story", "Bug"] and not application_service:
        error_msg = (
            f"The application_service field is required when creating a {issue_type}. "
            f"Please provide it as either a list: "
            f"['Level1', 'Level2', 'Level3'] or a delimited string: "
            f"'Level1 -> Level2 -> Level3' (also supports '.', '/', '|', '>')."
        )
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "validation",
        }

    # Build info message with optional fields
    info_parts = [f"➕ [bold cyan]{project_key}[/bold cyan] - {issue_type}"]
    if labels:
        info_parts.append(f"labels: {labels}")
    if components:
        info_parts.append(f"components: {components}")
    if epic_link:
        info_parts.append(f"epic: {epic_link}")
    if sprint_id:
        info_parts.append(f"sprint: {sprint_id}")
    if story_points is not None:
        info_parts.append(f"points: {story_points}")
    if application_service:
        info_parts.append(f"app/svc: {application_service}")

    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA CREATE ISSUE [/bold white on blue] "
            f"{' | '.join(info_parts)}"
        )
    )

    try:
        # Build extra fields for labels, components, and epic link
        extra_fields: dict[str, Any] = {}

        if labels:
            extra_fields["labels"] = labels

        if components:
            # Components require the {"name": "..."} format
            extra_fields["components"] = [{"name": c} for c in components]

        if epic_link:
            # Epic Link (configurable custom field)
            extra_fields[get_epic_link_field()] = epic_link

        if sprint_id is not None:
            # Sprint (configurable custom field)
            extra_fields[get_sprint_field()] = sprint_id

        if story_points is not None:
            # Story Points (configurable custom field)
            extra_fields[get_story_points_field()] = story_points

        with JiraClient() as client:
            if application_service:
                # Parse and normalize the input (handles both string and list formats)
                app_service_path = _parse_application_service_input(application_service)
                
                # To resolve the ID, we need an existing issue as context
                # Search for any recent issue in this project to use as template
                template_issue_id = None
                try:
                    search_results = client.search_issues(
                        jql=f"project = {project_key} ORDER BY created DESC",
                        max_results=1,
                        fields=["key"],
                    )
                    if search_results.get("issues"):
                        template_issue_id = search_results["issues"][0]["id"]
                except Exception:
                    # If we can't find a template issue, try without context
                    pass
                
                # Resolve the path to the numeric ID
                app_service_id = _resolve_application_service_id(
                    client, app_service_path, issue_id=template_issue_id
                )
                # Jira REST API expects just a list with the ID
                extra_fields[get_application_service_field()] = [app_service_id]
            
            result = client.create_issue(
                project_key=project_key,
                issue_type=issue_type,
                summary=summary,
                description=description,
                **extra_fields,
            )

            issue_key = result.get("key")
            emit_success(f"Created issue: {issue_key}")

            response: dict[str, Any] = {
                "success": True,
                "issue_key": issue_key,
                "issue_id": result.get("id"),
                "summary": summary,
            }

            # Include applied fields in response for confirmation
            if labels:
                response["labels"] = labels
            if components:
                response["components"] = components
            if epic_link:
                response["epic_link"] = epic_link
            if sprint_id is not None:
                response["sprint_id"] = sprint_id
            if story_points is not None:
                response["story_points"] = story_points
            if application_service:
                response["application_service"] = application_service

            return response

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_create_issue(agent: Any) -> Tool:
    """Register the jira_create_issue tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
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
        dict[str, Any]: Comment result containing:
            - success (bool): Whether the comment was added.
            - issue_key (str): The issue key that was commented on.
            - comment_id (str): The ID of the created comment.
            - error (str, optional): Error message if comment failed.
            - error_type (str, optional): Error category if comment failed.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA ADD COMMENT [/bold white on blue] "
            f"💬 [bold cyan]{issue_key}[/bold cyan]"
        )
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
    """Register the jira_add_comment tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
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
    labels: list[str] | None = None,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    components: list[str] | None = None,
    add_components: list[str] | None = None,
    remove_components: list[str] | None = None,
    epic_link: str | None = None,
    sprint_id: int | None = None,
    story_points: int | float | None = None,
    application_service: str | list[str] | None = None,
) -> dict[str, Any]:
    """Update fields on a Jira issue.

    At least one field must be provided. For labels and components, you can either:
    - Set them directly (replaces all existing values)
    - Use add_*/remove_* to incrementally modify

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        summary: New summary/title. Defaults to None (no change).
        description: New description. Defaults to None (no change).
        assignee: New assignee username. Defaults to None (no change).
        labels: Replace all labels with this list. Defaults to None (no change).
        add_labels: Labels to add (keeps existing). Defaults to None.
        remove_labels: Labels to remove. Defaults to None.
        components: Replace all components with this list. Defaults to None (no change).
        add_components: Components to add (keeps existing). Defaults to None.
        remove_components: Components to remove. Defaults to None.
        epic_link: Epic issue key to link to (e.g., "PROJ-100"). Defaults to None.
        sprint_id: Sprint ID to assign the issue to. Defaults to None.
        story_points: Story point estimate (e.g., 1, 2, 3, 5, 8). Defaults to None.
        application_service: Application/Service field value. Can be either:
            - A list of 3 strings: ["Level1", "Level2", "Level3"]
            - A delimited string: "Level1 -> Level2 -> Level3" (also supports '.', '/', '|', '>')
            e.g. ["EBS Finance Tech", "AP - Invoices and Payments", "Pay from Scan"]
            or "EBS Finance Tech -> AP - Invoices and Payments -> Pay from Scan"
            Defaults to None.

    Returns:
        dict[str, Any]: Update result containing:
            - success (bool): Whether the update succeeded.
            - issue_key (str): The issue key that was updated.
            - updated_fields (list[str]): List of field names that were updated.
            - error (str, optional): Error message if update failed.
            - error_type (str, optional): Error category if update failed.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA UPDATE ISSUE [/bold white on blue] "
            f"✏️ [bold cyan]{issue_key}[/bold cyan]"
        )
    )

    try:
        fields: dict[str, Any] = {}
        update: dict[str, Any] = {}
        updated_field_names: list[str] = []

        # Direct field updates
        if summary:
            fields["summary"] = summary
            updated_field_names.append("summary")
        if description:
            fields["description"] = description
            updated_field_names.append("description")
        if assignee:
            fields["assignee"] = {"name": assignee}
            updated_field_names.append("assignee")

        # Labels - either replace all or add/remove incrementally
        if labels is not None:
            fields["labels"] = labels
            updated_field_names.append("labels")
        else:
            label_ops = []
            if add_labels:
                label_ops.extend([{"add": lbl} for lbl in add_labels])
            if remove_labels:
                label_ops.extend([{"remove": lbl} for lbl in remove_labels])
            if label_ops:
                update["labels"] = label_ops
                updated_field_names.append("labels")

        # Components - either replace all or add/remove incrementally
        if components is not None:
            fields["components"] = [{"name": c} for c in components]
            updated_field_names.append("components")
        else:
            component_ops = []
            if add_components:
                component_ops.extend([{"add": {"name": c}} for c in add_components])
            if remove_components:
                component_ops.extend(
                    [{"remove": {"name": c}} for c in remove_components]
                )
            if component_ops:
                update["components"] = component_ops
                updated_field_names.append("components")

        # Epic link (configurable custom field)
        if epic_link is not None:
            fields[get_epic_link_field()] = epic_link
            updated_field_names.append("epic_link")

        # Sprint (configurable custom field)
        if sprint_id is not None:
            fields[get_sprint_field()] = sprint_id
            updated_field_names.append("sprint_id")

        # Story Points (configurable custom field)
        if story_points is not None:
            fields[get_story_points_field()] = story_points
            updated_field_names.append("story_points")

        if not fields and not update and not application_service:
            return {
                "success": False,
                "error": "No fields provided to update",
                "error_type": "validation",
            }

        with JiraClient() as client:
            if application_service:
                # Parse and normalize the input (handles both string and list formats)
                app_service_path = _parse_application_service_input(application_service)
                # Resolve the path to the numeric ID
                app_service_id = _resolve_application_service_id(
                    client, app_service_path
                )
                # Jira REST API expects just a list with the ID
                fields[get_application_service_field()] = [app_service_id]
                updated_field_names.append("application_service")

            client.update_issue(
                issue_key,
                fields=fields if fields else None,
                update=update if update else None,
            )

            emit_success(f"Updated issue: {issue_key}")

            return {
                "success": True,
                "issue_key": issue_key,
                "updated_fields": updated_field_names,
            }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_update_issue(agent: Any) -> Tool:
    """Register the jira_update_issue tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
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

    The status_name is matched case-insensitively against available transitions.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        status_name: Target status name (e.g., "In Progress", "Done").
            Matched case-insensitively.
        comment: Optional comment to add with the transition. Defaults to None.

    Returns:
        dict[str, Any]: Transition result containing:
            - success (bool): Whether the transition succeeded.
            - issue_key (str): The issue key that was transitioned.
            - new_status (str): The new status name (if successful).
            - available_transitions (list[str]): Available transition names
                (only present if transition failed due to invalid status).
            - error (str, optional): Error message if transition failed.
            - error_type (str, optional): Error category if transition failed.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA TRANSITION [/bold white on blue] "
            f"🔄 [bold cyan]{issue_key}[/bold cyan] → {status_name}"
        )
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
    """Register the jira_transition_issue tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
    return agent.tool(jira_transition_issue)


# =============================================================================
# JIRA GET COMMENTS TOOL
# =============================================================================


def jira_get_comments(
    ctx: RunContext,
    issue_key: str,
    max_results: int = 20,
    character_limit: int = 0,
    character_offset: int = 0,
) -> dict[str, Any]:
    """Get comments on a Jira issue.

    Use character_limit and character_offset to paginate through large comment bodies
    and avoid blowing out the LLM context window. The limit applies to the combined
    length of all comment bodies returned.

    Args:
        ctx: PydanticAI run context.
        issue_key: The issue key (e.g., "PROJ-123").
        max_results: Maximum number of comments to fetch from Jira. Defaults to 20.
        character_limit: Maximum total characters for all comment bodies combined.
            Use 0 (default) to apply MAX_CHARACTER_LIMIT (30000). Values above
            30000 are clamped to 30000.
        character_offset: Starting character position for reading combined comments.
            Use this to paginate through large comment threads. Defaults to 0.

    Returns:
        dict[str, Any]: Comments result containing:
            - success (bool): Whether the retrieval succeeded.
            - issue_key (str): The issue key that was queried.
            - comments (list[dict]): List of formatted comments (when not truncated).
                Each comment has: id, author, body, created.
            - comments_content (str): Combined comment content (when truncated or
                using offset). Format: "[Author] (date):\nBody\n\n---\n\n..."
            - total (int): Total number of comments on the issue.
            - comments_total_length (int): Total length of all comment bodies combined.
            - comments_truncated (bool): True if combined content was truncated.
            - comments_remaining_length (int): Characters remaining after this chunk.
            - character_offset (int): The offset used for this read.
            - character_limit (int): The limit used for this read.
            - error (str, optional): Error message if retrieval failed.
            - error_type (str, optional): Error category if retrieval failed.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] JIRA GET COMMENTS [/bold white on blue] "
            f"💬 [bold cyan]{issue_key}[/bold cyan]"
        )
    )

    try:
        with JiraClient() as client:
            result = client.get_comments(issue_key, max_results=max_results)
            comments = result.get("comments", [])

            # Build combined comment content for truncation
            # Format: "[Author] (date):\nBody\n\n---\n\n"
            combined_content_parts = []
            for c in comments:
                author = c.get("author", {}).get("displayName", "Unknown")
                created = c.get("created", "")
                body = c.get("body", "")
                combined_content_parts.append(f"[{author}] ({created}):\n{body}")

            combined_content = "\n\n---\n\n".join(combined_content_parts)

            # Apply truncation guardrails
            truncation_info = _truncate_content(
                combined_content,
                character_limit=character_limit,
                character_offset=character_offset,
            )

            # If truncated, we return the truncated combined content
            # Otherwise, return individual formatted comments
            if truncation_info["content_truncated"] or character_offset > 0:
                # Return as combined truncated content
                emit_success(
                    f"Retrieved comments for {issue_key} "
                    f"(chars {truncation_info['character_offset']}-"
                    f"{truncation_info['character_offset'] + len(truncation_info['content'])} "
                    f"of {truncation_info['total_content_length']}, "
                    f"{truncation_info['remaining_content_length']} remaining)"
                )

                return {
                    "success": True,
                    "issue_key": issue_key,
                    "comments_content": truncation_info["content"],
                    "total": result.get("total", len(comments)),
                    "comments_total_length": truncation_info["total_content_length"],
                    "comments_truncated": truncation_info["content_truncated"],
                    "comments_remaining_length": truncation_info[
                        "remaining_content_length"
                    ],
                    "character_offset": truncation_info["character_offset"],
                    "character_limit": truncation_info["character_limit"],
                }
            else:
                # Return individual formatted comments (no truncation needed)
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
                    "comments_total_length": truncation_info["total_content_length"],
                    "comments_truncated": False,
                    "comments_remaining_length": 0,
                    "character_offset": 0,
                    "character_limit": truncation_info["character_limit"],
                }

    except Exception as e:
        return _handle_jira_error(e)


def register_jira_get_comments(agent: Any) -> Tool:
    """Register the jira_get_comments tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance to register the tool with.

    Returns:
        Tool: The registered Tool instance.
    """
    return agent.tool(jira_get_comments)


# =============================================================================
# AUTHENTICATION TOOL
# =============================================================================


def jira_authenticate(ctx: RunContext) -> dict[str, Any]:
    """Launch Jira authentication flow.

    Opens a browser window for the user to sign in with their Walmart SSO.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with Jira.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on green] JIRA [/bold white on green] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        from code_puppy.plugins.walmart_specific.jira_auth import (
            handle_jira_auth_command,
        )

        result = handle_jira_auth_command("/jira_auth", "jira_auth")

        if result and "successful" in result.lower():
            emit_success("Jira authentication completed successfully!")
            return {
                "success": True,
                "message": "Jira authentication successful. You can now retry your previous request.",
            }
        else:
            return {
                "success": False,
                "error": result or "Authentication did not complete",
            }

    except Exception as e:
        error_msg = f"Authentication failed: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
        }


def register_jira_authenticate(agent: Any) -> Tool:
    """Register the jira_authenticate tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(jira_authenticate)