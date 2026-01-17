"""ServiceNow Knowledge Base integration tools for Code Puppy.

Provides tools for searching and reading ServiceNow Knowledge Base articles,
converting HTML content to markdown for easier consumption.
"""

import re
from typing import Any, List

from markdownify import markdownify as md
from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.servicenow_client import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowClient,
    ServiceNowError,
    ServiceNowNotFoundError,
)


# ============================================================================
# Constants
# ============================================================================

SERVICENOW_BASE_URL = "https://walmartglobal.service-now.com"
MAX_CHARACTER_LIMIT = 30000


# ============================================================================
# Helper Functions
# ============================================================================


def get_servicenow_client() -> ServiceNowClient:
    """Get a ServiceNow client instance.

    Returns:
        ServiceNowClient: A configured ServiceNow client
    """
    return ServiceNowClient()


def _convert_html_to_markdown(html_content: str) -> str:
    """Convert HTML content to markdown.

    Args:
        html_content: HTML content from ServiceNow article

    Returns:
        Markdown-formatted string
    """
    if not html_content:
        return ""

    # Use markdownify to convert HTML to markdown
    markdown = md(html_content, heading_style="ATX", strip=["script", "style"])
    return markdown.strip()


def _clean_text(text: str | None) -> str:
    """Clean text content by removing excess whitespace.

    Args:
        text: Raw text content

    Returns:
        Cleaned text string
    """
    if not text:
        return ""
    # Remove excess whitespace and normalize line breaks
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_search_result(result: dict) -> dict:
    """Format a single search result for better readability.

    Args:
        result: Raw search result from ServiceNow API

    Returns:
        Formatted dict with essential information
    """
    sys_id = result.get("sys_id", "")
    number = result.get("number", "")

    # kb_category can be a dict with display_value or a string
    kb_category = result.get("kb_category", "")
    if isinstance(kb_category, dict):
        kb_category = kb_category.get("display_value", "")
    
    kb_base = result.get("kb_knowledge_base", "")
    if isinstance(kb_base, dict):
        kb_base = kb_base.get("display_value", "")
    
    return {
        "sys_id": sys_id,
        "number": number,
        "title": result.get("short_description", ""),
        "category": kb_category,
        "knowledge_base": kb_base,
        "workflow_state": result.get("workflow_state", ""),
        "url": f"{SERVICENOW_BASE_URL}/kb_view.do?sysparm_article={number}" if number else "",
        "excerpt": _clean_text(result.get("text", ""))[:300] + "..." if result.get("text") else "",
    }


def _handle_servicenow_error(e: Exception) -> dict:
    """Convert ServiceNow exceptions to structured error responses.

    Args:
        e: Exception raised by ServiceNow client

    Returns:
        Dict with success=False and error details
    """
    error_str = str(e)
    
    # Check for validation/mandatory field errors and provide helpful guidance
    retry_hint = None
    if "mandatory" in error_str.lower() or "required" in error_str.lower():
        retry_hint = (
            "This error indicates missing required fields. Try different variable names "
            "(e.g., 'group_name' vs 'groupname' vs 'ad_group_name'). "
            "You can also try submitting with all the variables the user provided."
        )
    elif "invalid" in error_str.lower() or "validation" in error_str.lower():
        retry_hint = (
            "This error indicates invalid field values. Check the variable names and values. "
            "Try using sys_id values instead of display names for reference fields."
        )
    
    if isinstance(e, ServiceNowAuthError):
        error_msg = f"Authentication failed: {error_str}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
            "retry_hint": "Use servicenow_authenticate() to re-authenticate, then retry.",
        }
    elif isinstance(e, ServiceNowNotFoundError):
        error_msg = f"Resource not found: {error_str}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, ServiceNowAPIError):
        error_msg = f"API error: {error_str}"
        emit_error(error_msg)
        result = {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
            "raw_error": error_str,  # Include full error for debugging
        }
        if retry_hint:
            result["retry_hint"] = retry_hint
        return result
    elif isinstance(e, ServiceNowError):
        error_msg = f"ServiceNow error: {error_str}"
        emit_error(error_msg)
        result = {
            "success": False,
            "error": error_msg,
            "error_type": "servicenow",
            "raw_error": error_str,
        }
        if retry_hint:
            result["retry_hint"] = retry_hint
        return result
    else:
        error_msg = f"Unexpected error: {error_str}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
            "raw_error": error_str,
        }


# ============================================================================
# ServiceNow KB Search Tool
# ============================================================================


