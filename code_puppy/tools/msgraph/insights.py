"""Microsoft Graph Insights API tools.

Provides access to the Insights API which surfaces:
- Trending documents around the user
- Recently used documents
- Documents shared with the user

These are AI-powered relevance signals that help prioritize information.

API Reference:
https://learn.microsoft.com/en-us/graph/api/resources/officegraphinsights
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# TRENDING DOCUMENTS
# =============================================================================


def msgraph_get_trending_docs(
    ctx: RunContext[Any],
    *,
    top: int = 10,
) -> dict:
    """Get documents trending around you.

    Trending documents are files that are gaining popularity in your network,
    based on your closest relationships and activities.

    Args:
        top: Maximum number of items to return (default 10, max 100).

    Returns:
        Dict with success and list of trending documents with relevance info.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📈 [bold cyan]Getting trending documents...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        try:
            response = client.get(
                "/me/insights/trending",
                params={"$top": min(top, 100)},
            )
        except Exception as e:
            error_str = str(e).lower()
            if "iteminsightsdisabled" in error_str or "403" in error_str:
                # Tenant has disabled Item Insights - common in enterprise
                return {
                    "success": False,
                    "error": "Item Insights disabled by tenant policy",
                    "note": "Your organization has disabled trending document insights for privacy. Use msgraph_get_recent_docs instead.",
                    "fallback": "msgraph_get_recent_docs",
                }
            raise

        items = response.get("value", [])

        docs = []
        for item in items:
            resource = item.get("resourceReference", {})
            resource_vis = item.get("resourceVisualization", {})
            docs.append(
                {
                    "id": resource.get("id"),
                    "title": resource_vis.get("title", "Untitled"),
                    "type": resource_vis.get("type", "unknown"),
                    "web_url": resource.get("webUrl"),
                    "preview_text": resource_vis.get("previewText", "")[:200],
                    "container": resource_vis.get("containerDisplayName"),
                    "last_accessed": item.get("lastUsed", {}).get(
                        "lastAccessedDateTime"
                    ),
                }
            )

        emit_success(f"Found {len(docs)} trending documents")

        return {
            "success": True,
            "count": len(docs),
            "documents": docs,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_trending_docs(agent: Any) -> Tool:
    """Register the get trending docs tool."""
    return agent.tool()(msgraph_get_trending_docs)


# =============================================================================
# RECENTLY USED DOCUMENTS
# =============================================================================


def msgraph_get_recent_docs(
    ctx: RunContext[Any],
    *,
    top: int = 10,
) -> dict:
    """Get documents you recently used.

    Returns documents you've recently viewed, edited, or created,
    ordered by last access time.

    Args:
        top: Maximum number of items to return (default 10, max 100).

    Returns:
        Dict with success and list of recently used documents.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🕒 [bold cyan]Getting recently used documents...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get(
            "/me/insights/used",
            params={
                "$top": min(top, 100),
                "$orderby": "lastUsed/lastAccessedDateTime desc",
            },
        )
        items = response.get("value", [])

        docs = []
        for item in items:
            resource = item.get("resourceReference", {})
            resource_vis = item.get("resourceVisualization", {})
            last_used = item.get("lastUsed", {})
            docs.append(
                {
                    "id": resource.get("id"),
                    "title": resource_vis.get("title", "Untitled"),
                    "type": resource_vis.get("type", "unknown"),
                    "web_url": resource.get("webUrl"),
                    "container": resource_vis.get("containerDisplayName"),
                    "last_accessed": last_used.get("lastAccessedDateTime"),
                    "last_modified": last_used.get("lastModifiedDateTime"),
                }
            )

        emit_success(f"Found {len(docs)} recently used documents")

        return {
            "success": True,
            "count": len(docs),
            "documents": docs,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_recent_docs(agent: Any) -> Tool:
    """Register the get recent docs tool."""
    return agent.tool()(msgraph_get_recent_docs)


# =============================================================================
# SHARED WITH ME
# =============================================================================


def msgraph_get_shared_with_me(
    ctx: RunContext[Any],
    *,
    top: int = 10,
) -> dict:
    """Get documents shared with you.

    Returns documents that others have shared with you,
    ordered by share date.

    Args:
        top: Maximum number of items to return (default 10, max 100).

    Returns:
        Dict with success and list of shared documents.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📩 [bold cyan]Getting documents shared with you...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get(
            "/me/insights/shared",
            params={"$top": min(top, 100)},
        )
        items = response.get("value", [])

        docs = []
        for item in items:
            resource = item.get("resourceReference", {})
            resource_vis = item.get("resourceVisualization", {})
            shared_by = item.get("lastShared", {}).get("sharedBy", {})
            docs.append(
                {
                    "id": resource.get("id"),
                    "title": resource_vis.get("title", "Untitled"),
                    "type": resource_vis.get("type", "unknown"),
                    "web_url": resource.get("webUrl"),
                    "container": resource_vis.get("containerDisplayName"),
                    "shared_by": shared_by.get("displayName"),
                    "shared_by_email": shared_by.get("address"),
                    "shared_date": item.get("lastShared", {}).get("sharedDateTime"),
                }
            )

        emit_success(f"Found {len(docs)} documents shared with you")

        return {
            "success": True,
            "count": len(docs),
            "documents": docs,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_shared_with_me(agent: Any) -> Tool:
    """Register the get shared with me tool."""
    return agent.tool()(msgraph_get_shared_with_me)
