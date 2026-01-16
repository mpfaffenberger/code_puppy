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
    if isinstance(e, ServiceNowAuthError):
        error_msg = f"Authentication failed: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, ServiceNowNotFoundError):
        error_msg = f"Resource not found: {str(e)}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, ServiceNowAPIError):
        error_msg = f"API error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
    elif isinstance(e, ServiceNowError):
        error_msg = f"ServiceNow error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "servicenow",
        }
    else:
        error_msg = f"Unexpected error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
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
