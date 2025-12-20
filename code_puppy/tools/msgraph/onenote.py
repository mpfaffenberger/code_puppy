"""Microsoft Graph OneNote tools.

Provides tools for:
- Listing notebooks, sections, and pages
- Reading page content
- Creating notebooks, sections, and pages
- Searching notes

OneNote API: https://docs.microsoft.com/en-us/graph/api/resources/onenote-api-overview
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


def _format_notebook(data: dict) -> dict:
    """Format a notebook response."""
    return {
        "id": data.get("id"),
        "display_name": data.get("displayName"),
        "created_datetime": data.get("createdDateTime"),
        "last_modified": data.get("lastModifiedDateTime"),
        "is_default": data.get("isDefault", False),
        "is_shared": data.get("isShared", False),
        "sections_url": data.get("sectionsUrl"),
        "web_url": data.get("links", {}).get("oneNoteWebUrl", {}).get("href"),
    }


def _format_section(data: dict) -> dict:
    """Format a section response."""
    return {
        "id": data.get("id"),
        "display_name": data.get("displayName"),
        "created_datetime": data.get("createdDateTime"),
        "last_modified": data.get("lastModifiedDateTime"),
        "is_default": data.get("isDefault", False),
        "pages_url": data.get("pagesUrl"),
        "web_url": data.get("links", {}).get("oneNoteWebUrl", {}).get("href"),
    }


def _format_page(data: dict) -> dict:
    """Format a page response."""
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "created_datetime": data.get("createdDateTime"),
        "last_modified": data.get("lastModifiedDateTime"),
        "content_url": data.get("contentUrl"),
        "web_url": data.get("links", {}).get("oneNoteWebUrl", {}).get("href"),
        "level": data.get("level", 0),
        "order": data.get("order", 0),
    }


# =============================================================================
# NOTEBOOK TOOLS
# =============================================================================


def msgraph_list_notebooks(
    ctx: RunContext[Any],
) -> dict:
    """List all OneNote notebooks.

    Returns:
        Dict with success and list of notebooks.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📓 [bold cyan]Listing OneNote notebooks[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get("/me/onenote/notebooks")
        notebooks = [_format_notebook(nb) for nb in response.get("value", [])]

        emit_success(f"Found {len(notebooks)} notebook(s)")

        return {
            "success": True,
            "notebooks": notebooks,
            "total_count": len(notebooks),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_notebooks(agent: Any) -> Tool:
    """Register the list notebooks tool."""
    return agent.tool()(msgraph_list_notebooks)


# =============================================================================
# SECTION TOOLS
# =============================================================================


def msgraph_list_sections(
    ctx: RunContext[Any],
    *,
    notebook_id: str | None = None,
) -> dict:
    """List OneNote sections.

    Args:
        notebook_id: Optional notebook ID to filter sections.
            If not provided, lists all sections across all notebooks.

    Returns:
        Dict with success and list of sections.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📑 [bold cyan]Listing OneNote sections[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        if notebook_id:
            endpoint = f"/me/onenote/notebooks/{notebook_id}/sections"
        else:
            endpoint = "/me/onenote/sections"

        response = client.get(endpoint)
        sections = [_format_section(s) for s in response.get("value", [])]

        emit_success(f"Found {len(sections)} section(s)")

        return {
            "success": True,
            "sections": sections,
            "total_count": len(sections),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_sections(agent: Any) -> Tool:
    """Register the list sections tool."""
    return agent.tool()(msgraph_list_sections)


# =============================================================================
# PAGE TOOLS
# =============================================================================


def msgraph_list_pages(
    ctx: RunContext[Any],
    *,
    section_id: str | None = None,
    limit: int = 50,
) -> dict:
    """List OneNote pages.

    Args:
        section_id: Optional section ID to filter pages.
            If not provided, lists recent pages across all sections.
        limit: Maximum number of pages to return.

    Returns:
        Dict with success and list of pages.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📄 [bold cyan]Listing OneNote pages[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        params = {
            "$top": limit,
            "$orderby": "lastModifiedDateTime desc",
        }

        if section_id:
            endpoint = f"/me/onenote/sections/{section_id}/pages"
        else:
            endpoint = "/me/onenote/pages"

        response = client.get(endpoint, params=params)
        pages = [_format_page(p) for p in response.get("value", [])]

        emit_success(f"Found {len(pages)} page(s)")

        return {
            "success": True,
            "pages": pages,
            "total_count": len(pages),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_pages(agent: Any) -> Tool:
    """Register the list pages tool."""
    return agent.tool()(msgraph_list_pages)


def msgraph_get_page_content(
    ctx: RunContext[Any],
    *,
    page_id: str,
) -> dict:
    """Get the HTML content of a OneNote page.

    Args:
        page_id: The page ID to retrieve content for.

    Returns:
        Dict with success and page content (HTML).
    """
    if not page_id or not page_id.strip():
        return {
            "success": False,
            "error": "page_id cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📄 [bold cyan]Getting page content: {page_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Get page metadata first
        page = client.get(f"/me/onenote/pages/{page_id}")
        page_info = _format_page(page)

        # Get page content (returns HTML)
        # Note: This endpoint returns HTML directly, not JSON
        content_response = client.get(
            f"/me/onenote/pages/{page_id}/content",
            headers={"Accept": "text/html"},
        )

        # Extract text content from HTML (basic extraction)
        content = (
            content_response
            if isinstance(content_response, str)
            else str(content_response)
        )

        emit_success(f"Retrieved page: {page_info.get('title')}")

        return {
            "success": True,
            "page": page_info,
            "content_html": content,
            "content_length": len(content),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_page_content(agent: Any) -> Tool:
    """Register the get page content tool."""
    return agent.tool()(msgraph_get_page_content)


# =============================================================================
# CREATE TOOLS
# =============================================================================


def msgraph_create_notebook(
    ctx: RunContext[Any],
    *,
    display_name: str,
) -> dict:
    """Create a new OneNote notebook.

    Args:
        display_name: Name for the new notebook.

    Returns:
        Dict with success and created notebook details.
    """
    if not display_name or not display_name.strip():
        return {
            "success": False,
            "error": "display_name cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📓 [bold cyan]Creating notebook: {display_name}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.post(
            "/me/onenote/notebooks",
            json={"displayName": display_name},
        )

        notebook = _format_notebook(response)
        emit_success(f"Created notebook: {notebook.get('display_name')}")

        return {
            "success": True,
            "notebook": notebook,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_notebook(agent: Any) -> Tool:
    """Register the create notebook tool."""
    return agent.tool()(msgraph_create_notebook)


def msgraph_create_section(
    ctx: RunContext[Any],
    *,
    notebook_id: str,
    display_name: str,
) -> dict:
    """Create a new section in a notebook.

    Args:
        notebook_id: The notebook ID to create the section in.
        display_name: Name for the new section.

    Returns:
        Dict with success and created section details.
    """
    if not notebook_id or not notebook_id.strip():
        return {
            "success": False,
            "error": "notebook_id cannot be empty",
        }
    if not display_name or not display_name.strip():
        return {
            "success": False,
            "error": "display_name cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📑 [bold cyan]Creating section: {display_name}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.post(
            f"/me/onenote/notebooks/{notebook_id}/sections",
            json={"displayName": display_name},
        )

        section = _format_section(response)
        emit_success(f"Created section: {section.get('display_name')}")

        return {
            "success": True,
            "section": section,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_section(agent: Any) -> Tool:
    """Register the create section tool."""
    return agent.tool()(msgraph_create_section)


def msgraph_create_page(
    ctx: RunContext[Any],
    *,
    section_id: str,
    title: str,
    content: str | None = None,
) -> dict:
    """Create a new page in a section.

    Args:
        section_id: The section ID to create the page in.
        title: Title for the new page.
        content: Optional HTML content for the page body.

    Returns:
        Dict with success and created page details.
    """
    if not section_id or not section_id.strip():
        return {
            "success": False,
            "error": "section_id cannot be empty",
        }
    if not title or not title.strip():
        return {
            "success": False,
            "error": "title cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📄 [bold cyan]Creating page: {title}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # OneNote pages are created with HTML content
        body_content = content or ""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
</head>
<body>
    {body_content}
</body>
</html>"""

        response = client.post(
            f"/me/onenote/sections/{section_id}/pages",
            data=html_content,
            headers={"Content-Type": "text/html"},
        )

        page = _format_page(response)
        emit_success(f"Created page: {page.get('title')}")

        return {
            "success": True,
            "page": page,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_page(agent: Any) -> Tool:
    """Register the create page tool."""
    return agent.tool()(msgraph_create_page)


# =============================================================================
# SEARCH TOOLS
# =============================================================================


def msgraph_search_notes(
    ctx: RunContext[Any],
    *,
    query: str,
    limit: int = 25,
) -> dict:
    """Search across all OneNote pages.

    Args:
        query: Search query string.
        limit: Maximum number of results.

    Returns:
        Dict with success and matching pages.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "error": "query cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching notes for: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Use the search API
        # Note: OneNote search is done via the pages endpoint with a filter
        # or via the Microsoft Search API
        response = client.get(
            "/me/onenote/pages",
            params={
                "$top": limit,
                "$search": f'"{query}"',
                "$orderby": "lastModifiedDateTime desc",
            },
        )

        pages = [_format_page(p) for p in response.get("value", [])]

        emit_success(f"Found {len(pages)} matching page(s)")

        return {
            "success": True,
            "query": query,
            "pages": pages,
            "total_count": len(pages),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_notes(agent: Any) -> Tool:
    """Register the search notes tool."""
    return agent.tool()(msgraph_search_notes)
