"""Microsoft Graph OneDrive tools.

Provides tools for:
- Listing files and folders
- Getting file/folder metadata
- Downloading file content
- Uploading files
- Creating folders
- Sharing files
- Searching files
- Deleting files and folders
"""

import base64
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    truncate_content,
    truncate_list_response,
    MAX_RESPONSE_CHARS,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


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


def _normalize_path(path: str) -> str:
    """Normalize a OneDrive path.

    Args:
        path: The path to normalize.

    Returns:
        Normalized path with proper formatting.
    """
    # Remove leading/trailing slashes for path building
    path = path.strip("/")
    return path


def _is_text_file(mime_type: str | None, filename: str) -> bool:
    """Determine if a file is a text file based on mime type or extension.

    Args:
        mime_type: The MIME type of the file.
        filename: The filename to check extension.

    Returns:
        True if the file is likely a text file.
    """
    text_mime_prefixes = (
        "text/",
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-python",
        "application/x-sh",
        "application/x-yaml",
    )

    if mime_type and any(mime_type.startswith(prefix) for prefix in text_mime_prefixes):
        return True

    # Check extension
    text_extensions = {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".json",
        ".yaml",
        ".yml",
        ".xml",
        ".html",
        ".css",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".java",
        ".go",
        ".rs",
        ".sql",
        ".graphql",
        ".csv",
        ".log",
        ".ini",
        ".cfg",
        ".toml",
        ".env",
        ".gitignore",
        ".dockerfile",
    }

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in text_extensions


# =============================================================================
# LIST DRIVE ITEMS TOOL
# =============================================================================


def msgraph_list_drive_items(
    ctx: RunContext,
    path: str = "/",
    limit: int = 25,
    item_offset: int = 0,
) -> dict:
    """List files and folders in OneDrive.

    Args:
        path: Folder path (default "/" for root).
        limit: Maximum items to return (default 25).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, items list (name, size, type, lastModified), or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    display_path = path if path != "/" else "root"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📁 [bold cyan]Listing OneDrive: {display_path}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint based on path
        normalized_path = _normalize_path(path)
        if normalized_path == "" or path == "/":
            endpoint = "/me/drive/root/children"
        else:
            endpoint = f"/me/drive/root:/{normalized_path}:/children"

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

        # Count folders and files from the returned items
        folder_count = sum(1 for i in list_result["items"] if i["type"] == "folder")
        file_count = sum(1 for i in list_result["items"] if i["type"] == "file")

        emit_success(
            f"Found {list_result['items_returned']} item(s): {folder_count} folder(s), {file_count} file(s)"
        )

        result = {
            "success": True,
            "items": list_result["items"],
            "total_count": len(items),
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


def register_msgraph_list_drive_items(agent: Any) -> Tool:
    """Register the msgraph_list_drive_items tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_drive_items)


# =============================================================================
# GET DRIVE ITEM TOOL
# =============================================================================


