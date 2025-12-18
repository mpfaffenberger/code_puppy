"""Extended Microsoft Graph Mail tools.

Provides additional granular mail operations:
- Move messages between folders
- Archive messages
- Mark messages as read/unread
- Forward messages
- List and download attachments
- Delete messages
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import get_msgraph_client, _handle_msgraph_error


# =============================================================================
# MESSAGE MANAGEMENT TOOLS
# =============================================================================


def msgraph_move_message(
    ctx: RunContext,
    message_id: str,
    destination_folder: str,
) -> dict:
    """Move a message to a different folder.

    Args:
        message_id: The message ID to move.
        destination_folder: Folder name or ID (e.g., "archive", "deleteditems").

    Returns:
        Dict with success, moved message, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📨 [bold cyan]Moving message to {destination_folder}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.post(
            f"/me/messages/{message_id}/move",
            json={"destinationId": destination_folder},
        )

        emit_success(f"Message moved to {destination_folder}")

        return {
            "success": True,
            "message_id": response.get("id"),
            "new_folder": destination_folder,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_move_message(agent: Any) -> Tool:
    """Register the msgraph_move_message tool."""
    return agent.tool(msgraph_move_message)


def msgraph_archive_message(ctx: RunContext, message_id: str) -> dict:
    """Archive a message (move to Archive folder).

    Args:
        message_id: The message ID to archive.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📦 [bold cyan]Archiving message[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.post(
            f"/me/messages/{message_id}/move", json={"destinationId": "archive"}
        )

        emit_success("Message archived")

        return {
            "success": True,
            "message_id": response.get("id"),
            "action": "archived",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_archive_message(agent: Any) -> Tool:
    """Register the msgraph_archive_message tool."""
    return agent.tool(msgraph_archive_message)


def msgraph_mark_as_read(ctx: RunContext, message_id: str) -> dict:
    """Mark a message as read.

    Args:
        message_id: The message ID.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "✅ [bold cyan]Marking message as read[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        client.patch(f"/me/messages/{message_id}", json={"isRead": True})

        emit_success("Message marked as read")

        return {
            "success": True,
            "message_id": message_id,
            "is_read": True,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_mark_as_read(agent: Any) -> Tool:
    """Register the msgraph_mark_as_read tool."""
    return agent.tool(msgraph_mark_as_read)


def msgraph_mark_as_unread(ctx: RunContext, message_id: str) -> dict:
    """Mark a message as unread.

    Args:
        message_id: The message ID.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "⚪ [bold cyan]Marking message as unread[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        client.patch(f"/me/messages/{message_id}", json={"isRead": False})

        emit_success("Message marked as unread")

        return {
            "success": True,
            "message_id": message_id,
            "is_read": False,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_mark_as_unread(agent: Any) -> Tool:
    """Register the msgraph_mark_as_unread tool."""
    return agent.tool(msgraph_mark_as_unread)


def msgraph_forward_message(
    ctx: RunContext,
    message_id: str,
    to_recipients: list[str],
    comment: str | None = None,
) -> dict:
    """Forward a message to other recipients.

    Args:
        message_id: The message ID to forward.
        to_recipients: List of email addresses to forward to.
        comment: Optional comment to include.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"➡️ [bold cyan]Forwarding message to {len(to_recipients)} recipient(s)[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        forward_data: dict[str, Any] = {
            "toRecipients": [
                {"emailAddress": {"address": email}} for email in to_recipients
            ]
        }

        if comment:
            forward_data["comment"] = comment

        client.post(f"/me/messages/{message_id}/forward", json=forward_data)

        emit_success(f"Message forwarded to {', '.join(to_recipients)}")

        return {
            "success": True,
            "forwarded_to": to_recipients,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_forward_message(agent: Any) -> Tool:
    """Register the msgraph_forward_message tool."""
    return agent.tool(msgraph_forward_message)


def msgraph_delete_message(ctx: RunContext, message_id: str) -> dict:
    """Delete a message (moves to Deleted Items).

    Args:
        message_id: The message ID to delete.

    Returns:
        Dict with success or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🗑️ [bold cyan]Deleting message[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        client.delete(f"/me/messages/{message_id}")

        emit_success("Message deleted")

        return {
            "success": True,
            "message_id": message_id,
            "action": "deleted",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_message(agent: Any) -> Tool:
    """Register the msgraph_delete_message tool."""
    return agent.tool(msgraph_delete_message)


# =============================================================================
# ATTACHMENT TOOLS
# =============================================================================


def msgraph_list_attachments(ctx: RunContext, message_id: str) -> dict:
    """List attachments on a message.

    Args:
        message_id: The message ID.

    Returns:
        Dict with success, attachments list, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📎 [bold cyan]Listing attachments[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.get(f"/me/messages/{message_id}/attachments")
        attachments_data = response.get("value", [])

        attachments = []
        for att in attachments_data:
            attachments.append(
                {
                    "id": att.get("id"),
                    "name": att.get("name"),
                    "content_type": att.get("contentType"),
                    "size": att.get("size"),
                    "is_inline": att.get("isInline", False),
                }
            )

        emit_success(f"Found {len(attachments)} attachment(s)")

        return {
            "success": True,
            "attachments": attachments,
            "total_count": len(attachments),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_attachments(agent: Any) -> Tool:
    """Register the msgraph_list_attachments tool."""
    return agent.tool(msgraph_list_attachments)


def msgraph_get_attachment(
    ctx: RunContext,
    message_id: str,
    attachment_id: str,
) -> dict:
    """Get attachment details and content.

    Args:
        message_id: The message ID.
        attachment_id: The attachment ID.

    Returns:
        Dict with success, attachment details including base64 content, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📎 [bold cyan]Getting attachment[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.get(f"/me/messages/{message_id}/attachments/{attachment_id}")

        attachment = {
            "id": response.get("id"),
            "name": response.get("name"),
            "content_type": response.get("contentType"),
            "size": response.get("size"),
            "is_inline": response.get("isInline", False),
            "content_bytes": response.get("contentBytes"),  # Base64 encoded
        }

        emit_success(f"Retrieved attachment: {attachment.get('name')}")

        return {
            "success": True,
            "attachment": attachment,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_attachment(agent: Any) -> Tool:
    """Register the msgraph_get_attachment tool."""
    return agent.tool(msgraph_get_attachment)
