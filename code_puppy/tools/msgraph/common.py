"""Common utilities for Microsoft Graph tools.

Provides shared helpers for all msgraph tools including:
- Client instantiation
- Error handling and response formatting
- Markdown to HTML conversion for rich email/message formatting
- Response truncation for token safety
- Shared Pydantic models (if needed)

"""

import json
import re
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.msgraph_client import (
    MSGraphClient,
    MSGraphError,
    MSGraphAuthError,
    MSGraphNotFoundError,
    MSGraphAPIError,
    MSGraphThrottledError,
)

# Maximum character limit for tool responses to stay within token budget
MAX_RESPONSE_CHARS = 10_000


# =============================================================================
# RESPONSE TRUNCATION UTILITIES
# =============================================================================


def _serialize_for_length(data: Any) -> str:
    """Serialize data to JSON string for length measurement.

    Args:
        data: Any serializable data.

    Returns:
        JSON string representation.
    """
    try:
        return json.dumps(data, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(data)


def truncate_content(
    content: str,
    char_offset: int = 0,
    max_chars: int = MAX_RESPONSE_CHARS,
) -> dict:
    """Truncate content with character offset pagination support.

    Use this for tools that return large text content (email bodies,
    file contents, etc.).

    Args:
        content: The full text content to potentially truncate.
        char_offset: Starting character position (for pagination).
        max_chars: Maximum characters to return (default 10,000).

    Returns:
        Dict with:
        - content: The (possibly truncated) content
        - truncated: True if content was truncated
        - char_offset: The offset used
        - next_offset: Next offset to use for pagination (None if not truncated)
        - total_chars: Total length of original content
    """
    total_chars = len(content)

    # Apply offset
    if char_offset > 0:
        if char_offset >= total_chars:
            return {
                "content": "",
                "truncated": False,
                "char_offset": char_offset,
                "next_offset": None,
                "total_chars": total_chars,
                "message": f"Offset {char_offset} exceeds content length {total_chars}",
            }
        content = content[char_offset:]

    # Check if truncation needed
    if len(content) <= max_chars:
        return {
            "content": content,
            "truncated": False,
            "char_offset": char_offset,
            "next_offset": None,
            "total_chars": total_chars,
        }

    # Truncate and provide next offset
    truncated_content = content[:max_chars]
    next_offset = char_offset + max_chars

    return {
        "content": truncated_content,
        "truncated": True,
        "char_offset": char_offset,
        "next_offset": next_offset,
        "total_chars": total_chars,
        "message": f"Content truncated at {max_chars} chars. Use char_offset={next_offset} to continue.",
    }


def truncate_list_response(
    items: list,
    char_offset: int = 0,
    max_chars: int = MAX_RESPONSE_CHARS,
) -> dict:
    """Truncate a list response with character offset pagination.

    Serializes items to JSON to measure character length, then returns
    as many complete items as fit within the limit.

    Args:
        items: List of items (dicts, strings, etc.).
        char_offset: Number of items to skip (for list pagination, this is item offset).
        max_chars: Maximum characters for the serialized response.

    Returns:
        Dict with:
        - items: The items that fit within the limit
        - truncated: True if not all items were returned
        - item_offset: The offset used (number of items skipped)
        - next_offset: Next offset to use for pagination (None if not truncated)
        - items_returned: Number of items in this response
        - total_items: Total items available (if known)
    """
    # Apply item offset
    if char_offset > 0:
        if char_offset >= len(items):
            return {
                "items": [],
                "truncated": False,
                "item_offset": char_offset,
                "next_offset": None,
                "items_returned": 0,
                "total_items": len(items),
            }
        items = items[char_offset:]

    # Add items one by one until we exceed the limit
    result_items = []
    current_chars = 2  # Account for [] in JSON

    for i, item in enumerate(items):
        item_json = _serialize_for_length(item)
        item_chars = len(item_json) + (2 if i > 0 else 0)  # comma + space

        if current_chars + item_chars > max_chars:
            # Can't fit this item
            break

        result_items.append(item)
        current_chars += item_chars

    items_returned = len(result_items)
    original_count = len(items) + char_offset
    truncated = items_returned < len(items)
    next_offset = char_offset + items_returned if truncated else None

    result = {
        "items": result_items,
        "truncated": truncated,
        "item_offset": char_offset,
        "next_offset": next_offset,
        "items_returned": items_returned,
        "total_items": original_count,
    }

    if truncated:
        result["message"] = (
            f"Response truncated. Returned {items_returned} of {len(items)} items. Use item_offset={next_offset} to continue."
        )

    return result


def apply_response_limit(
    response: dict,
    char_offset: int = 0,
    max_chars: int = MAX_RESPONSE_CHARS,
) -> dict:
    """Apply character limit to a complete response dict.

    This is a safety wrapper that checks the total serialized size of a
    response and truncates if necessary. It preserves the structure but
    may truncate individual string fields.

    Args:
        response: The response dict to potentially truncate.
        char_offset: Character offset into the serialized response.
        max_chars: Maximum characters for the response.

    Returns:
        The response, potentially with truncation metadata added.
    """
    serialized = _serialize_for_length(response)
    total_chars = len(serialized)

    if total_chars <= max_chars:
        return response

    # Response too large - add warning metadata
    response["_response_size"] = total_chars
    response["_truncation_warning"] = (
        f"Response is {total_chars} chars, exceeding {max_chars} limit. "
        "Some data may be incomplete. Use more specific queries or pagination."
    )

    # Try to identify and truncate the largest string fields
    # Common large fields in msgraph responses
    large_fields = ["body", "content", "description", "bodyPreview", "summary"]

    for field in large_fields:
        if field in response and isinstance(response[field], str):
            field_len = len(response[field])
            if field_len > max_chars // 2:
                # Truncate this field
                truncated_value = response[field][: max_chars // 2]
                response[field] = truncated_value
                response[f"_{field}_truncated"] = True
                response[f"_{field}_original_length"] = field_len

    return response


# =============================================================================
# USER APPROVAL GATE
# =============================================================================


class UserRejectedError(Exception):
    """Raised when the user declines to approve a send action."""


# Cache for current user identity (avoids repeated /me calls)
_current_user_cache: dict | None = None


def get_current_user_identity() -> dict | None:
    """Get current user's email, UPN, and ID (cached for session).

    Returns:
        Dict with lowercase 'id', 'mail', and 'upn' keys, or None if unavailable.
    """
    global _current_user_cache
    if _current_user_cache is not None:
        return _current_user_cache

    try:
        client = get_msgraph_client()
        me = client.get("/me", params={"$select": "id,mail,userPrincipalName"})
        _current_user_cache = {
            "id": (me.get("id") or "").lower(),
            "mail": (me.get("mail") or "").lower(),
            "upn": (me.get("userPrincipalName") or "").lower(),
        }
        return _current_user_cache
    except Exception:  # noqa: BLE001
        # If we can't get current user, don't block - just skip the optimization
        return None


# Special Teams chat IDs that indicate self-messaging
SELF_CHAT_IDS = {
    "48:notes",  # Teams "Chat with yourself" feature
}


def _resolve_teams_whitelist_entry(
    entry: str, client: "MSGraphClient | None" = None
) -> set[str]:
    """Resolve a Teams whitelist entry to matchable identifiers.

    Whitelist entry formats:
    - Plain email/UPN: "user@walmart.com" → for Teams DMs to individuals
    - Chat ID: "19:abc123@thread.v2" → direct chat/group chat ID
    - Named group chat: "chat:Daily Standup" → exact topic match (via API lookup)
    - Channel: "channel:Platform Team/General" → exact team/channel match (via API)

    Examples:
        # Individual DM - just use their email
        msgraph_teams_whitelist = user@walmart.com, boss@walmart.com

        # Named group chat - use chat: prefix with exact topic
        msgraph_teams_whitelist = chat:Daily Standup

        # Channel - use channel: prefix with Team Name/Channel Name
        msgraph_teams_whitelist = channel:Platform Team/General

    Args:
        entry: Whitelist entry (may have chat: or channel: prefix).
        client: Optional MSGraphClient for lookups.

    Returns:
        Set of identifiers that match this entry (exact match only).
    """
    entry_stripped = entry.strip()
    entry_lower = entry_stripped.lower()

    # Plain email or ID - return as-is (for DMs to individuals)
    if not entry_lower.startswith(("chat:", "channel:")):
        return {entry_lower}

    # Need client for lookups
    if client is None:
        try:
            client = get_msgraph_client()
        except Exception:  # noqa: BLE001
            return set()  # Can't resolve without client

    # Chat topic lookup: "chat:Topic Name" - EXACT match only
    if entry_lower.startswith("chat:"):
        topic_name = entry_stripped[5:].strip().lower()
        if not topic_name:
            return set()  # Empty topic name
        try:
            response = client.get("/me/chats", params={"$top": 50})
            chats = response.get("value", [])
            for chat in chats:
                chat_topic = (chat.get("topic") or "").strip().lower()
                # Exact match required for security
                if chat_topic and chat_topic == topic_name:
                    return {chat.get("id", "").lower()}
            return set()  # No exact match found
        except Exception:  # noqa: BLE001
            return set()

    # Channel lookup: "channel:Team Name/Channel Name" - EXACT match only
    if entry_lower.startswith("channel:"):
        channel_spec = entry_stripped[8:].strip()  # e.g., "Platform Team/General"
        if "/" not in channel_spec:
            return set()  # Invalid format

        team_name, channel_name = channel_spec.split("/", 1)
        team_name = team_name.strip().lower()
        channel_name = channel_name.strip().lower()

        if not team_name or not channel_name:
            return set()  # Empty team or channel name

        try:
            # Find team - exact match
            teams_response = client.get("/me/joinedTeams")
            teams = teams_response.get("value", [])

            for team in teams:
                team_display = (team.get("displayName") or "").strip().lower()
                if team_display == team_name:  # Exact match
                    team_id = team.get("id")
                    # Find channel in this team - exact match
                    channels_response = client.get(f"/teams/{team_id}/channels")
                    channels = channels_response.get("value", [])

                    for channel in channels:
                        channel_display = (channel.get("displayName") or "").strip().lower()
                        if channel_display == channel_name:  # Exact match
                            return {channel.get("id", "").lower()}
            return set()  # No exact match found
        except Exception:  # noqa: BLE001
            return set()

    return set()


def should_skip_approval(
    recipients: list[str],
    context: str = "mail",
) -> tuple[bool, str | None]:
    """Check if approval should be skipped for these recipients.

    Checks in order:
    1. Special self-chat IDs (e.g., "48:notes" for Teams self-chat)
    2. All recipients are the current user (self-messages)
    3. All recipients are in the configured whitelist (context-specific)

    Args:
        recipients: List of email addresses, user IDs, or chat IDs.
        context: "mail" or "teams" - determines which whitelist to use.

    Returns:
        Tuple of (should_skip, reason_message).
        If should_skip is True, reason_message explains why.
    """
    if not recipients:
        return False, None

    normalized = {r.lower().strip() for r in recipients if r}
    if not normalized:
        return False, None

    # Check: Special self-chat IDs (e.g., 48:notes for Teams)
    if normalized.issubset(SELF_CHAT_IDS):
        return True, "Sending to self (48:notes) \u2014 skipping confirmation"

    # Build set of all "safe" recipients (self + whitelist)
    safe_recipients: set[str] = set()

    # Add self identities
    current_user = get_current_user_identity()
    if current_user:
        self_identities = {
            current_user["id"],
            current_user["mail"],
            current_user["upn"],
        }
        self_identities.discard("")  # Remove empty strings
        safe_recipients.update(self_identities)

    # Check: All recipients are self (before loading whitelist for efficiency)
    if safe_recipients and normalized.issubset(safe_recipients):
        return True, "Sending to self \u2014 skipping confirmation"

    # Load context-specific whitelist
    try:
        if context == "mail":
            from code_puppy.config import get_msgraph_mail_whitelist
            whitelist = get_msgraph_mail_whitelist()
            # Mail whitelist is simple - just email addresses
            if whitelist:
                safe_recipients.update(whitelist)
        elif context == "teams":
            from code_puppy.config import get_msgraph_teams_whitelist
            whitelist = get_msgraph_teams_whitelist()
            # Teams whitelist may need resolution (chat:, channel: prefixes)
            if whitelist:
                for entry in whitelist:
                    if entry.startswith(("chat:", "channel:")):
                        # Resolve named entries to IDs
                        resolved = _resolve_teams_whitelist_entry(entry)
                        safe_recipients.update(resolved)
                    else:
                        # Plain email or ID
                        safe_recipients.add(entry)
    except Exception:  # noqa: BLE001
        # If config loading fails, continue without whitelist
        pass

    # Check: All recipients are in safe set (self + whitelist)
    if safe_recipients and normalized.issubset(safe_recipients):
        # Determine reason based on what matched
        if current_user:
            self_set = {current_user["id"], current_user["mail"], current_user["upn"]}
            self_set.discard("")
            if normalized.issubset(self_set):
                return True, "Sending to self \u2014 skipping confirmation"
        return True, "All recipients whitelisted \u2014 skipping confirmation"

    return False, None


def require_user_approval(
    action: str,
    details: dict[str, str],
    recipients: list[str] | None = None,
    context: str = "mail",
) -> None:
    """Ask the user for approval before sending a message or email.

    Displays a polished full-screen TUI with the action details, letting the
    user approve or reject with keyboard navigation (↑↓, y/n, Enter, Esc).

    Falls back to a simple y/N prompt if the TUI can't be shown (e.g., async
    context, non-interactive terminal, sub-agent, or wiggum mode).

    Auto-skips confirmation when sending to self (same user identity).

    Args:
        action: Short description, e.g. "Send Email" or "Teams Channel Message".
        details: Key/value pairs to display (e.g. {"To": "...", "Subject": "..."}).
        recipients: Optional list of recipient emails/IDs for skip-check.
        context: "mail" or "teams" - determines which whitelist to use.

    Raises:
        UserRejectedError: If the user does not approve.
    """
    # Check if we should skip approval (e.g., sending to self)
    if recipients:
        should_skip, reason = should_skip_approval(recipients, context=context)
        if should_skip:
            emit_info(f"✓ {reason}")
            return

    from .approval_tui import request_approval

    approved = request_approval(action, details)
    if not approved:
        raise UserRejectedError(f"User declined: {action}")


def _rejected_response(action: str) -> dict:
    """Return a standardised tool response when the user declines."""
    return {
        "success": False,
        "error": f"{action} was cancelled by the user.",
        "error_type": "user_rejected",
    }


# =============================================================================
# CLIENT HELPER
# =============================================================================


def get_msgraph_client() -> MSGraphClient:
    """Get a Microsoft Graph client instance.

    Returns:
        MSGraphClient: A configured Microsoft Graph client.

    Raises:
        MSGraphAuthError: If no valid tokens are available.
    """
    return MSGraphClient()


# =============================================================================
# ERROR HANDLING
# =============================================================================


def _handle_msgraph_error(e: Exception) -> dict:
    """Convert Microsoft Graph exceptions to structured error responses.

    Args:
        e: Exception raised by MSGraphClient.

    Returns:
        Dict with success=False and error details.
    """
    if isinstance(e, MSGraphAuthError):
        error_msg = f"Authentication failed: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, MSGraphNotFoundError):
        error_msg = f"Resource not found: {e!s}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, MSGraphThrottledError):
        retry_after = getattr(e, "retry_after", None)
        error_msg = f"Rate limited: {e!s}"
        if retry_after:
            error_msg += f" (retry after {retry_after}s)"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "throttled",
            "retry_after": retry_after,
        }
    elif isinstance(e, MSGraphAPIError):
        error_msg = f"API error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
            "status_code": getattr(e, "status_code", None),
            "error_code": getattr(e, "error_code", None),
        }
    elif isinstance(e, MSGraphError):
        error_msg = f"Microsoft Graph error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "msgraph",
        }
    else:
        error_msg = f"Unexpected error: {e!s}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
        }