def msgraph_get_drive_item(
    ctx: RunContext,
    item_id: str | None = None,
    path: str | None = None,
) -> dict:
    """Get file or folder metadata.

    Args:
        item_id: The item ID (optional if path provided).
        path: The file path (optional if item_id provided).

    Returns:
        Dict with success, item details, or error.
    """
    if not item_id and not path:
        return {
            "success": False,
            "error": "Either item_id or path must be provided",
            "error_type": "validation",
        }

    identifier = item_id or path
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📄 [bold cyan]Getting item: {identifier}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint based on what was provided
        if item_id:
            endpoint = f"/me/drive/items/{item_id}"
        else:
            normalized_path = _normalize_path(path)  # type: ignore
            endpoint = f"/me/drive/root:/{normalized_path}"

        params = {
            "$select": "id,name,size,lastModifiedDateTime,createdDateTime,"
            "webUrl,folder,file,parentReference",
        }

        item_data = client.get(endpoint, params=params)
        item = _format_drive_item(item_data)

        # Add parent info if available
        parent_ref = item_data.get("parentReference", {})
        item["parent_path"] = parent_ref.get("path", "").replace("/drive/root:", "")

        emit_success(f"Retrieved item: {item['name']} ({item['type']})")

        return {
            "success": True,
            "item": item,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_drive_item(agent: Any) -> Tool:
    """Register the msgraph_get_drive_item tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_drive_item)


# =============================================================================
# DOWNLOAD FILE TOOL
# =============================================================================


def msgraph_download_file(
    ctx: RunContext,
    item_id: str | None = None,
    path: str | None = None,
    max_size_mb: int = 10,
    char_offset: int = 0,
) -> dict:
    """Download a file's content.

    Args:
        item_id: The item ID (optional if path provided).
        path: The file path (optional if item_id provided).
        max_size_mb: Maximum file size to download in MB (default 10).
        char_offset: Character offset for paginating large text files (default 0).
            If content exceeds 10,000 chars, use the returned next_offset value
            to continue reading. Only applies to text files.

    Returns:
        Dict with success, content (text for text files, base64 for binary),
        metadata, or error. If truncated: truncated=True, next_offset, total_chars.
    """
    if not item_id and not path:
        return {
            "success": False,
            "error": "Either item_id or path must be provided",
            "error_type": "validation",
        }

    identifier = item_id or path
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"⬇️ [bold cyan]Downloading: {identifier}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # First, get the item metadata to check size and type
        if item_id:
            metadata_endpoint = f"/me/drive/items/{item_id}"
        else:
            normalized_path = _normalize_path(path)  # type: ignore
            metadata_endpoint = f"/me/drive/root:/{normalized_path}"

        item_data = client.get(metadata_endpoint)

        # Check if it's a folder
        if "folder" in item_data:
            emit_warning("Cannot download a folder")
            return {
                "success": False,
                "error": "Cannot download a folder. Use msgraph_list_drive_items instead.",
                "error_type": "validation",
            }

        # Check file size
        file_size = item_data.get("size", 0)
        max_size_bytes = max_size_mb * 1024 * 1024

        if file_size > max_size_bytes:
            size_mb = file_size / (1024 * 1024)
            emit_warning(f"File too large: {size_mb:.2f} MB (max: {max_size_mb} MB)")
            return {
                "success": False,
                "error": f"File size ({size_mb:.2f} MB) exceeds maximum "
                f"({max_size_mb} MB). Increase max_size_mb if needed.",
                "error_type": "file_too_large",
                "file_size_mb": size_mb,
            }

        # Download the content
        # Use the item ID from metadata to ensure we have it
        actual_item_id = item_data.get("id")
        download_endpoint = f"/me/drive/items/{actual_item_id}/content"

        # Get raw content (client.get_raw returns bytes)
        content_bytes = client.get_raw(download_endpoint)

        # Determine if text or binary
        filename = item_data.get("name", "")
        mime_type = item_data.get("file", {}).get("mimeType")
        is_text = _is_text_file(mime_type, filename)

        if is_text:
            # Try to decode as text
            try:
                content = content_bytes.decode("utf-8")
                content_encoding = "text"

                # Apply truncation for text content
                if len(content) > MAX_RESPONSE_CHARS:
                    truncation = truncate_content(
                        content, char_offset=char_offset, max_chars=MAX_RESPONSE_CHARS
                    )
                    content = truncation["content"]
                    truncated = truncation["truncated"]
                    next_offset = truncation["next_offset"]
                    total_chars = truncation["total_chars"]
                else:
                    truncated = False
                    next_offset = None
                    total_chars = len(content)

            except UnicodeDecodeError:
                # Fall back to base64
                content = base64.b64encode(content_bytes).decode("ascii")
                content_encoding = "base64"
                truncated = False
                next_offset = None
                total_chars = len(content)
        else:
            # Binary file - encode as base64
            content = base64.b64encode(content_bytes).decode("ascii")
            content_encoding = "base64"
            truncated = False
            next_offset = None
            total_chars = len(content)

        emit_success(f"Downloaded: {filename} ({file_size} bytes)")

        result = {
            "success": True,
            "content": content,
            "encoding": content_encoding,
            "truncated": truncated,
            "total_chars": total_chars,
            "metadata": {
                "id": actual_item_id,
                "name": filename,
                "size": file_size,
                "mime_type": mime_type,
                "last_modified": item_data.get("lastModifiedDateTime"),
            },
        }

        if truncated:
            result["char_offset"] = char_offset
            result["next_offset"] = next_offset
            result[
                "truncation_message"
            ] = f"Content truncated. Use char_offset={next_offset} to continue."

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_download_file(agent: Any) -> Tool:
    """Register the msgraph_download_file tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_download_file)


# =============================================================================
# UPLOAD FILE TOOL
# =============================================================================


def msgraph_upload_file(
    ctx: RunContext,
    path: str,
    content: str,
    content_type: str = "text/plain",
) -> dict:
    """Upload a file to OneDrive.

    Uses simple upload (up to 4MB). For larger files, use resumable upload.

    Args:
        path: Destination path including filename (e.g., "/Documents/notes.txt").
        content: File content as string.
        content_type: MIME type (default "text/plain").

    Returns:
        Dict with success, created item (id, name, webUrl), or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"⬆️ [bold cyan]Uploading to: {path}[/bold cyan]"
        )
    )

    # Check content size (simple upload limit is 4MB)
    content_bytes = content.encode("utf-8")
    max_simple_upload = 4 * 1024 * 1024  # 4MB

    if len(content_bytes) > max_simple_upload:
        size_mb = len(content_bytes) / (1024 * 1024)
        emit_warning(f"File too large for simple upload: {size_mb:.2f} MB")
        return {
            "success": False,
            "error": f"File size ({size_mb:.2f} MB) exceeds simple upload limit (4 MB). "
            "Large file upload is not yet supported.",
            "error_type": "file_too_large",
        }

    try:
        client = get_msgraph_client()

        # Build endpoint
        normalized_path = _normalize_path(path)
        endpoint = f"/me/drive/root:/{normalized_path}:/content"

        # Upload the content
        item_data = client.put(
            endpoint,
            data=content_bytes,
            headers={"Content-Type": content_type},
        )

        item = _format_drive_item(item_data)

        emit_success(f"Uploaded: {item['name']} ({len(content_bytes)} bytes)")

        return {
            "success": True,
            "item": {
                "id": item["id"],
                "name": item["name"],
                "web_url": item["web_url"],
                "size": item["size"],
            },
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_upload_file(agent: Any) -> Tool:
    """Register the msgraph_upload_file tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_upload_file)


