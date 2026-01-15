"""Microsoft Graph Mail (Outlook) tools.

Provides tools for:
- Listing messages from mail folders
- Getting specific messages with full body
- Sending emails
- Replying to messages
- Searching emails
- Listing mail folders
"""

import re
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    markdown_to_html,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _strip_html_tags(html: str) -> str:
    """Strip HTML tags from a string for cleaner text output.

    Args:
        html: HTML string to clean.

    Returns:
        Plain text with HTML tags removed.
    """
    if not html:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _format_message_preview(msg: dict) -> dict:
    """Format a message for list/preview display.

    Args:
        msg: Raw message data from MS Graph API.

    Returns:
        Formatted message dict with key preview fields.
    """
    from_info = msg.get("from", {})
    from_email = from_info.get("emailAddress", {})

    return {
        "id": msg.get("id"),
        "subject": msg.get("subject", "(No Subject)"),
        "from": {
            "name": from_email.get("name"),
            "email": from_email.get("address"),
        },
        "received": msg.get("receivedDateTime"),
        "preview": msg.get("bodyPreview", "")[:200],
        "is_read": msg.get("isRead", False),
        "has_attachments": msg.get("hasAttachments", False),
        "importance": msg.get("importance", "normal"),
    }


def _format_email_address(addr: dict) -> dict:
    """Format an email address object.

    Args:
        addr: Email address dict from MS Graph.

    Returns:
        Formatted dict with name and email.
    """
    email_addr = addr.get("emailAddress", {})
    return {
        "name": email_addr.get("name"),
        "email": email_addr.get("address"),
    }


def _format_message_full(msg: dict) -> dict:
    """Format a message for full display.

    Args:
        msg: Raw message data from MS Graph API.

    Returns:
        Formatted message dict with all fields including body.
    """
    from_info = msg.get("from", {})
    from_email = from_info.get("emailAddress", {})

    # Get recipients
    to_recipients = [_format_email_address(r) for r in msg.get("toRecipients", [])]
    cc_recipients = [_format_email_address(r) for r in msg.get("ccRecipients", [])]
    bcc_recipients = [_format_email_address(r) for r in msg.get("bccRecipients", [])]

    # Get body
    body_data = msg.get("body", {})
    body_content = body_data.get("content", "")
    body_type = body_data.get("contentType", "text")

    # Convert HTML body to plain text for cleaner output
    if body_type.lower() == "html":
        body_text = _strip_html_tags(body_content)
    else:
        body_text = body_content

    return {
        "id": msg.get("id"),
        "subject": msg.get("subject", "(No Subject)"),
        "from": {
            "name": from_email.get("name"),
            "email": from_email.get("address"),
        },
        "to": to_recipients,
        "cc": cc_recipients,
        "bcc": bcc_recipients,
        "body": body_text,
        "body_type": body_type,
        "received": msg.get("receivedDateTime"),
        "sent": msg.get("sentDateTime"),
        "is_read": msg.get("isRead", False),
        "has_attachments": msg.get("hasAttachments", False),
        "importance": msg.get("importance", "normal"),
        "conversation_id": msg.get("conversationId"),
    }


def _format_folder(folder: dict) -> dict:
    """Format a mail folder for display.

    Args:
        folder: Raw folder data from MS Graph API.

    Returns:
        Formatted folder dict.
    """
    return {
        "id": folder.get("id"),
        "display_name": folder.get("displayName"),
        "unread_count": folder.get("unreadItemCount", 0),
        "total_count": folder.get("totalItemCount", 0),
        "parent_folder_id": folder.get("parentFolderId"),
    }


# =============================================================================
# LIST MESSAGES TOOL
# =============================================================================


def msgraph_list_messages(
    ctx: RunContext,
    folder: str = "inbox",
    limit: int = 10,
    skip: int = 0,
    filter_unread: bool = False,
) -> dict:
    """List messages from a mail folder.

    Args:
        folder: Mail folder - "inbox", "sentitems", "drafts",
                "deleteditems", or folder ID.
        limit: Maximum messages to return (default 10).
        skip: Number of messages to skip for pagination (default 0).
        filter_unread: If True, only return unread messages.

    Returns:
        Dict with success, messages list (subject, from, received, preview),
        total_count.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📧 [bold cyan]Listing messages from: {folder}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build endpoint
        endpoint = f"/me/mailFolders/{folder}/messages"

        # Build params
        params = {
            "$top": limit,
            "$skip": skip,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,"
            "isRead,hasAttachments,importance",
        }

        if filter_unread:
            params["$filter"] = "isRead eq false"

        response = client.get(endpoint, params=params)
        messages_data = response.get("value", [])

        messages = [_format_message_preview(m) for m in messages_data]
        total_count = len(messages)

        unread_note = " (unread only)" if filter_unread else ""
        emit_success(f"Retrieved {total_count} message(s) from {folder}{unread_note}")

        return {
            "success": True,
            "messages": messages,
            "total_count": total_count,
            "folder": folder,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_messages(agent: Any) -> Tool:
    """Register the msgraph_list_messages tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_messages)


# =============================================================================
# GET MESSAGE TOOL
# =============================================================================


def msgraph_get_message(ctx: RunContext, message_id: str) -> dict:
    """Get a specific email message with full body.

    Args:
        message_id: The message ID.

    Returns:
        Dict with success, message (subject, from, to, cc, body, received, etc.).
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📧 [bold cyan]Getting message: {message_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/me/messages/{message_id}"
        params = {
            "$select": "id,subject,from,toRecipients,ccRecipients,"
            "bccRecipients,body,receivedDateTime,sentDateTime,"
            "isRead,hasAttachments,importance,conversationId",
        }

        msg_data = client.get(endpoint, params=params)
        message = _format_message_full(msg_data)

        emit_success(f"Retrieved message: {message['subject']}")

        return {
            "success": True,
            "message": message,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_message(agent: Any) -> Tool:
    """Register the msgraph_get_message tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_message)


