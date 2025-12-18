"""Microsoft Graph Search API tools.

Provides unified search across all Microsoft 365 data:
- Messages (email)
- Events (calendar)
- DriveItems (files)
- Sites (SharePoint)
- Lists (SharePoint lists)
- ListItems (SharePoint list items)
- Chats/ChatMessages (Teams)

This is the most powerful endpoint for context gathering as it
allows searching across ALL data sources in a single query.

API Reference:
https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# UNIFIED SEARCH
# =============================================================================


def msgraph_unified_search(
    ctx: RunContext[Any],
    *,
    query: str,
    entity_types: list[str] | None = None,
    top: int = 10,
) -> dict:
    """Search across all Microsoft 365 data sources.

    This is the most powerful search - queries email, files, calendar,
    SharePoint, and Teams in a single call.

    Args:
        query: Search query (supports KQL syntax).
        entity_types: Types to search. Options:
            - "message" (email)
            - "event" (calendar)
            - "driveItem" (files)
            - "site" (SharePoint sites)
            - "list" (SharePoint lists)
            - "listItem" (SharePoint items)
            - "chatMessage" (Teams messages)
            Default: ["message", "event", "driveItem"]
        top: Results per entity type (default 10, max 25).

    Returns:
        Dict with search results grouped by entity type.
    """
    if entity_types is None:
        entity_types = ["message", "event", "driveItem"]

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Unified search: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build search request
        search_requests = [
            {
                "entityTypes": entity_types,
                "query": {"queryString": query},
                "from": 0,
                "size": min(top, 25),
            }
        ]

        response = client.post(
            "/search/query",
            json={"requests": search_requests},
        )

        results_by_type: dict[str, list] = {}
        total_count = 0

        for result in response.get("value", []):
            for hit_container in result.get("hitsContainers", []):
                if not hit_container.get("hits"):
                    continue

                for hit in hit_container.get("hits", []):
                    resource = hit.get("resource", {})
                    entity_type = resource.get("@odata.type", "").replace(
                        "#microsoft.graph.", ""
                    )

                    if entity_type not in results_by_type:
                        results_by_type[entity_type] = []

                    item = {
                        "id": resource.get("id"),
                        "rank": hit.get("rank"),
                        "summary": hit.get("summary", "")[:200],
                    }

                    # Add type-specific fields
                    if entity_type == "message":
                        item.update(
                            {
                                "subject": resource.get("subject"),
                                "from": resource.get("from", {})
                                .get("emailAddress", {})
                                .get("name"),
                                "received": resource.get("receivedDateTime"),
                                "web_link": resource.get("webLink"),
                            }
                        )
                    elif entity_type == "event":
                        item.update(
                            {
                                "subject": resource.get("subject"),
                                "start": resource.get("start", {}).get("dateTime"),
                                "organizer": resource.get("organizer", {})
                                .get("emailAddress", {})
                                .get("name"),
                                "web_link": resource.get("webLink"),
                            }
                        )
                    elif entity_type == "driveItem":
                        item.update(
                            {
                                "name": resource.get("name"),
                                "web_url": resource.get("webUrl"),
                                "last_modified": resource.get("lastModifiedDateTime"),
                                "created_by": resource.get("createdBy", {})
                                .get("user", {})
                                .get("displayName"),
                            }
                        )
                    elif entity_type == "site":
                        item.update(
                            {
                                "name": resource.get("displayName"),
                                "web_url": resource.get("webUrl"),
                                "description": resource.get("description"),
                            }
                        )
                    elif entity_type == "chatMessage":
                        item.update(
                            {
                                "content": resource.get("body", {}).get("content", "")[
                                    :200
                                ],
                                "from": resource.get("from", {})
                                .get("user", {})
                                .get("displayName"),
                                "created": resource.get("createdDateTime"),
                            }
                        )

                    results_by_type[entity_type].append(item)
                    total_count += 1

        emit_success(f"Found {total_count} results across {len(results_by_type)} types")

        return {
            "success": True,
            "query": query,
            "total_count": total_count,
            "results_by_type": results_by_type,
            "entity_types_searched": entity_types,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_unified_search(agent: Any) -> Tool:
    """Register the unified search tool."""
    return agent.tool()(msgraph_unified_search)


# =============================================================================
# SEARCH EMAILS
# =============================================================================


def msgraph_search_emails_advanced(
    ctx: RunContext[Any],
    *,
    query: str,
    from_address: str | None = None,
    has_attachment: bool | None = None,
    is_unread: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    top: int = 25,
) -> dict:
    """Advanced email search with filters.

    Uses the Search API for powerful email search with KQL filters.

    Args:
        query: Search query (searches subject and body).
        from_address: Filter by sender email/name.
        has_attachment: Filter by attachment presence.
        is_unread: Filter by read status.
        date_from: Filter by received date (YYYY-MM-DD).
        date_to: Filter by received date (YYYY-MM-DD).
        top: Maximum results (default 25).

    Returns:
        Dict with matching emails.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📧 [bold cyan]Advanced email search: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build KQL query
        kql_parts = [query]
        if from_address:
            kql_parts.append(f'from:"{from_address}"')
        if has_attachment is True:
            kql_parts.append("hasAttachment:true")
        if is_unread is True:
            kql_parts.append("isRead:false")
        if date_from:
            kql_parts.append(f"received>={date_from}")
        if date_to:
            kql_parts.append(f"received<={date_to}")

        full_query = " AND ".join(kql_parts)

        search_request = {
            "requests": [
                {
                    "entityTypes": ["message"],
                    "query": {"queryString": full_query},
                    "from": 0,
                    "size": min(top, 25),
                }
            ]
        }

        response = client.post("/search/query", json=search_request)

        emails = []
        for result in response.get("value", []):
            for container in result.get("hitsContainers", []):
                for hit in container.get("hits", []):
                    resource = hit.get("resource", {})
                    emails.append(
                        {
                            "id": resource.get("id"),
                            "subject": resource.get("subject"),
                            "from": resource.get("from", {})
                            .get("emailAddress", {})
                            .get("name"),
                            "from_email": resource.get("from", {})
                            .get("emailAddress", {})
                            .get("address"),
                            "received": resource.get("receivedDateTime"),
                            "preview": hit.get("summary", "")[:200],
                            "has_attachments": resource.get("hasAttachments", False),
                            "is_read": resource.get("isRead", True),
                            "web_link": resource.get("webLink"),
                        }
                    )

        emit_success(f"Found {len(emails)} emails matching query")

        return {
            "success": True,
            "query": full_query,
            "count": len(emails),
            "emails": emails,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_emails_advanced(agent: Any) -> Tool:
    """Register the advanced email search tool."""
    return agent.tool()(msgraph_search_emails_advanced)


# =============================================================================
# SEARCH FILES
# =============================================================================


def msgraph_search_files_advanced(
    ctx: RunContext[Any],
    *,
    query: str,
    file_type: str | None = None,
    author: str | None = None,
    modified_after: str | None = None,
    top: int = 25,
) -> dict:
    """Advanced file search across OneDrive and SharePoint.

    Args:
        query: Search query.
        file_type: Filter by extension (e.g., "docx", "xlsx", "pptx").
        author: Filter by author name.
        modified_after: Filter by modification date (YYYY-MM-DD).
        top: Maximum results (default 25).

    Returns:
        Dict with matching files.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📄 [bold cyan]Advanced file search: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build KQL query
        kql_parts = [query]
        if file_type:
            kql_parts.append(f'fileType:"{file_type}"')
        if author:
            kql_parts.append(f'author:"{author}"')
        if modified_after:
            kql_parts.append(f"lastModifiedTime>={modified_after}")

        full_query = " AND ".join(kql_parts)

        search_request = {
            "requests": [
                {
                    "entityTypes": ["driveItem"],
                    "query": {"queryString": full_query},
                    "from": 0,
                    "size": min(top, 25),
                }
            ]
        }

        response = client.post("/search/query", json=search_request)

        files = []
        for result in response.get("value", []):
            for container in result.get("hitsContainers", []):
                for hit in container.get("hits", []):
                    resource = hit.get("resource", {})
                    files.append(
                        {
                            "id": resource.get("id"),
                            "name": resource.get("name"),
                            "web_url": resource.get("webUrl"),
                            "last_modified": resource.get("lastModifiedDateTime"),
                            "size": resource.get("size"),
                            "created_by": resource.get("createdBy", {})
                            .get("user", {})
                            .get("displayName"),
                            "modified_by": resource.get("lastModifiedBy", {})
                            .get("user", {})
                            .get("displayName"),
                            "preview": hit.get("summary", "")[:200],
                        }
                    )

        emit_success(f"Found {len(files)} files matching query")

        return {
            "success": True,
            "query": full_query,
            "count": len(files),
            "files": files,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_files_advanced(agent: Any) -> Tool:
    """Register the advanced file search tool."""
    return agent.tool()(msgraph_search_files_advanced)


# =============================================================================
# SEARCH TEAMS MESSAGES
# =============================================================================


def msgraph_search_teams_messages(
    ctx: RunContext[Any],
    *,
    query: str,
    from_user: str | None = None,
    top: int = 25,
) -> dict:
    """Search Teams chat messages.

    Args:
        query: Search query.
        from_user: Filter by sender name.
        top: Maximum results (default 25).

    Returns:
        Dict with matching Teams messages.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"💬 [bold cyan]Searching Teams messages: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Build query
        kql_parts = [query]
        if from_user:
            kql_parts.append(f'from:"{from_user}"')

        full_query = " AND ".join(kql_parts)

        search_request = {
            "requests": [
                {
                    "entityTypes": ["chatMessage"],
                    "query": {"queryString": full_query},
                    "from": 0,
                    "size": min(top, 25),
                }
            ]
        }

        response = client.post("/search/query", json=search_request)

        messages = []
        for result in response.get("value", []):
            for container in result.get("hitsContainers", []):
                for hit in container.get("hits", []):
                    resource = hit.get("resource", {})
                    messages.append(
                        {
                            "id": resource.get("id"),
                            "content": resource.get("body", {}).get("content", "")[
                                :300
                            ],
                            "from": resource.get("from", {})
                            .get("user", {})
                            .get("displayName"),
                            "created": resource.get("createdDateTime"),
                            "chat_id": resource.get("chatId"),
                            "channel_id": resource.get("channelIdentity", {}).get(
                                "channelId"
                            ),
                            "preview": hit.get("summary", "")[:200],
                        }
                    )

        emit_success(f"Found {len(messages)} Teams messages matching query")

        return {
            "success": True,
            "query": full_query,
            "count": len(messages),
            "messages": messages,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_teams_messages(agent: Any) -> Tool:
    """Register the search Teams messages tool."""
    return agent.tool()(msgraph_search_teams_messages)
