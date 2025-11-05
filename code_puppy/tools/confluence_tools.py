"""Confluence integration tools for Biscuit.

Provides tools for searching and reading Confluence pages, converting
Confluence storage format (HTML) to markdown for easier consumption.
"""

from typing import Any, List

from markdownify import markdownify as md
from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from code_puppy.plugins.walmart_specific.confluence_client import (
    ConfluenceClient,
    ConfluenceError,
    ConfluenceAuthError,
    ConfluenceNotFoundError,
    ConfluenceAPIError,
)
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning


# ============================================================================
# Helper Functions
# ============================================================================


def get_confluence_client() -> ConfluenceClient:
    """Get a Confluence client instance.

    Returns:
        ConfluenceClient: A configured Confluence client
    """
    return ConfluenceClient()


def _convert_storage_to_markdown(storage_html: str) -> str:
    """Convert Confluence storage format (HTML) to markdown.

    Args:
        storage_html: HTML content from Confluence storage format

    Returns:
        Markdown-formatted string
    """
    if not storage_html:
        return ""

    # Use markdownify to convert HTML to markdown
    # Strip whitespace for cleaner output
    markdown = md(storage_html, heading_style="ATX", strip=["script", "style"])
    return markdown.strip()


def _format_search_result(result: dict) -> dict:
    """Format a single search result for better readability.

    Args:
        result: Raw search result from Confluence API

    Returns:
        Formatted dict with essential information
    """
    return {
        "id": result.get("id"),
        "title": result.get("title"),
        "type": result.get("type"),
        "space": result.get("space", {}).get("key"),
        "url": result.get("_links", {}).get("webui"),
        "excerpt": result.get("excerpt", ""),
    }


def _handle_confluence_error(e: Exception) -> dict:
    """Convert Confluence exceptions to structured error responses.

    Args:
        e: Exception raised by Confluence client

    Returns:
        Dict with success=False and error details
    """
    if isinstance(e, ConfluenceAuthError):
        error_msg = f"Authentication failed: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, ConfluenceNotFoundError):
        error_msg = f"Resource not found: {str(e)}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, ConfluenceAPIError):
        error_msg = f"API error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
    elif isinstance(e, ConfluenceError):
        error_msg = f"Confluence error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "confluence",
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
# Confluence Search Tool
# ============================================================================


def confluence_search(
    ctx: RunContext, query: str, limit: int = 10, start: int = 0
) -> dict:
    """Search Confluence for pages and content.

    Args:
        ctx: PydanticAI run context
        query: Search query string (CQL syntax supported)
        limit: Maximum number of results to return (default: 10, max: 100)
        start: Starting offset for pagination (default: 0)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of formatted search results
            - total_count (int): Total number of results found
            - error (str, optional): Error message if search failed
    """
    emit_info(f"Searching Confluence for: '{query}'")

    try:
        client = ConfluenceClient()
        # Use search_content with CQL query
        cql = f"type=page AND text~'{query}'"
        raw_results = client.search_content(cql=cql, limit=limit, start=start)

        # Format results for better readability
        formatted_results = [
            _format_search_result(result) for result in raw_results.get("results", [])
        ]

        total_count = raw_results.get("size", len(formatted_results))

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
        return _handle_confluence_error(e)


