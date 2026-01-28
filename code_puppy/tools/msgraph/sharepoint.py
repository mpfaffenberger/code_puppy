"""Microsoft Graph SharePoint tools.

Provides tools for:
- Listing and searching SharePoint sites
- Getting site details
- Listing document libraries (drives) in a site
- Listing files and folders in a site
- Searching across SharePoint content
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    truncate_list_response,
    MAX_RESPONSE_CHARS,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_site(site: dict) -> dict:
    """Format a SharePoint site for display.

    Args:
        site: Raw site data from MS Graph API.

    Returns:
        Formatted site dict with key fields.
    """
    return {
        "id": site.get("id"),
        "name": site.get("displayName") or site.get("name"),
        "description": site.get("description"),
        "web_url": site.get("webUrl"),
        "created": site.get("createdDateTime"),
        "last_modified": site.get("lastModifiedDateTime"),
    }


def _format_drive(drive: dict) -> dict:
    """Format a document library (drive) for display.

    Args:
        drive: Raw drive data from MS Graph API.

    Returns:
        Formatted drive dict with key fields.
    """
    return {
        "id": drive.get("id"),
        "name": drive.get("name"),
        "description": drive.get("description"),
        "web_url": drive.get("webUrl"),
        "drive_type": drive.get("driveType"),
        "quota": drive.get("quota"),
    }


def _format_drive_item(item: dict) -> dict:
    """Format a drive item for display.

    Args:
        item: Raw drive item data from MS Graph API.

    Returns:
        Formatted drive item dict with key fields.
    """
    # Determine item type
    if "folder" in item:
        item_type = "folder"
        child_count = item.get("folder", {}).get("childCount", 0)
    elif "file" in item:
        item_type = "file"
        child_count = None
    else:
        item_type = "unknown"
        child_count = None

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": item_type,
        "size": item.get("size", 0),
        "last_modified": item.get("lastModifiedDateTime"),
        "created": item.get("createdDateTime"),
        "web_url": item.get("webUrl"),
        "child_count": child_count,
        "mime_type": item.get("file", {}).get("mimeType")
        if item_type == "file"
        else None,
    }


def _format_search_hit(hit: dict) -> dict:
    """Format a search hit for display.

    Args:
        hit: Raw search hit data from MS Graph API.

    Returns:
        Formatted search hit dict with key fields.
    """
    resource = hit.get("resource", {})
    return {
        "id": resource.get("id"),
        "name": resource.get("name"),
        "web_url": resource.get("webUrl"),
        "last_modified": resource.get("lastModifiedDateTime"),
        "size": resource.get("size"),
        "summary": hit.get("summary"),
    }


def _normalize_path(path: str) -> str:
    """Normalize a path for use in API calls.

    Args:
        path: The path to normalize.

    Returns:
        Normalized path with proper formatting.
    """
    # Remove leading/trailing slashes for path building
    return path.strip("/")


# =============================================================================
# LIST SITES TOOL
# =============================================================================


def msgraph_list_sites(
    ctx: RunContext,
    query: str | None = None,
    limit: int = 10,
) -> dict:
    """List or search SharePoint sites.

    Args:
        query: Optional search query (if None, lists followed sites).
        limit: Maximum sites to return (default 10).

    Returns:
        Dict with success, sites list (id, name, webUrl), or error.
    """
    action = f"Searching sites: '{query}'" if query else "Listing followed sites"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🏢 [bold cyan]{action}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        if query:
            # Search sites
            endpoint = "/sites"
            params = {
                "search": query,
                "$top": limit,
                "$select": "id,displayName,name,description,webUrl,"
                "createdDateTime,lastModifiedDateTime",
            }
        else:
            # List followed sites
            endpoint = "/me/followedSites"
            params = {
                "$top": limit,
                "$select": "id,displayName,name,description,webUrl,"
                "createdDateTime,lastModifiedDateTime",
            }

        response = client.get(endpoint, params=params)
        sites_data = response.get("value", [])

        sites = [_format_site(site) for site in sites_data]
        total_count = len(sites)

        emit_success(f"Found {total_count} site(s)")

        return {
            "success": True,
            "sites": sites,
            "total_count": total_count,
            "query": query,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_sites(agent: Any) -> Tool:
    """Register the msgraph_list_sites tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_sites)


# =============================================================================
# GET SITE TOOL
# =============================================================================


def msgraph_get_site(
    ctx: RunContext,
    site_id: str,
) -> dict:
    """Get details about a SharePoint site.

    Args:
        site_id: The site ID or path (e.g., "contoso.sharepoint.com:/sites/team").

    Returns:
        Dict with success, site details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🏢 [bold cyan]Getting site: {site_id[:50]}{'...' if len(site_id) > 50 else ''}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint - site_id can be an ID or a path like "hostname:/path"
        endpoint = f"/sites/{site_id}"

        params = {
            "$select": "id,displayName,name,description,webUrl,"
            "createdDateTime,lastModifiedDateTime,siteCollection",
        }

        site_data = client.get(endpoint, params=params)
        site = _format_site(site_data)

        # Add site collection info if available
        site_collection = site_data.get("siteCollection", {})
        if site_collection:
            site["hostname"] = site_collection.get("hostname")
            site["root"] = site_collection.get("root")

        emit_success(f"Retrieved site: {site['name']}")

        return {
            "success": True,
            "site": site,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_site(agent: Any) -> Tool:
    """Register the msgraph_get_site tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_site)