# =============================================================================
# CREATE FOLDER TOOL
# =============================================================================


def msgraph_create_folder(
    ctx: RunContext,
    path: str,
    name: str,
) -> dict:
    """Create a folder in OneDrive.

    Args:
        path: Parent folder path (e.g., "/Documents" or "/" for root).
        name: Name of the new folder.

    Returns:
        Dict with success, created folder, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📁 [bold cyan]Creating folder: {name} in {path}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint based on path
        normalized_path = _normalize_path(path)
        if normalized_path == "" or path == "/":
            endpoint = "/me/drive/root/children"
        else:
            endpoint = f"/me/drive/root:/{normalized_path}:/children"

        # Create folder payload
        payload = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }

        item_data = client.post(endpoint, json=payload)
        item = _format_drive_item(item_data)

        emit_success(f"Created folder: {item['name']}")

        return {
            "success": True,
            "folder": {
                "id": item["id"],
                "name": item["name"],
                "web_url": item["web_url"],
            },
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_folder(agent: Any) -> Tool:
    """Register the msgraph_create_folder tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_create_folder)


# =============================================================================
# SHARE FILE TOOL
# =============================================================================


def msgraph_share_file(
    ctx: RunContext,
    item_id: str,
    share_type: str = "view",
    scope: str = "organization",
) -> dict:
    """Create a sharing link for a file.

    Args:
        item_id: The item ID to share.
        share_type: "view" or "edit" (default "view").
        scope: "anonymous", "organization", or "users" (default "organization").

    Returns:
        Dict with success, sharing link, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔗 [bold cyan]Creating {share_type} link for: {item_id[:20]}...[/bold cyan]"
        )
    )

    # Validate share_type
    if share_type not in ("view", "edit"):
        return {
            "success": False,
            "error": f"Invalid share_type: {share_type}. Must be 'view' or 'edit'.",
            "error_type": "validation",
        }

    # Validate scope
    if scope not in ("anonymous", "organization", "users"):
        return {
            "success": False,
            "error": f"Invalid scope: {scope}. "
            "Must be 'anonymous', 'organization', or 'users'.",
            "error_type": "validation",
        }

    try:
        client = get_msgraph_client()

        endpoint = f"/me/drive/items/{item_id}/createLink"

        payload = {
            "type": share_type,
            "scope": scope,
        }

        response = client.post(endpoint, json=payload)

        link_data = response.get("link", {})
        share_url = link_data.get("webUrl")

        emit_success(f"Created {scope} {share_type} link")

        return {
            "success": True,
            "link": {
                "url": share_url,
                "type": share_type,
                "scope": scope,
            },
            "item_id": item_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_share_file(agent: Any) -> Tool:
    """Register the msgraph_share_file tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_share_file)


# =============================================================================
# SEARCH FILES TOOL
# =============================================================================


def msgraph_search_files(
    ctx: RunContext,
    query: str,
    limit: int = 10,
    item_offset: int = 0,
) -> dict:
    """Search for files in OneDrive.

    Args:
        query: Search query.
        limit: Maximum results (default 10).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, items list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching OneDrive: '{query}'[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Use the search endpoint
        endpoint = f"/me/drive/root/search(q='{query}')"

        params = {
            "$top": limit,
            "$select": "id,name,size,lastModifiedDateTime,createdDateTime,"
            "webUrl,folder,file,parentReference",
        }

        response = client.get(endpoint, params=params)
        items_data = response.get("value", [])

        items = []
        for item_data in items_data:
            item = _format_drive_item(item_data)
            # Add parent path for context
            parent_ref = item_data.get("parentReference", {})
            item["parent_path"] = parent_ref.get("path", "").replace("/drive/root:", "")
            items.append(item)

        # Apply list truncation
        list_result = truncate_list_response(
            items, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(
            f"Found {list_result['items_returned']} item(s) matching '{query}'"
        )

        result = {
            "success": True,
            "items": list_result["items"],
            "total_count": len(items),
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


def register_msgraph_search_files(agent: Any) -> Tool:
    """Register the msgraph_search_files tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_search_files)


# =============================================================================
# DELETE DRIVE ITEM TOOL
# =============================================================================


def msgraph_delete_drive_item(
    ctx: RunContext,
    item_id: str,
) -> dict:
    """Delete a file or folder.

    Args:
        item_id: The item ID to delete.

    Returns:
        Dict with success, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🗑️ [bold cyan]Deleting item: {item_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/me/drive/items/{item_id}"

        # DELETE returns no content on success
        client.delete(endpoint)

        emit_success("Item deleted successfully")

        return {
            "success": True,
            "message": "Item deleted successfully",
            "item_id": item_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_drive_item(agent: Any) -> Tool:
    """Register the msgraph_delete_drive_item tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_delete_drive_item)