def register_confluence_search(agent: Any) -> Tool:
    """Register the confluence_search tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(confluence_search)


# ============================================================================
# Confluence Read Page Tool
# ============================================================================


def confluence_read_page(ctx: RunContext, page_id: str) -> dict:
    """Read the full content of a Confluence page.

    Args:
        ctx: PydanticAI run context
        page_id: The Confluence page ID to read

    Returns:
        Dict containing:
            - success (bool): Whether the read succeeded
            - page_id (str): The page ID
            - title (str): Page title
            - content (str): Page content in markdown format
            - space (str): Space key
            - url (str): Web URL to the page
            - version (int): Current page version
            - error (str, optional): Error message if read failed
    """
    emit_info(f"Reading Confluence page: {page_id}")

    try:
        client = ConfluenceClient()
        # Use get_page_content to get full page with body
        page_data = client.get_page_content(page_id=page_id)

        # Extract content and convert to markdown
        storage_html = page_data.get("body", {}).get("storage", {}).get("value", "")
        markdown_content = _convert_storage_to_markdown(storage_html)

        # Extract metadata
        title = page_data.get("title", "Untitled")
        space_key = page_data.get("space", {}).get("key", "Unknown")
        version = page_data.get("version", {}).get("number", 1)
        url = page_data.get("_links", {}).get("webui", "")

        emit_success(f"Successfully read page: '{title}'")

        return {
            "success": True,
            "page_id": page_id,
            "title": title,
            "content": markdown_content,
            "space": space_key,
            "url": url,
            "version": version,
        }

    except Exception as e:
        return _handle_confluence_error(e)


def register_confluence_read_page(agent: Any) -> Tool:
    """Register the confluence_read_page tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(confluence_read_page)


# ============================================================================
# Confluence Search by Space Tool
# ============================================================================


def confluence_search_by_space(
    ctx: RunContext, space_key: str, query: str = "", limit: int = 10
) -> dict:
    """Search for pages within a specific Confluence space.

    Args:
        ctx: PydanticAI run context
        space_key: The Confluence space key to search within
        query: Optional search query string (default: "" returns all pages)
        limit: Maximum number of results to return (default: 10)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - results (list): List of formatted search results
            - total_count (int): Total number of results found
            - space_key (str): The space key searched
            - query (str): The query used
            - error (str, optional): Error message if search failed
    """
    if query:
        emit_info(f"Searching space '{space_key}' for: '{query}'")
    else:
        emit_info(f"Listing pages in space '{space_key}'")

    try:
        client = ConfluenceClient()
        # Build CQL query for space search
        if query:
            cql = f"type=page AND space='{space_key}' AND text~'{query}'"
        else:
            cql = f"type=page AND space='{space_key}'"

        raw_results = client.search_content(cql=cql, limit=limit, start=start)

        # Format results for better readability
        formatted_results = [
            _format_search_result(result) for result in raw_results.get("results", [])
        ]

        total_count = raw_results.get("size", len(formatted_results))

        emit_success(
            f"Found {total_count} result(s) in space '{space_key}', "
            f"returning {len(formatted_results)}"
        )

        return {
            "success": True,
            "results": formatted_results,
            "total_count": total_count,
            "space_key": space_key,
            "query": query,
        }

    except Exception as e:
        return _handle_confluence_error(e)


def register_confluence_search_by_space(agent: Any) -> Tool:
    """Register the confluence_search_by_space tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(confluence_search_by_space)


# ============================================================================
# Async Wrapper Functions (for tests and async contexts)
# ============================================================================


async def search_confluence(query: str, limit: int = 10) -> str:
    """Async wrapper for searching Confluence.

    Args:
        query: Search query string
        limit: Maximum number of results to return (default: 10)

    Returns:
        Formatted string with search results
    """
    emit_info(f"Searching Confluence for: '{query}'")

    try:
        client = get_confluence_client()
        # Use search_content with CQL query
        cql = f"type=page AND text~'{query}'"
        raw_results = client.search_content(cql=cql, limit=limit, start=start)

        # Format results
        results_list: List[str] = []
        for result in raw_results.get("results", []):
            title = result.get("title", "Untitled")
            space_key = result.get("space", {}).get("key", "Unknown")
            url = result.get("_links", {}).get("webui", "")
            excerpt = result.get("excerpt", "")

            results_list.append(
                f"**{title}** ({space_key})\nURL: {url}\nExcerpt: {excerpt}\n"
            )

        if not results_list:
            return f"No results found for query: '{query}'"

        return "\n".join(results_list)

    except Exception as e:
        error_msg = f"Search failed: {str(e)}"
        emit_error(error_msg)
        return error_msg