# =============================================================================
# MARKDOWN TO HTML CONVERSION
# =============================================================================


def markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML for Outlook/Teams rendering.

    Supports common markdown patterns:
    - **bold** and __bold__
    - *italic* and _italic_
    - `inline code`
    - ```code blocks```
    - # Headers (h1-h6)
    - --- horizontal rules
    - - bullet lists
    - 1. numbered lists
    - [links](url)
    - Paragraphs (double newlines)

    Args:
        text: Markdown-formatted text.

    Returns:
        HTML-formatted string suitable for Outlook/Teams.
    """
    if not text:
        return text

    html = text

    # Escape HTML special characters first (except in code blocks)
    # We'll handle code blocks separately to preserve their content

    # Extract and placeholder code blocks first
    code_blocks: list[str] = []

    def save_code_block(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    html = re.sub(r"```(?:\w+)?\n?(.*?)```", save_code_block, html, flags=re.DOTALL)

    # Extract inline code
    inline_codes: list[str] = []

    def save_inline_code(match: re.Match) -> str:
        inline_codes.append(match.group(1))
        return f"\x00INLINECODE{len(inline_codes) - 1}\x00"

    html = re.sub(r"`([^`]+)`", save_inline_code, html)

    # Now escape HTML in the remaining text
    html = html.replace("&", "&amp;")
    html = html.replace("<", "&lt;")
    html = html.replace(">", "&gt;")

    # Headers (must be at start of line)
    html = re.sub(r"^###### (.+)$", r"<h6>\1</h6>", html, flags=re.MULTILINE)
    html = re.sub(r"^##### (.+)$", r"<h5>\1</h5>", html, flags=re.MULTILINE)
    html = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Horizontal rules
    html = re.sub(r"^---+$", r"<hr>", html, flags=re.MULTILINE)

    # Bold (** or __)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"__(.+?)__", r"<strong>\1</strong>", html)

    # Italic (* or _) - be careful not to match inside words
    html = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", html)
    html = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", html)

    # Links [text](url)
    html = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', html)

    # Bullet lists (simple - just the items, not nested)
    # Convert lines starting with - or * to list items
    def convert_bullet_list(text: str) -> str:
        lines = text.split("\n")
        result = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^[-*] ", stripped):
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                item_content = re.sub(r"^[-*] ", "", stripped)
                result.append(f"<li>{item_content}</li>")
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ul>")
        return "\n".join(result)

    html = convert_bullet_list(html)

    # Numbered lists
    def convert_numbered_list(text: str) -> str:
        lines = text.split("\n")
        result = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if re.match(r"^\d+\. ", stripped):
                if not in_list:
                    result.append("<ol>")
                    in_list = True
                item_content = re.sub(r"^\d+\. ", "", stripped)
                result.append(f"<li>{item_content}</li>")
            else:
                if in_list:
                    result.append("</ol>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ol>")
        return "\n".join(result)

    html = convert_numbered_list(html)

    # Restore code blocks with styling
    for i, code in enumerate(code_blocks):
        escaped_code = (
            code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        styled_block = (
            f'<pre style="background-color: #f4f4f4; padding: 10px; '
            f'border-radius: 4px; font-family: monospace; overflow-x: auto;">'
            f"{escaped_code}</pre>"
        )
        html = html.replace(f"\x00CODEBLOCK{i}\x00", styled_block)

    # Restore inline code with styling
    for i, code in enumerate(inline_codes):
        escaped_code = (
            code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        styled_inline = (
            f'<code style="background-color: #f4f4f4; padding: 2px 6px; '
            f'border-radius: 3px; font-family: monospace;">{escaped_code}</code>'
        )
        html = html.replace(f"\x00INLINECODE{i}\x00", styled_inline)

    # Convert double newlines to paragraph breaks
    # But not inside pre/code blocks (already handled)
    html = re.sub(r"\n\n+", "</p><p>", html)

    # Convert single newlines to <br> (for line breaks within paragraphs)
    html = re.sub(r"(?<!>)\n(?!<)", "<br>\n", html)

    # Wrap in paragraph tags if not already wrapped in block elements
    if not html.startswith(("<h", "<p", "<ul", "<ol", "<pre", "<hr")):
        html = f"<p>{html}</p>"

    return html


# =============================================================================
# GENERIC API REQUEST TOOL
# =============================================================================


def msgraph_api_request(
    ctx: RunContext,
    method: str,
    endpoint: str,
    params: dict | None = None,
    body: dict | None = None,
    char_offset: int = 0,
) -> dict:
    """Make a generic Microsoft Graph API request.

    This is a fallback tool for calling any MS Graph endpoint that doesn't
    have a dedicated tool. Use this for less common operations.

    Args:
        method: HTTP method - "GET", "POST", "PATCH", "DELETE", "PUT".
        endpoint: API endpoint path (e.g., "/me/profile", "/users/{id}/manager").
        params: Optional query parameters as a dict (e.g., {"$top": 10}).
        body: Optional request body as a dict (for POST/PATCH/PUT requests).
        char_offset: Character offset for paginating large responses (default 0).
            If response exceeds 10,000 chars, use the returned next_offset value.

    Returns:
        Dict with success=True and response data, or success=False and error.
        If truncated, includes: truncated=True, char_offset, next_offset, total_chars.

    Examples:
        # GET request with query params
        msgraph_api_request(
            method="GET",
            endpoint="/me/memberOf",
            params={"$top": 5}
        )

        # POST request with body
        msgraph_api_request(
            method="POST",
            endpoint="/me/sendMail",
            body={"message": {"subject": "Hello"}}
        )

        # Continue reading truncated response
        msgraph_api_request(
            method="GET",
            endpoint="/me/messages/{id}",
            char_offset=10000  # continue from previous next_offset
        )
    """
    # Validate method
    method = method.upper()
    valid_methods = {"GET", "POST", "PATCH", "DELETE", "PUT"}
    if method not in valid_methods:
        error_msg = (
            f"Invalid HTTP method: {method}. "
            f"Must be one of: {', '.join(sorted(valid_methods))}"
        )
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "invalid_method",
        }

    # Validate endpoint
    if not endpoint:
        error_msg = "Endpoint cannot be empty"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "invalid_endpoint",
        }

    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔗 [bold cyan]{method} {endpoint}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Call the appropriate client method based on HTTP method
        if method == "GET":
            response = client.get(endpoint, params=params)
        elif method == "POST":
            response = client.post(endpoint, json=body, params=params)
        elif method == "PATCH":
            response = client.patch(endpoint, json=body, params=params)
        elif method == "DELETE":
            response = client.delete(endpoint, params=params)
        elif method == "PUT":
            response = client.put(endpoint, json=body, params=params)
        else:
            # This should never happen due to validation above
            raise ValueError(f"Unsupported method: {method}")

        emit_success(f"API request completed: {method} {endpoint}")

        # Serialize and check response size
        response_json = _serialize_for_length(response)
        total_chars = len(response_json)

        result = {
            "success": True,
            "method": method,
            "endpoint": endpoint,
        }

        # Apply truncation if response is large
        if total_chars > MAX_RESPONSE_CHARS:
            truncation = truncate_content(
                response_json, char_offset=char_offset, max_chars=MAX_RESPONSE_CHARS
            )
            result["response_raw"] = truncation["content"]
            result["truncated"] = truncation["truncated"]
            result["char_offset"] = truncation["char_offset"]
            result["next_offset"] = truncation["next_offset"]
            result["total_chars"] = truncation["total_chars"]
            if truncation.get("message"):
                result["truncation_message"] = truncation["message"]
        else:
            result["response"] = response
            result["truncated"] = False
            result["total_chars"] = total_chars

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_api_request(agent: Any) -> Tool:
    """Register the msgraph_api_request tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_api_request)


# =============================================================================
# AUTHENTICATION TOOL
# =============================================================================


def msgraph_authenticate(ctx: RunContext) -> dict:
    """Launch Microsoft Graph authentication flow.

    Opens a browser window for the user to sign in with their Microsoft account.
    Use this tool when you receive a 401 authentication error, or when the user
    needs to authenticate/re-authenticate with Microsoft Graph.

    Returns:
        Dict with success=True if authentication completed, or error details.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🔐 [bold cyan]Launching authentication flow...[/bold cyan]"
        )
    )

    try:
        # Import the auth module and run the auth flow
        from code_puppy.plugins.walmart_specific.msgraph_auth import (
            handle_msgraph_auth_command,
        )

        result = handle_msgraph_auth_command("/msgraph_auth", "msgraph_auth")

        if result and "successful" in result.lower():
            emit_success("Authentication completed successfully!")
            return {
                "success": True,
                "message": "Microsoft Graph authentication successful. You can now retry your previous request.",
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


def register_msgraph_authenticate(agent: Any) -> Tool:
    """Register the msgraph_authenticate tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_authenticate)