def servicenow_kb_search(
    ctx: RunContext,
    query: str,
    limit: int = 10,
    workflow_state: str = "published",
) -> dict:
    """Search ServiceNow Knowledge Base for articles.

    Args:
        ctx: PydanticAI run context
        query: Search query string
        limit: Maximum number of results to return (default: 10, max: 100)
        workflow_state: Filter by workflow state (default: "published")

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of formatted search results
            - total_count (int): Total number of results found
            - error (str, optional): Error message if search failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW KB SEARCH [/bold white on green] "
            f"🔍 [bold cyan]'{query}'[/bold cyan]"
        )
    )

    try:
        client = ServiceNowClient()
        raw_results = client.search_kb_articles(
            query=query,
            limit=limit,
            workflow_state=workflow_state,
        )

        # Format results for better readability
        formatted_results = [
            _format_search_result(result)
            for result in raw_results.get("result", [])
        ]

        total_count = len(formatted_results)

        emit_success(
            f"Found {total_count} result(s), returning {len(formatted_results)}"
        )

        return {
            "success": True,
            "results": formatted_results,
            "total_count": total_count,
            "query": query,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_kb_search(agent: Any) -> Tool:
    """Register the servicenow_kb_search tool with a PydanticAI agent."""
    return agent.tool(servicenow_kb_search)


# ============================================================================
# ServiceNow KB Read Article Tool
# ============================================================================


def servicenow_kb_read_article(
    ctx: RunContext,
    article_id: str,
    character_limit: int = 0,
    character_offset: int = 0,
) -> dict:
    """Read the content of a ServiceNow Knowledge Base article.

    Use character_limit and character_offset to paginate through large articles
    and avoid blowing out the LLM context window.

    Args:
        ctx: PydanticAI run context
        article_id: The article sys_id OR article number (e.g., "KB0012345")
        character_limit: Maximum characters to return (0 = use default max of 30000)
        character_offset: Starting character position for reading (default: 0)

    Returns:
        Dict containing:
            - success (bool): Whether the read succeeded
            - article_id (str): The article ID
            - number (str): KB article number
            - title (str): Article title
            - content (str): Article content in markdown format
            - category (str): Article category
            - url (str): Web URL to the article
            - total_content_length (int): Total length of full content
            - content_truncated (bool): Whether content was truncated
            - remaining_content_length (int): Characters remaining after this chunk
            - error (str, optional): Error message if read failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on green] SERVICENOW KB READ [/bold white on green] "
            f"📄 [bold cyan]{article_id}[/bold cyan]"
        )
    )

    try:
        client = ServiceNowClient()

        # Determine if this is a sys_id or article number
        if article_id.upper().startswith("KB"):
            # It's an article number
            raw_result = client.get_kb_article_by_number(article_id)
            if not raw_result.get("result"):
                return {
                    "success": False,
                    "error": f"Article not found: {article_id}",
                    "error_type": "not_found",
                }
            article_data = raw_result["result"][0]
        else:
            # It's a sys_id
            raw_result = client.get_kb_article_by_id(article_id)
            article_data = raw_result.get("result", {})

        # Extract and convert content
        html_content = article_data.get("text", "")
        full_markdown_content = _convert_html_to_markdown(html_content)

        # Calculate content length and apply limits
        total_content_length = len(full_markdown_content)

        effective_limit = (
            MAX_CHARACTER_LIMIT
            if character_limit <= 0
            else min(character_limit, MAX_CHARACTER_LIMIT)
        )
        effective_offset = max(0, character_offset)

        # Slice the content
        content_end = effective_offset + effective_limit
        sliced_content = full_markdown_content[effective_offset:content_end]

        # Calculate truncation metadata
        content_truncated = content_end < total_content_length
        remaining_content_length = max(0, total_content_length - content_end)

        # Extract metadata
        number = article_data.get("number", "")
        title = article_data.get("short_description", "Untitled")
        category = article_data.get("category", "")
        workflow_state = article_data.get("workflow_state", "")
        url = f"{SERVICENOW_BASE_URL}/kb_view.do?sysparm_article={number}" if number else ""

        if content_truncated:
            emit_success(
                f"Successfully read article: '{title}' "
                f"(showing chars {effective_offset}-{content_end} of {total_content_length}, "
                f"{remaining_content_length} remaining)"
            )
        else:
            emit_success(f"Successfully read article: '{title}'")

        return {
            "success": True,
            "article_id": article_data.get("sys_id", article_id),
            "number": number,
            "title": title,
            "content": sliced_content,
            "category": category,
            "workflow_state": workflow_state,
            "url": url,
            "total_content_length": total_content_length,
            "content_truncated": content_truncated,
            "remaining_content_length": remaining_content_length,
            "character_offset": effective_offset,
            "character_limit": effective_limit,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_kb_read_article(agent: Any) -> Tool:
    """Register the servicenow_kb_read_article tool with a PydanticAI agent."""
    return agent.tool(servicenow_kb_read_article)


# ============================================================================
# ServiceNow KB Search by Category Tool
# ============================================================================


def servicenow_kb_search_by_category(
    ctx: RunContext,
    category: str,
    query: str = "",
    limit: int = 10,
) -> dict:
    """Search for Knowledge Base articles within a specific category.

    Args:
        ctx: PydanticAI run context
        category: The category name or ID to search within
        query: Optional search query string (default: "" returns all in category)
        limit: Maximum number of results to return (default: 10)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of formatted search results
            - total_count (int): Total number of results found
            - category (str): The category searched
            - query (str): The query used
            - error (str, optional): Error message if search failed
    """
    if query:
        emit_info(
            Text.from_markup(
                f"\n[bold white on green] SERVICENOW KB CATEGORY [/bold white on green] "
                f"📁 [bold cyan]{category}[/bold cyan] [dim]for '{query}'[/dim]"
            )
        )
    else:
        emit_info(
            Text.from_markup(
                f"\n[bold white on green] SERVICENOW KB CATEGORY [/bold white on green] "
                f"📁 [bold cyan]{category}[/bold cyan]"
            )
        )

    try:
        client = ServiceNowClient()
        raw_results = client.search_kb_by_category(
            category=category,
            query=query,
            limit=limit,
        )

        # Format results for better readability
        formatted_results = [
            _format_search_result(result)
            for result in raw_results.get("result", [])
        ]

        total_count = len(formatted_results)

        emit_success(
            f"Found {total_count} result(s) in category '{category}', "
            f"returning {len(formatted_results)}"
        )

        return {
            "success": True,
            "results": formatted_results,
            "total_count": total_count,
            "category": category,
            "query": query,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_kb_search_by_category(agent: Any) -> Tool:
    """Register the servicenow_kb_search_by_category tool."""
    return agent.tool(servicenow_kb_search_by_category)


# =============================================================================
# AUTHENTICATION TOOL
# =============================================================================


def servicenow_authenticate(ctx: RunContext) -> dict[str, Any]:
    """Launch ServiceNow authentication flow.

    Opens a browser window for the user to sign in with their Walmart SSO.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with ServiceNow.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on green] SERVICENOW [/bold white on green] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        from code_puppy.plugins.walmart_specific.servicenow_auth import (
            handle_servicenow_auth_command,
        )

        result = handle_servicenow_auth_command("/servicenow_auth", "servicenow_auth")

        if result and "successful" in result.lower():
            emit_success("ServiceNow authentication completed successfully!")
            return {
                "success": True,
                "message": "ServiceNow authentication successful. You can now retry your previous request.",
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


def register_servicenow_authenticate(agent: Any) -> Tool:
    """Register the servicenow_authenticate tool with a PydanticAI agent."""
    return agent.tool(servicenow_authenticate)


# ============================================================================
# ServiceNow Incident Creation Tool
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
        description: Detailed description of the incident
        urgency: Urgency level (1=High, 2=Medium, 3=Low). Default: 3
        impact: Impact level (1=High, 2=Medium, 3=Low). Default: 3
        category: Incident category (e.g., "Software", "Hardware", "Network")
        subcategory: Incident subcategory
        assignment_group: Name of the assignment group to route the incident to.
                          Use servicenow_search_assignment_groups to find groups.
        assigned_to: Username or sys_id of a specific user to assign the incident to.
                     Use servicenow_search_users to find the right person.
        caller_id: Username or sys_id of the person reporting the incident.
                   Defaults to the current user if not specified.
        contact_type: Channel/method of contact. Common values:
                      "phone", "email", "self-service", "chat", "walk-in", "virtual_agent"
        cmdb_ci: Configuration Item - name or sys_id of the affected CI/application.
                 This links the incident to a specific system in the CMDB.
        additional_fields: Dictionary of any additional ServiceNow incident fields.
                          Common additional fields include:
                          - priority: Override calculated priority (1-5)
                          - state: Incident state (1=New, 2=In Progress, 3=On Hold, 6=Resolved, 7=Closed)
                          - work_notes: Internal work notes (not visible to caller)
                          - comments: Customer-visible comments
                          - business_service: Affected business service
                          - service_offering: Service offering
                          - location: Location name or sys_id
                          - opened_by: User who opened the incident
                          - close_code: Resolution code (for resolved/closed)
                          - close_notes: Resolution notes (for resolved/closed)
                          - parent_incident: Parent incident for related incidents
                          - problem_id: Related problem record
                          - rfc: Related change request
                          - u_*: Any custom fields (check your ServiceNow instance)
        dry_run: If True, validate and preview the incident without actually creating it.
                 Use this to test the integration safely. Default: False

    Returns:
        Dict containing:
            - success (bool): Whether the incident was created (or would be created in dry_run)
            - incident_number (str): The incident number (e.g., INC0012345)
            - sys_id (str): The incident sys_id
            - url (str): Web URL to view the incident
            - state (str): Current incident state
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if creation failed
    """
    mode_label = "DRY RUN" if dry_run else "CREATE INCIDENT"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW {mode_label} [/bold white on blue] "
            f"\ud83d\udcdd [bold cyan]'{short_description[:50]}...'[/bold cyan]"
        )
    )

    # Build the payload for preview or submission
    payload = {
        "short_description": short_description,
        "description": description,
        "urgency": urgency,
        "impact": impact,
        "category": category,
        "subcategory": subcategory,
        "assignment_group": assignment_group,
        "assigned_to": assigned_to,
        "caller_id": caller_id,
        "contact_type": contact_type,
        "cmdb_ci": cmdb_ci,
    }

    # In dry_run mode, just return what would be submitted
    if dry_run:
        urgency_labels = {1: "High", 2: "Medium", 3: "Low"}
        impact_labels = {1: "High", 2: "Medium", 3: "Low"}
        
        preview = {
            "short_description": short_description,
            "description": description,
            "urgency": f"{urgency} ({urgency_labels.get(urgency, 'Unknown')})",
            "impact": f"{impact} ({impact_labels.get(impact, 'Unknown')})",
            "category": category or "(not specified)",
            "subcategory": subcategory or "(not specified)",
            "assignment_group": assignment_group or "(auto-assign)",
            "assigned_to": assigned_to or "(not assigned)",
            "caller_id": caller_id or "(current user)",
            "contact_type": contact_type or "(not specified)",
            "cmdb_ci": cmdb_ci or "(not specified)",
        }
        
        # Include additional fields in preview if provided
        if additional_fields:
            preview["additional_fields"] = additional_fields
        
        emit_success("Dry run complete - incident NOT created")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually create the incident.",
            "preview": preview,
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

        # Build URL to view the incident
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}"

        emit_success(f"Created incident: {incident_number}")

        return {
            "success": True,
            "dry_run": False,
            "incident_number": incident_number,
            "sys_id": sys_id,
            "url": url,
            "state": incident_data.get("state", ""),
            "priority": incident_data.get("priority", ""),
            "short_description": incident_data.get("short_description", ""),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_create_incident(agent: Any) -> Tool:
    """Register the servicenow_create_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_create_incident)


# ============================================================================
# ServiceNow Get Incident Tool
# ============================================================================


def _extract_display_value(field_data) -> str:
    """Extract display value from a ServiceNow field that may be a dict or string."""
    if isinstance(field_data, dict):
        return field_data.get("display_value", field_data.get("value", ""))
    return field_data or ""


def servicenow_get_incident(
    ctx: RunContext,
    incident_id: str,
) -> dict:
    """Get details of a ServiceNow incident.

    Args:
        ctx: PydanticAI run context
        incident_id: The incident number (e.g., INC0012345) or sys_id

    Returns:
        Dict containing all incident fields including:
            - success (bool): Whether the incident was found
            - incident_number (str): The incident number (e.g., INC0012345)
            - sys_id (str): The incident sys_id
            - short_description (str): Brief summary
            - description (str): Full description
            - state (str): Current state (New, In Progress, Resolved, etc.)
            - priority (str): Priority level (1-5)
            - urgency (str): Urgency level (1=High, 2=Medium, 3=Low)
            - impact (str): Impact level (1=High, 2=Medium, 3=Low)
            - category (str): Incident category
            - subcategory (str): Incident subcategory
            - assignment_group (str): The assigned group
            - assigned_to (str): Who is working on it
            - caller_id (str): Who reported the incident
            - contact_type (str): Channel (phone, email, self-service, etc.)
            - cmdb_ci (str): Configuration Item (affected system)
            - opened_by (str): Who opened the incident
            - resolved_by (str): Who resolved the incident (if resolved)
            - close_code (str): Resolution code (if closed)
            - close_notes (str): Resolution notes (if closed)
            - work_notes (str): Latest work notes
            - comments (str): Latest comments
            - created_on (str): When the incident was created
            - updated_on (str): When the incident was last updated
            - resolved_at (str): When the incident was resolved
            - closed_at (str): When the incident was closed
            - url (str): Web URL to view the incident
            - error (str, optional): Error message if lookup failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GET INCIDENT [/bold white on blue] "
            f"🔍 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_incident(incident_id)

        # Handle list response (when searching by number)
        if "result" in result:
            if isinstance(result["result"], list):
                if not result["result"]:
                    return {
                        "success": False,
                        "error": f"Incident not found: {incident_id}",
                        "error_type": "not_found",
                    }
                incident_data = result["result"][0]
            else:
                incident_data = result["result"]
        else:
            return {
                "success": False,
                "error": f"Unexpected response format for incident: {incident_id}",
                "error_type": "api_error",
            }

        sys_id = incident_data.get("sys_id", "")
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}"

        emit_success(f"Found incident: {incident_data.get('number', incident_id)}")

        return {
            "success": True,
            # Identifiers
            "incident_number": incident_data.get("number", ""),
            "sys_id": sys_id,
            "url": url,
            # Core details
            "short_description": incident_data.get("short_description", ""),
            "description": incident_data.get("description", ""),
            # Status & Priority
            "state": _extract_display_value(incident_data.get("state", "")),
            "priority": _extract_display_value(incident_data.get("priority", "")),
            "urgency": _extract_display_value(incident_data.get("urgency", "")),
            "impact": _extract_display_value(incident_data.get("impact", "")),
            # Classification
            "category": _extract_display_value(incident_data.get("category", "")),
            "subcategory": _extract_display_value(incident_data.get("subcategory", "")),
            # Assignment
            "assignment_group": _extract_display_value(incident_data.get("assignment_group", "")),
            "assigned_to": _extract_display_value(incident_data.get("assigned_to", "")),
            # Caller & Contact
            "caller_id": _extract_display_value(incident_data.get("caller_id", "")),
            "contact_type": _extract_display_value(incident_data.get("contact_type", "")),
            # Configuration Item
            "cmdb_ci": _extract_display_value(incident_data.get("cmdb_ci", "")),
            # People
            "opened_by": _extract_display_value(incident_data.get("opened_by", "")),
            "resolved_by": _extract_display_value(incident_data.get("resolved_by", "")),
            # Resolution
            "close_code": _extract_display_value(incident_data.get("close_code", "")),
            "close_notes": incident_data.get("close_notes", ""),
            # Notes (latest only - full history requires separate API call)
            "work_notes": incident_data.get("work_notes", ""),
            "comments": incident_data.get("comments", ""),
            # Timestamps
            "created_on": incident_data.get("sys_created_on", ""),
            "updated_on": incident_data.get("sys_updated_on", ""),
            "resolved_at": incident_data.get("resolved_at", ""),
            "closed_at": incident_data.get("closed_at", ""),
            # Business context
            "business_service": _extract_display_value(incident_data.get("business_service", "")),
            "service_offering": _extract_display_value(incident_data.get("service_offering", "")),
            "location": _extract_display_value(incident_data.get("location", "")),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_get_incident(agent: Any) -> Tool:
    """Register the servicenow_get_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_incident)


# ============================================================================
# ServiceNow List My Incidents Tool
# ============================================================================


def servicenow_list_my_incidents(
    ctx: RunContext,
    state: str = "",
    limit: int = 10,
) -> dict:
    """List incidents assigned to or opened by the current user.

    Args:
        ctx: PydanticAI run context
        state: Filter by state ("new", "in_progress", "resolved", "closed", or state number)
        limit: Maximum number of incidents to return (default: 10, max: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - incidents (list): List of incident summaries
            - total_count (int): Number of incidents returned
            - error (str, optional): Error message if query failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] SERVICENOW MY INCIDENTS [/bold white on blue] "
            "📋 [bold cyan]Listing your incidents...[/bold cyan]"
        )
    )

    # Map friendly state names to ServiceNow state values
    state_map = {
        "new": "1",
        "in_progress": "2",
        "on_hold": "3",
        "resolved": "6",
        "closed": "7",
        "canceled": "8",
    }
    
    state_value = state_map.get(state.lower().replace(" ", "_"), state) if state else ""

    try:
        client = get_servicenow_client()
        result = client.list_my_incidents(
            state=state_value,
            limit=min(limit, 50),
        )

        incidents = []
        for inc in result.get("result", []):
            # Extract display values for reference fields
            assigned_to = inc.get("assigned_to", "")
            if isinstance(assigned_to, dict):
                assigned_to = assigned_to.get("display_value", "")

            assignment_group = inc.get("assignment_group", "")
            if isinstance(assignment_group, dict):
                assignment_group = assignment_group.get("display_value", "")

            sys_id = inc.get("sys_id", "")
            incidents.append({
                "incident_number": inc.get("number", ""),
                "sys_id": sys_id,
                "short_description": inc.get("short_description", ""),
                "state": inc.get("state", ""),
                "priority": inc.get("priority", ""),
                "assigned_to": assigned_to,
                "assignment_group": assignment_group,
                "created_on": inc.get("sys_created_on", ""),
                "url": f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}",
            })

        emit_success(f"Found {len(incidents)} incident(s)")

        return {
            "success": True,
            "incidents": incidents,
            "total_count": len(incidents),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_list_my_incidents(agent: Any) -> Tool:
    """Register the servicenow_list_my_incidents tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_my_incidents)


# ============================================================================
# ServiceNow Add Incident Comment Tool
# ============================================================================


def servicenow_add_incident_comment(
    ctx: RunContext,
    incident_id: str,
    comment: str,
    work_notes: bool = False,
    dry_run: bool = False,
) -> dict:
    """Add a comment or work note to an incident.

    Args:
        ctx: PydanticAI run context
        incident_id: The incident number (e.g., INC0012345) or sys_id
        comment: The comment text to add
        work_notes: If True, add as work notes (internal only).
                   If False, add as comments (visible to requester).
        dry_run: If True, preview the comment without actually adding it.
                 Use this to test the integration safely. Default: False

    Returns:
        Dict containing:
            - success (bool): Whether the comment was added (or would be in dry_run)
            - incident_number (str): The incident number
            - message (str): Confirmation message
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if update failed
    """
    comment_type = "work note" if work_notes else "comment"
    mode_label = "DRY RUN" if dry_run else f"ADD {comment_type.upper()}"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW {mode_label} [/bold white on blue] "
            f"\ud83d\udcac [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    # In dry_run mode, just return what would be submitted
    if dry_run:
        emit_success(f"Dry run complete - {comment_type} NOT added")
        return {
            "success": True,
            "dry_run": True,
            "message": f"This is a preview. Set dry_run=False to actually add the {comment_type}.",
            "preview": {
                "incident_id": incident_id,
                "comment_type": comment_type,
                "comment": comment[:500] + ("..." if len(comment) > 500 else ""),
            },
        }

    try:
        client = get_servicenow_client()

        # If incident_id is a number, we need to get the sys_id first
        sys_id = incident_id
        if incident_id.upper().startswith("INC"):
            inc_result = client.get_incident(incident_id)
            if inc_result.get("result"):
                if isinstance(inc_result["result"], list):
                    if not inc_result["result"]:
                        return {
                            "success": False,
                            "error": f"Incident not found: {incident_id}",
                            "error_type": "not_found",
                        }
                    sys_id = inc_result["result"][0].get("sys_id", "")
                else:
                    sys_id = inc_result["result"].get("sys_id", "")

        result = client.add_incident_comment(
            sys_id=sys_id,
            comment=comment,
            work_notes=work_notes,
        )

        incident_data = result.get("result", {})
        incident_number = incident_data.get("number", incident_id)

        emit_success(f"Added {comment_type} to {incident_number}")

        return {
            "success": True,
            "dry_run": False,
            "incident_number": incident_number,
            "message": f"Successfully added {comment_type} to {incident_number}",
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_add_incident_comment(agent: Any) -> Tool:
    """Register the servicenow_add_incident_comment tool with a PydanticAI agent."""
    return agent.tool(servicenow_add_incident_comment)


# ============================================================================
# ServiceNow Reassign Incident Tool
# ============================================================================


def servicenow_reassign_incident(
    ctx: RunContext,
    incident_id: str,
    assignment_group: str = "",
    assigned_to: str = "",
    work_notes: str = "",
    dry_run: bool = False,
) -> dict:
    """Reassign an incident to a different group and/or user.

    Use this tool to transfer ownership of an incident to another team or person.
    You must specify at least one of assignment_group or assigned_to.

    Use `servicenow_search_assignment_groups` to find valid group names.
    Use `servicenow_search_users` to find valid user IDs.

    Args:
        ctx: PydanticAI run context
        incident_id: The incident number (e.g., INC0012345) or sys_id
        assignment_group: Name or sys_id of the new assignment group.
                          Use servicenow_search_assignment_groups to find groups.
        assigned_to: Username or sys_id of the user to assign the incident to.
                     Use servicenow_search_users to find users.
        work_notes: Optional work note to add explaining the reassignment.
                    This is internal only (not visible to the requester).
        dry_run: If True, preview the reassignment without actually doing it.
                 Use this to test the integration safely. Default: False

    Returns:
        Dict containing:
            - success (bool): Whether the reassignment succeeded (or would in dry_run)
            - incident_number (str): The incident number
            - sys_id (str): The incident sys_id
            - assignment_group (str): The new assignment group (if changed)
            - assigned_to (str): The new assignee (if changed)
            - url (str): Web URL to view the incident
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if reassignment failed
    """
    # Validate that at least one assignment field is provided
    if not assignment_group and not assigned_to:
        return {
            "success": False,
            "error": "You must specify at least one of 'assignment_group' or 'assigned_to'",
            "error_type": "validation",
        }

    mode_label = "DRY RUN" if dry_run else "REASSIGN INCIDENT"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW {mode_label} [/bold white on blue] "
            f"🔄 [bold cyan]{incident_id}[/bold cyan]"
        )
    )

    # Build preview/update payload
    reassign_fields = {}
    if assignment_group:
        reassign_fields["assignment_group"] = assignment_group
    if assigned_to:
        reassign_fields["assigned_to"] = assigned_to
    if work_notes:
        reassign_fields["work_notes"] = work_notes

    # In dry_run mode, just return what would be submitted
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

        # If incident_id is a number, we need to get the sys_id first
        sys_id = incident_id
        incident_number = incident_id
        if incident_id.upper().startswith("INC"):
            inc_result = client.get_incident(incident_id)
            if inc_result.get("result"):
                if isinstance(inc_result["result"], list):
                    if not inc_result["result"]:
                        return {
                            "success": False,
                            "error": f"Incident not found: {incident_id}",
                            "error_type": "not_found",
                        }
                    sys_id = inc_result["result"][0].get("sys_id", "")
                    incident_number = inc_result["result"][0].get("number", incident_id)
                else:
                    sys_id = inc_result["result"].get("sys_id", "")
                    incident_number = inc_result["result"].get("number", incident_id)

        # Perform the reassignment via update_incident
        result = client.update_incident(
            sys_id=sys_id,
            updates=reassign_fields,
        )

        incident_data = result.get("result", {})
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=incident.do?sys_id={sys_id}"

        # Extract the updated assignment info
        new_group = _extract_display_value(incident_data.get("assignment_group", ""))
        new_assignee = _extract_display_value(incident_data.get("assigned_to", ""))

        emit_success(
            f"Reassigned {incident_number} → "
            f"Group: {new_group or '(unchanged)'}, "
            f"Assignee: {new_assignee or '(unassigned)'}"
        )

        return {
            "success": True,
            "dry_run": False,
            "incident_number": incident_number,
            "sys_id": sys_id,
            "assignment_group": new_group,
            "assigned_to": new_assignee,
            "url": url,
            "message": f"Successfully reassigned {incident_number}",
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_reassign_incident(agent: Any) -> Tool:
    """Register the servicenow_reassign_incident tool with a PydanticAI agent."""
    return agent.tool(servicenow_reassign_incident)


# ============================================================================
# ServiceNow List Catalog Items Tool
# ============================================================================


def servicenow_list_catalog_items(
    ctx: RunContext,
    category: str = "",
    query: str = "",
    limit: int = 10,
) -> dict:
    """List available service catalog items.

    Args:
        ctx: PydanticAI run context
        category: Filter by category name
        query: Search query for catalog items
        limit: Maximum number of items to return (default: 10, max: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - items (list): List of catalog items
            - total_count (int): Number of items returned
            - error (str, optional): Error message if query failed
    """
    search_desc = query or category or "all items"
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW CATALOG [/bold white on purple] "
            f"🛒 [bold cyan]Searching: {search_desc}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.list_catalog_items(
            category=category,
            query=query,
            limit=min(limit, 50),
        )

        items = []
        for item in result.get("result", []):
            category_val = item.get("category", "")
            if isinstance(category_val, dict):
                category_val = category_val.get("display_value", "")

            items.append({
                "sys_id": item.get("sys_id", ""),
                "name": item.get("name", ""),
                "short_description": item.get("short_description", ""),
                "category": category_val,
                "price": item.get("price", ""),
                "delivery_time": item.get("delivery_time", ""),
            })

        emit_success(f"Found {len(items)} catalog item(s)")

        return {
            "success": True,
            "items": items,
            "total_count": len(items),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_list_catalog_items(agent: Any) -> Tool:
    """Register the servicenow_list_catalog_items tool with a PydanticAI agent."""
    return agent.tool(servicenow_list_catalog_items)


# ============================================================================
# Automation Feasibility Analysis
# ============================================================================


def _analyze_automation_feasibility(item_data: dict) -> dict:
    """Analyze a catalog item to determine if it can be automated via API.
    
    Checks for patterns that indicate the form requires browser-based interaction:
    - External API calls in client scripts (Tableau, Azure, etc.)
    - Dynamically populated dropdowns (empty choices)
    - Hidden validation fields checked by onSubmit
    - GlideAjax or REST calls in scripts
    
    Args:
        item_data: The raw catalog item data from ServiceNow API
        
    Returns:
        Dict containing:
            - automatable (bool): Whether the form can likely be automated
            - confidence (str): "high", "medium", "low"
            - blockers (list): List of reasons why automation may fail
            - warnings (list): Potential issues that may cause problems
    """
    blockers = []
    warnings = []
    
    # Patterns that indicate external API calls
    external_api_patterns = [
        (r'tableau', 'Tableau API integration detected'),
        (r'azure', 'Azure API integration detected'),
        (r'Bearer\s+', 'Bearer token authentication detected (external API)'),
        (r'XMLHttpRequest|fetch\s*\(', 'Direct HTTP requests to external services'),
        (r'api_version\s*=', 'External API versioning detected'),
        (r'\.service-now\.com.*api(?!/now)', 'Custom ServiceNow API endpoint'),
    ]
    
    # Patterns that indicate browser-required validation
    validation_patterns = [
        (r"g_form\.getValue\(['\"]submit_form['\"]\)", 'Hidden submit validation field'),
        (r"g_form\.addErrorMessage", 'Client-side error validation'),
        (r"return\s+false", 'Form submission blocking logic'),
    ]
    
    # Patterns that indicate dynamic data loading
    dynamic_patterns = [
        (r'GlideAjax', 'Server-side script calls (GlideAjax)'),
        (r'addParam.*sysparm_', 'Dynamic parameter loading'),
    ]
    
    # Analyze client scripts
    client_scripts = item_data.get("client_script", {})
    all_scripts = []
    
    for script_type in ["onChange", "onSubmit", "onLoad"]:
        for script in client_scripts.get(script_type, []):
            script_content = script.get("script", "")
            all_scripts.append((script_type, script_content))
    
    # Check for external API patterns
    for script_type, script_content in all_scripts:
        script_lower = script_content.lower()
        
        for pattern, message in external_api_patterns:
            if re.search(pattern, script_lower, re.IGNORECASE):
                blockers.append(f"{message} in {script_type} script")
        
        for pattern, message in validation_patterns:
            if re.search(pattern, script_content):  # Case-sensitive for JS
                if script_type == "onSubmit":
                    blockers.append(f"{message} in {script_type} script")
                else:
                    warnings.append(f"{message} in {script_type} script")
        
        for pattern, message in dynamic_patterns:
            if re.search(pattern, script_content):
                warnings.append(f"{message} in {script_type} script")
    
    # Check for empty dynamic dropdowns
    variables = item_data.get("variables", [])
    for var in variables:
        var_type = var.get("friendly_type", var.get("display_type", ""))
        var_name = var.get("name", "unknown")
        choices = var.get("choices", [])
        
        # Select box with only "None" option = dynamically populated
        if var_type == "select_box" and choices:
            non_empty_choices = [c for c in choices if c.get("value", "")]
            if not non_empty_choices:
                blockers.append(f"Field '{var_name}' has no choices (dynamically populated by JavaScript)")
    
    # Determine overall feasibility
    if blockers:
        automatable = False
        confidence = "high"
    elif warnings:
        automatable = True  # Might still work
        confidence = "medium"
    else:
        automatable = True
        confidence = "high"
    
    # Deduplicate
    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))
    
    return {
        "automatable": automatable,
        "confidence": confidence,
        "blockers": blockers,
        "warnings": warnings,
    }


# ============================================================================
# ServiceNow Get Catalog Item Details Tool
# ============================================================================


def servicenow_get_catalog_item_details(
    ctx: RunContext,
    item_id: str,
) -> dict:
    """Get detailed information about a service catalog item, including its required variables.

    Use this tool BEFORE submitting a catalog request to understand what fields/variables
    are required for that specific catalog item.

    Args:
        ctx: PydanticAI run context
        item_id: The catalog item sys_id (get this from servicenow_list_catalog_items)

    Returns:
        Dict containing:
            - success (bool): Whether the item was found
            - name (str): Catalog item name
            - short_description (str): Brief description
            - description (str): Full description (markdown)
            - category (str): Item category
            - price (str): Price information
            - delivery_time (str): Expected delivery time
            - variables (list): List of required/optional variables with:
                - name (str): Variable name (use this as key in variables dict)
                - label (str): Human-readable label
                - type (str): Variable type (string, boolean, reference, etc.)
                - mandatory (bool): Whether this field is required
                - description (str): Help text for this variable
                - default_value (str): Default value if any
                - choices (list): Available options for choice fields
            - url (str): Web URL to view the catalog item
            - automation (dict): Analysis of whether the form can be automated:
                - automatable (bool): Whether API submission is likely to work
                - confidence (str): "high", "medium", or "low"
                - blockers (list): Reasons why automation will definitely fail
                - warnings (list): Potential issues that may cause problems
            - error (str, optional): Error message if lookup failed
    
    IMPORTANT: If automation.automatable is False, do NOT attempt to submit via API.
    Instead, provide the user with the URL and the values they need to enter manually.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW CATALOG ITEM DETAILS [/bold white on purple] "
            f"\ud83d\udccb [bold cyan]{item_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_catalog_item(item_id)

        item_data = result.get("result", {})
        
        if not item_data:
            return {
                "success": False,
                "error": f"Catalog item not found: {item_id}",
                "error_type": "not_found",
            }

        # Extract and format variables
        variables = []
        raw_variables = item_data.get("variables", [])
        
        for var in raw_variables:
            var_info = {
                "name": var.get("name", ""),
                "label": var.get("label", var.get("question_text", "")),
                "type": var.get("type", var.get("display_type", "string")),
                "mandatory": var.get("mandatory", False),
                "description": var.get("help_text", var.get("instructions", "")),
                "default_value": var.get("default_value", ""),
            }
            
            # Include choices for select/choice fields
            choices = var.get("choices", var.get("choice_table", []))
            if choices:
                if isinstance(choices, list):
                    var_info["choices"] = [
                        {"value": c.get("value", c), "label": c.get("label", c.get("text", c))}
                        for c in choices
                    ]
                else:
                    var_info["choices"] = choices
            
            variables.append(var_info)

        # Sort variables: mandatory first, then by name
        variables.sort(key=lambda v: (not v.get("mandatory", False), v.get("name", "")))

        # Convert description HTML to markdown
        description_html = item_data.get("description", "")
        description_md = _convert_html_to_markdown(description_html) if description_html else ""

        # Build URL
        url = f"{SERVICENOW_BASE_URL}/sp?id=sc_cat_item&sys_id={item_id}"
        
        # Analyze automation feasibility
        automation_analysis = _analyze_automation_feasibility(item_data)

        emit_success(f"Found catalog item: {item_data.get('name', item_id)}")
        
        # Emit warning if form is not automatable
        if not automation_analysis["automatable"]:
            emit_warning(
                f"⚠️  This form may NOT be automatable via API. "
                f"Blockers: {len(automation_analysis['blockers'])}"
            )

        return {
            "success": True,
            "sys_id": item_id,
            "name": item_data.get("name", ""),
            "short_description": item_data.get("short_description", ""),
            "description": description_md,
            "category": item_data.get("category", {}).get("name", "") if isinstance(item_data.get("category"), dict) else item_data.get("category", ""),
            "price": item_data.get("price", item_data.get("recurring_price", "")),
            "delivery_time": item_data.get("delivery_time", ""),
            "variables": variables,
            "variable_count": len(variables),
            "mandatory_variable_count": sum(1 for v in variables if v.get("mandatory")),
            "url": url,
            # Automation feasibility analysis
            "automation": automation_analysis,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_get_catalog_item_details(agent: Any) -> Tool:
    """Register the servicenow_get_catalog_item_details tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_catalog_item_details)


# ============================================================================
# ServiceNow Submit Catalog Request Tool
# ============================================================================


def servicenow_submit_catalog_request(
    ctx: RunContext,
    item_id: str,
    variables: dict | None = None,
    quantity: int = 1,
    special_instructions: str = "",
    dry_run: bool = False,
) -> dict:
    """Submit a service catalog request.

    Args:
        ctx: PydanticAI run context
        item_id: The catalog item sys_id (get this from servicenow_list_catalog_items)
        variables: Dictionary of variable values required by the catalog item
        quantity: Quantity to order (default: 1)
        special_instructions: Additional instructions for the request
        dry_run: If True, preview the request without actually submitting it.
                 Use this to test the integration safely. Default: False

    Returns:
        Dict containing:
            - success (bool): Whether the request was submitted (or would be in dry_run)
            - request_number (str): The request number (e.g., REQ0012345)
            - sys_id (str): The request sys_id
            - url (str): Web URL to view the request
            - dry_run (bool): Whether this was a dry run
            - error (str, optional): Error message if submission failed
    """
    mode_label = "DRY RUN" if dry_run else "SUBMIT REQUEST"
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW {mode_label} [/bold white on purple] "
            f"\ud83d\udce6 [bold cyan]Item: {item_id[:20]}...[/bold cyan]"
        )
    )

    # In dry_run mode, just return what would be submitted
    if dry_run:
        emit_success("Dry run complete - request NOT submitted")
        return {
            "success": True,
            "dry_run": True,
            "message": "This is a preview. Set dry_run=False to actually submit the request.",
            "preview": {
                "item_id": item_id,
                "variables": variables or {},
                "quantity": quantity,
                "special_instructions": special_instructions or "(none)",
            },
        }

    try:
        client = get_servicenow_client()
        result = client.submit_catalog_request(
            item_id=item_id,
            variables=variables,
            quantity=quantity,
            special_instructions=special_instructions,
        )

        request_data = result.get("result", {})
        request_number = request_data.get("number", request_data.get("request_number", ""))
        sys_id = request_data.get("sys_id", request_data.get("request_id", ""))

        # Build URL to view the request
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=sc_request.do?sys_id={sys_id}"

        emit_success(f"Submitted request: {request_number}")

        return {
            "success": True,
            "dry_run": False,
            "request_number": request_number,
            "sys_id": sys_id,
            "url": url,
            "message": f"Successfully submitted catalog request {request_number}",
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_submit_catalog_request(agent: Any) -> Tool:
    """Register the servicenow_submit_catalog_request tool with a PydanticAI agent."""
    return agent.tool(servicenow_submit_catalog_request)


# ============================================================================
# ServiceNow Get Request Status Tool
# ============================================================================


def servicenow_get_request_status(
    ctx: RunContext,
    request_id: str,
) -> dict:
    """Get the status of a service catalog request.

    Args:
        ctx: PydanticAI run context
        request_id: The request number (e.g., REQ0012345) or sys_id

    Returns:
        Dict containing:
            - success (bool): Whether the request was found
            - request_number (str): The request number
            - state (str): Current request state
            - stage (str): Current stage
            - requested_for (str): Who the request is for
            - opened_at (str): When the request was opened
            - url (str): Web URL to view the request
            - error (str, optional): Error message if lookup failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on purple] SERVICENOW REQUEST STATUS [/bold white on purple] "
            f"🔍 [bold cyan]{request_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_request_status(request_id)

        # Handle list response (when searching by number)
        if "result" in result:
            if isinstance(result["result"], list):
                if not result["result"]:
                    return {
                        "success": False,
                        "error": f"Request not found: {request_id}",
                        "error_type": "not_found",
                    }
                request_data = result["result"][0]
            else:
                request_data = result["result"]
        else:
            return {
                "success": False,
                "error": f"Unexpected response format for request: {request_id}",
                "error_type": "api_error",
            }

        sys_id = request_data.get("sys_id", "")
        url = f"{SERVICENOW_BASE_URL}/nav_to.do?uri=sc_request.do?sys_id={sys_id}"

        # Extract display values for reference fields
        requested_for = request_data.get("requested_for", "")
        if isinstance(requested_for, dict):
            requested_for = requested_for.get("display_value", "")

        emit_success(f"Found request: {request_data.get('number', request_id)}")

        return {
            "success": True,
            "request_number": request_data.get("number", ""),
            "sys_id": sys_id,
            "state": request_data.get("request_state", request_data.get("state", "")),
            "stage": request_data.get("stage", ""),
            "requested_for": requested_for,
            "opened_at": request_data.get("opened_at", request_data.get("sys_created_on", "")),
            "short_description": request_data.get("short_description", ""),
            "url": url,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_get_request_status(agent: Any) -> Tool:
    """Register the servicenow_get_request_status tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_request_status)


# ============================================================================
# ServiceNow Search Assignment Groups Tool
# ============================================================================


def servicenow_search_assignment_groups(
    ctx: RunContext,
    query: str = "",
    limit: int = 10,
) -> dict:
    """Search for ServiceNow assignment groups (ITIL groups).

    Use this tool to find the correct assignment group name or sys_id
    before creating an incident that should be routed to a specific team.

    Args:
        ctx: PydanticAI run context
        query: Search query string (searches group name and description)
        limit: Maximum number of results to return (default: 10, max: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - groups (list): List of assignment groups with:
                - sys_id (str): Group sys_id (use this for assignment_group)
                - name (str): Group name (can also use this)
                - description (str): Group description
                - email (str): Group email if available
                - manager (str): Group manager
            - total_count (int): Number of groups returned
            - error (str, optional): Error message if search failed
    """
    search_desc = query if query else "all groups"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW ASSIGNMENT GROUPS [/bold white on blue] "
            f"\ud83d\udc65 [bold cyan]Searching: {search_desc}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_assignment_groups(
            query=query,
            limit=min(limit, 50),
        )

        groups = []
        for group in result.get("result", []):
            # Extract display values for reference fields
            manager = group.get("manager", "")
            if isinstance(manager, dict):
                manager = manager.get("display_value", "")

            groups.append({
                "sys_id": group.get("sys_id", ""),
                "name": group.get("name", ""),
                "description": group.get("description", ""),
                "email": group.get("email", ""),
                "manager": manager,
                "type": group.get("type", ""),
            })

        emit_success(f"Found {len(groups)} assignment group(s)")

        return {
            "success": True,
            "groups": groups,
            "total_count": len(groups),
            "query": query,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_search_assignment_groups(agent: Any) -> Tool:
    """Register the servicenow_search_assignment_groups tool with a PydanticAI agent."""
    return agent.tool(servicenow_search_assignment_groups)


# ============================================================================
# ServiceNow Search Users Tool
# ============================================================================


def servicenow_search_users(
    ctx: RunContext,
    query: str = "",
    limit: int = 10,
) -> dict:
    """Search for ServiceNow users.

    Use this tool to find a specific user to assign an incident to,
    or to look up user information.

    Args:
        ctx: PydanticAI run context
        query: Search query string (searches name, username, and email)
        limit: Maximum number of results to return (default: 10, max: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - users (list): List of users with:
                - sys_id (str): User sys_id (use this for assigned_to)
                - user_name (str): Username (can also use this for assigned_to)
                - name (str): Full name
                - email (str): Email address
                - title (str): Job title
                - department (str): Department
                - manager (str): Manager name
            - total_count (int): Number of users returned
            - error (str, optional): Error message if search failed
    """
    search_desc = query if query else "all users"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW USER SEARCH [/bold white on blue] "
            f"\ud83d\udc64 [bold cyan]Searching: {search_desc}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_users(
            query=query,
            limit=min(limit, 50),
        )

        users = []
        for user in result.get("result", []):
            # Extract display values for reference fields
            manager = user.get("manager", "")
            if isinstance(manager, dict):
                manager = manager.get("display_value", "")

            department = user.get("department", "")
            if isinstance(department, dict):
                department = department.get("display_value", "")

            location = user.get("location", "")
            if isinstance(location, dict):
                location = location.get("display_value", "")

            users.append({
                "sys_id": user.get("sys_id", ""),
                "user_name": user.get("user_name", ""),
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "title": user.get("title", ""),
                "department": department,
                "manager": manager,
                "location": location,
            })

        emit_success(f"Found {len(users)} user(s)")

        return {
            "success": True,
            "users": users,
            "total_count": len(users),
            "query": query,
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_search_users(agent: Any) -> Tool:
    """Register the servicenow_search_users tool with a PydanticAI agent."""
    return agent.tool(servicenow_search_users)


# ============================================================================
# ServiceNow Get User Groups Tool
# ============================================================================


def servicenow_get_user_groups(
    ctx: RunContext,
    user_id: str,
    limit: int = 50,
) -> dict:
    """Get the assignment groups that a user is a member of.

    Use this tool to find which ITIL groups a specific user belongs to.
    This is useful for finding the right assignment group when you know
    who should work on an incident.

    Args:
        ctx: PydanticAI run context
        user_id: Username or sys_id of the user to look up
        limit: Maximum number of groups to return (default: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the lookup succeeded
            - user (str): The user that was looked up
            - groups (list): List of groups the user belongs to, with:
                - sys_id (str): Group sys_id
                - name (str): Group name
            - total_count (int): Number of groups found
            - error (str, optional): Error message if lookup failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW USER GROUPS [/bold white on blue] "
            f"\ud83d\udc65 [bold cyan]Groups for: {user_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_user_groups(
            user_id=user_id,
            limit=limit,
        )

        groups = []
        for membership in result.get("result", []):
            group_info = membership.get("group", {})
            if isinstance(group_info, dict):
                groups.append({
                    "sys_id": group_info.get("value", ""),
                    "name": group_info.get("display_value", ""),
                })
            elif group_info:  # It's a string (sys_id)
                groups.append({
                    "sys_id": group_info,
                    "name": "(name not available)",
                })

        emit_success(f"Found {len(groups)} group(s) for user {user_id}")

        return {
            "success": True,
            "user": user_id,
            "groups": groups,
            "total_count": len(groups),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_get_user_groups(agent: Any) -> Tool:
    """Register the servicenow_get_user_groups tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_user_groups)


# ============================================================================
# ServiceNow Get Group Members Tool
# ============================================================================


def servicenow_get_group_members(
    ctx: RunContext,
    group_id: str,
    limit: int = 50,
) -> dict:
    """Get the members of a specific assignment group.

    Use this tool to see who is in a particular ITIL group.
    This helps identify potential assignees for incidents.

    Args:
        ctx: PydanticAI run context
        group_id: Group name or sys_id to look up
        limit: Maximum number of members to return (default: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the lookup succeeded
            - group (str): The group that was looked up
            - members (list): List of group members, with:
                - sys_id (str): User sys_id
                - name (str): User's full name
                - user_name (str): Username
            - total_count (int): Number of members found
            - error (str, optional): Error message if lookup failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW GROUP MEMBERS [/bold white on blue] "
            f"\ud83d\udc65 [bold cyan]Members of: {group_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.get_group_members(
            group_id=group_id,
            limit=limit,
        )

        members = []
        for membership in result.get("result", []):
            user_info = membership.get("user", {})
            if isinstance(user_info, dict):
                # Try to get username from the display value or do a secondary lookup
                display_value = user_info.get("display_value", "")
                members.append({
                    "sys_id": user_info.get("value", ""),
                    "name": display_value,
                })
            elif user_info:  # It's a string (sys_id)
                members.append({
                    "sys_id": user_info,
                    "name": "(name not available)",
                })

        emit_success(f"Found {len(members)} member(s) in group {group_id}")

        return {
            "success": True,
            "group": group_id,
            "members": members,
            "total_count": len(members),
        }

    except Exception as e:
        return _handle_servicenow_error(e)


def register_servicenow_get_group_members(agent: Any) -> Tool:
    """Register the servicenow_get_group_members tool with a PydanticAI agent."""
    return agent.tool(servicenow_get_group_members)