# =============================================================================
# LIST SITE DRIVES TOOL
# =============================================================================


def msgraph_list_site_drives(
    ctx: RunContext,
    site_id: str,
) -> dict:
    """List document libraries in a SharePoint site.

    Args:
        site_id: The site ID.

    Returns:
        Dict with success, drives list (id, name, webUrl), or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📚 [bold cyan]Listing drives for site: {site_id[:30]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/sites/{site_id}/drives"

        params = {
            "$select": "id,name,description,webUrl,driveType,quota",
        }

        response = client.get(endpoint, params=params)
        drives_data = response.get("value", [])

        drives = [_format_drive(drive) for drive in drives_data]
        total_count = len(drives)

        emit_success(f"Found {total_count} document library(ies)")

        return {
            "success": True,
            "drives": drives,
            "total_count": total_count,
            "site_id": site_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_site_drives(agent: Any) -> Tool:
    """Register the msgraph_list_site_drives tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_site_drives)


# =============================================================================
# LIST SITE ITEMS TOOL
# =============================================================================


def msgraph_list_site_items(
    ctx: RunContext,
    site_id: str,
    drive_id: str | None = None,
    path: str = "/",
    limit: int = 25,
    item_offset: int = 0,
) -> dict:
    """List files and folders in a SharePoint site.

    Args:
        site_id: The site ID.
        drive_id: The drive/library ID (optional, uses default if not specified).
        path: Folder path (default "/" for root).
        limit: Maximum items to return (default 25).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, items list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    display_path = path if path != "/" else "root"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📁 [bold cyan]Listing site items: {display_path}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint based on whether drive_id and path are provided
        normalized_path = _normalize_path(path)

        if drive_id:
            # Use specific drive
            if normalized_path == "" or path == "/":
                endpoint = f"/sites/{site_id}/drives/{drive_id}/root/children"
            else:
                endpoint = f"/sites/{site_id}/drives/{drive_id}/root:/{normalized_path}:/children"
        else:
            # Use default drive
            if normalized_path == "" or path == "/":
                endpoint = f"/sites/{site_id}/drive/root/children"
            else:
                endpoint = f"/sites/{site_id}/drive/root:/{normalized_path}:/children"

        params = {
            "$top": limit,
            "$orderby": "name asc",
            "$select": "id,name,size,lastModifiedDateTime,createdDateTime,"
            "webUrl,folder,file",
        }

        response = client.get(endpoint, params=params)
        items_data = response.get("value", [])

        items = [_format_drive_item(item) for item in items_data]

        # Apply list truncation
        list_result = truncate_list_response(
            items, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        # Count folders and files from returned items
        folder_count = sum(1 for i in list_result["items"] if i["type"] == "folder")
        file_count = sum(1 for i in list_result["items"] if i["type"] == "file")

        emit_success(
            f"Found {list_result['items_returned']} item(s): {folder_count} folder(s), {file_count} file(s)"
        )

        result = {
            "success": True,
            "items": list_result["items"],
            "total_count": len(items),
            "site_id": site_id,
            "drive_id": drive_id,
            "path": path,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_site_items(agent: Any) -> Tool:
    """Register the msgraph_list_site_items tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_site_items)


# =============================================================================
# SEARCH SHAREPOINT TOOL
# =============================================================================


def msgraph_search_sharepoint(
    ctx: RunContext,
    query: str,
    limit: int = 10,
    item_offset: int = 0,
) -> dict:
    """Search across all SharePoint content.

    Args:
        query: Search query.
        limit: Maximum results (default 10).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, results list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching SharePoint: '{query}'[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Use the Microsoft Search API for comprehensive SharePoint search
        endpoint = "/search/query"

        payload = {
            "requests": [
                {
                    "entityTypes": ["driveItem", "listItem", "site"],
                    "query": {
                        "queryString": query,
                    },
                    "from": 0,
                    "size": limit,
                }
            ]
        }

        response = client.post(endpoint, json=payload)

        # Parse search results
        results = []
        search_response = response.get("value", [])

        for search_result in search_response:
            hits_containers = search_result.get("hitsContainers", [])
            for container in hits_containers:
                hits = container.get("hits", [])
                for hit in hits:
                    results.append(_format_search_hit(hit))

        # Apply list truncation
        list_result = truncate_list_response(
            results, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(
            f"Found {list_result['items_returned']} result(s) for '{query}'"
        )

        result = {
            "success": True,
            "results": list_result["items"],
            "total_count": len(results),
            "query": query,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_sharepoint(agent: Any) -> Tool:
    """Register the msgraph_search_sharepoint tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_search_sharepoint)