# =============================================================================
# SEND MAIL TOOL
# =============================================================================


def msgraph_send_mail(
    ctx: RunContext,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    is_html: bool = False,
) -> dict:
    """Send an email.

    Args:
        to: List of recipient email addresses.
        subject: Email subject.
        body: Email body (plain text or HTML).
        cc: Optional list of CC recipients.
        bcc: Optional list of BCC recipients.
        is_html: If True, body is HTML; otherwise plain text.

    Returns:
        Dict with success, or error.
    """
    recipients_str = ", ".join(to[:3])
    if len(to) > 3:
        recipients_str += f" (+{len(to) - 3} more)"

    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✉️ [bold cyan]Sending mail to: {recipients_str}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build recipient lists
        def _make_recipient(email: str) -> dict:
            return {"emailAddress": {"address": email}}

        to_recipients = [_make_recipient(email) for email in to]
        cc_recipients = [_make_recipient(email) for email in (cc or [])]
        bcc_recipients = [_make_recipient(email) for email in (bcc or [])]

        # Build message payload
        message = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if is_html else "Text",
                "content": body,
            },
            "toRecipients": to_recipients,
        }

        if cc_recipients:
            message["ccRecipients"] = cc_recipients
        if bcc_recipients:
            message["bccRecipients"] = bcc_recipients

        payload = {"message": message}

        # Send the mail
        client.post("/me/sendMail", json=payload)

        emit_success(f"Email sent successfully! Subject: {subject}")

        return {
            "success": True,
            "message": "Email sent successfully",
            "to": to,
            "subject": subject,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_send_mail(agent: Any) -> Tool:
    """Register the msgraph_send_mail tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_send_mail)


# =============================================================================
# REPLY TO MESSAGE TOOL
# =============================================================================


def msgraph_reply_to_message(
    ctx: RunContext,
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> dict:
    """Reply to an email message with full HTML/markdown support.

    The body can contain markdown formatting which will be converted to HTML:
    - **bold** and *italic*
    - `inline code` and ```code blocks```
    - # Headers, --- rules
    - - bullet lists and 1. numbered lists
    - [links](url)

    Args:
        message_id: The message ID to reply to.
        body: Reply body text (supports markdown formatting).
        reply_all: If True, reply to all recipients.

    Returns:
        Dict with success, or error.
    """
    reply_type = "Reply All" if reply_all else "Reply"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"↩️ [bold cyan]{reply_type} to message: "
            f"{message_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Step 1: Create a draft reply
        create_action = "createReplyAll" if reply_all else "createReply"
        create_endpoint = f"/me/messages/{message_id}/{create_action}"
        
        draft_response = client.post(create_endpoint, json={})
        draft_id = draft_response.get("id")
        
        if not draft_id:
            return {
                "success": False,
                "error": "Failed to create reply draft",
                "error_type": "api_error",
            }

        # Step 2: Update the draft with HTML body
        html_body = markdown_to_html(body)
        update_endpoint = f"/me/messages/{draft_id}"
        
        update_payload = {
            "body": {
                "contentType": "HTML",
                "content": html_body,
            }
        }
        
        client.patch(update_endpoint, json=update_payload)

        # Step 3: Send the draft
        send_endpoint = f"/me/messages/{draft_id}/send"
        client.post(send_endpoint, json={})

        emit_success(f"{reply_type} sent successfully!")

        return {
            "success": True,
            "message": f"{reply_type} sent successfully",
            "message_id": message_id,
            "reply_all": reply_all,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_reply_to_message(agent: Any) -> Tool:
    """Register the msgraph_reply_to_message tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_reply_to_message)


# =============================================================================
# SEARCH MAIL TOOL
# =============================================================================


def msgraph_search_mail(
    ctx: RunContext,
    query: str,
    limit: int = 10,
) -> dict:
    """Search emails using Microsoft Search.

    Args:
        query: Search query (searches subject, body, from, etc.).
        limit: Maximum results (default 10).

    Returns:
        Dict with success, messages list, total_count.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching mail: '{query}'[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Use $search query parameter
        # Note: $search requires quotes around the query
        endpoint = "/me/messages"
        params = {
            "$search": f'"{query}"',
            "$top": limit,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,"
            "isRead,hasAttachments,importance",
        }

        response = client.get(endpoint, params=params)
        messages_data = response.get("value", [])

        messages = [_format_message_preview(m) for m in messages_data]
        total_count = len(messages)

        emit_success(f"Found {total_count} message(s) matching '{query}'")

        return {
            "success": True,
            "messages": messages,
            "total_count": total_count,
            "query": query,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_mail(agent: Any) -> Tool:
    """Register the msgraph_search_mail tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_search_mail)


# =============================================================================
# LIST MAIL FOLDERS TOOL
# =============================================================================


def msgraph_list_mail_folders(ctx: RunContext) -> dict:
    """List all mail folders.

    Returns:
        Dict with success, folders list (id, displayName, unreadItemCount,
        totalItemCount).
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📁 [bold cyan]Listing mail folders[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = "/me/mailFolders"
        params = {
            "$select": "id,displayName,unreadItemCount,totalItemCount,parentFolderId",
        }

        response = client.get(endpoint, params=params)
        folders_data = response.get("value", [])

        folders = [_format_folder(f) for f in folders_data]
        total_count = len(folders)

        emit_success(f"Found {total_count} mail folder(s)")

        return {
            "success": True,
            "folders": folders,
            "total_count": total_count,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_mail_folders(agent: Any) -> Tool:
    """Register the msgraph_list_mail_folders tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_mail_folders)
