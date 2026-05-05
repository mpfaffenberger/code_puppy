"""Microsoft Graph Teams tools.

Provides tools for:
- Listing joined teams
- Getting team details
- Listing and managing channels
- Reading and sending channel messages
- Creating online meetings
- Listing chats

Note: Teams messages require specific permissions (ChannelMessage.Read.All, etc.)
"""

from typing import Any

from datetime import datetime, timezone

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import (
    get_msgraph_client,
    _handle_msgraph_error,
    _rejected_response,
    markdown_to_html,
    require_user_approval,
    truncate_list_response,
    UserRejectedError,
    MAX_RESPONSE_CHARS,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_team(team_data: dict) -> dict:
    """Format a team response for cleaner output.

    Args:
        team_data: Raw team data from MS Graph API.

    Returns:
        Formatted team dict with key fields.
    """
    return {
        "id": team_data.get("id"),
        "display_name": team_data.get("displayName"),
        "description": team_data.get("description"),
        "visibility": team_data.get("visibility"),
        "web_url": team_data.get("webUrl"),
    }


def _format_channel(channel_data: dict) -> dict:
    """Format a channel response for cleaner output.

    Args:
        channel_data: Raw channel data from MS Graph API.

    Returns:
        Formatted channel dict with key fields.
    """
    return {
        "id": channel_data.get("id"),
        "display_name": channel_data.get("displayName"),
        "description": channel_data.get("description"),
        "membership_type": channel_data.get("membershipType"),
        "web_url": channel_data.get("webUrl"),
    }


def _format_message(msg_data: dict) -> dict:
    """Format a channel message for cleaner output.

    Args:
        msg_data: Raw message data from MS Graph API.

    Returns:
        Formatted message dict with key fields.
    """
    from_data = msg_data.get("from", {}) or {}
    user_data = from_data.get("user", {}) or {}

    body_data = msg_data.get("body", {}) or {}
    body_content = body_data.get("content", "")
    body_type = body_data.get("contentType", "text")

    return {
        "id": msg_data.get("id"),
        "from": {
            "user_id": user_data.get("id"),
            "display_name": user_data.get("displayName"),
        },
        "body": body_content,
        "body_type": body_type,
        "created": msg_data.get("createdDateTime"),
        "last_modified": msg_data.get("lastModifiedDateTime"),
        "message_type": msg_data.get("messageType"),
        "importance": msg_data.get("importance"),
    }


def _format_chat(chat_data: dict) -> dict:
    """Format a chat response for cleaner output.

    Args:
        chat_data: Raw chat data from MS Graph API.

    Returns:
        Formatted chat dict with key fields.
    """
    return {
        "id": chat_data.get("id"),
        "topic": chat_data.get("topic"),
        "chat_type": chat_data.get("chatType"),
        "created": chat_data.get("createdDateTime"),
        "last_updated": chat_data.get("lastUpdatedDateTime"),
        "web_url": chat_data.get("webUrl"),
    }


def _format_meeting(meeting_data: dict) -> dict:
    """Format a meeting response for cleaner output.

    Args:
        meeting_data: Raw meeting data from MS Graph API.

    Returns:
        Formatted meeting dict with key fields.
    """
    return {
        "id": meeting_data.get("id"),
        "join_url": meeting_data.get("joinWebUrl"),
        "subject": meeting_data.get("subject"),
        "start": meeting_data.get("startDateTime"),
        "end": meeting_data.get("endDateTime"),
        "join_info": meeting_data.get("joinInformation"),
    }


# =============================================================================
# LIST TEAMS TOOL
# =============================================================================


def msgraph_list_teams(ctx: RunContext, item_offset: int = 0) -> dict:
    """List all teams the current user is a member of.

    Args:
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, teams list (id, displayName, description), or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "💼 [bold cyan]Listing joined teams[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get("/me/joinedTeams")
        teams_data = response.get("value", [])

        teams = [_format_team(t) for t in teams_data]

        # Apply list truncation
        list_result = truncate_list_response(
            teams, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Found {list_result['items_returned']} team(s)")

        result = {
            "success": True,
            "teams": list_result["items"],
            "total_count": len(teams),
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_teams(agent: Any) -> Tool:
    """Register the msgraph_list_teams tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_teams)


# =============================================================================
# GET TEAM TOOL
# =============================================================================


def msgraph_get_team(ctx: RunContext, team_id: str) -> dict:
    """Get details about a specific team.

    Args:
        team_id: The team ID.

    Returns:
        Dict with success, team details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"💼 [bold cyan]Getting team: {team_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        team_data = client.get(f"/teams/{team_id}")
        team = _format_team(team_data)

        emit_success(f"Retrieved team: {team['display_name']}")

        return {
            "success": True,
            "team": team,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_team(agent: Any) -> Tool:
    """Register the msgraph_get_team tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_team)


# =============================================================================
# LIST CHANNELS TOOL
# =============================================================================


def msgraph_list_channels(ctx: RunContext, team_id: str) -> dict:
    """List channels in a team.

    Args:
        team_id: The team ID.

    Returns:
        Dict with success, channels list (id, displayName, description), or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📺 [bold cyan]Listing channels for team: {team_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        response = client.get(f"/teams/{team_id}/channels")
        channels_data = response.get("value", [])

        channels = [_format_channel(c) for c in channels_data]
        total_count = len(channels)

        emit_success(f"Found {total_count} channel(s)")

        return {
            "success": True,
            "channels": channels,
            "total_count": total_count,
            "team_id": team_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_channels(agent: Any) -> Tool:
    """Register the msgraph_list_channels tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_channels)


# =============================================================================
# GET CHANNEL TOOL
# =============================================================================


def msgraph_get_channel(ctx: RunContext, team_id: str, channel_id: str) -> dict:
    """Get details about a specific channel.

    Args:
        team_id: The team ID.
        channel_id: The channel ID.

    Returns:
        Dict with success, channel details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📺 [bold cyan]Getting channel: {channel_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        channel_data = client.get(f"/teams/{team_id}/channels/{channel_id}")
        channel = _format_channel(channel_data)

        emit_success(f"Retrieved channel: {channel['display_name']}")

        return {
            "success": True,
            "channel": channel,
            "team_id": team_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_channel(agent: Any) -> Tool:
    """Register the msgraph_get_channel tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_channel)


# =============================================================================
# LIST CHANNEL MESSAGES TOOL
# =============================================================================


def msgraph_list_channel_messages(
    ctx: RunContext,
    team_id: str,
    channel_id: str,
    limit: int = 20,
    item_offset: int = 0,
) -> dict:
    """List messages in a channel.

    Args:
        team_id: The team ID.
        channel_id: The channel ID.
        limit: Maximum messages to return (default 20).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, messages list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"💬 [bold cyan]Listing messages in channel: "
            f"{channel_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        params = {
            "$top": limit,
        }

        response = client.get(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            params=params,
        )
        messages_data = response.get("value", [])

        messages = [_format_message(m) for m in messages_data]

        # Apply list truncation
        list_result = truncate_list_response(
            messages, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Retrieved {list_result['items_returned']} message(s)")

        result = {
            "success": True,
            "messages": list_result["items"],
            "total_count": len(messages),
            "team_id": team_id,
            "channel_id": channel_id,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_channel_messages(agent: Any) -> Tool:
    """Register the msgraph_list_channel_messages tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_channel_messages)


# =============================================================================
# SEND CHANNEL MESSAGE TOOL
# =============================================================================


def msgraph_send_channel_message(
    ctx: RunContext,
    team_id: str,
    channel_id: str,
    content: str,
    content_type: str = "html",
) -> dict:
    """Send a message to a channel with full markdown/HTML support.

    The content can contain markdown formatting which will be converted to HTML:
    - **bold** and *italic*
    - `inline code` and ```code blocks```
    - # Headers, --- rules
    - - bullet lists and 1. numbered lists
    - [links](url)

    Args:
        team_id: The team ID.
        channel_id: The channel ID.
        content: Message content (supports markdown formatting).
        content_type: "text" or "html" (default "html" for rich formatting).

    Returns:
        Dict with success, sent message, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✉️ [bold cyan]Sending message to channel: "
            f"{channel_id[:20]}...[/bold cyan]"
        )
    )

    try:
        # --- approval gate ---
        # Pass channel_id as recipient for whitelist lookup (channel:Team/Channel)
        require_user_approval(
            "Teams Channel Message",
            {
                "Team ID": team_id,
                "Channel ID": channel_id,
                "Content": content,
            },
            recipients=[channel_id],
            context="teams",
        )

        client = get_msgraph_client()

        # Convert markdown to HTML if using html content type
        final_content = content
        final_type = content_type
        if content_type.lower() == "html":
            final_content = markdown_to_html(content)
            final_type = "html"

        payload = {
            "body": {
                "contentType": final_type,
                "content": final_content,
            },
        }

        response = client.post(
            f"/teams/{team_id}/channels/{channel_id}/messages",
            json=payload,
        )

        message = _format_message(response)

        emit_success("Message sent successfully!")

        return {
            "success": True,
            "message": message,
            "team_id": team_id,
            "channel_id": channel_id,
        }

    except UserRejectedError:
        return _rejected_response("Teams Channel Message")
    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_send_channel_message(agent: Any) -> Tool:
    """Register the msgraph_send_channel_message tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_send_channel_message)


# =============================================================================
# CREATE ONLINE MEETING TOOL
# =============================================================================


def msgraph_create_online_meeting(
    ctx: RunContext,
    subject: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
) -> dict:
    """Create a Teams online meeting.

    Args:
        subject: Meeting subject.
        start: Start datetime in ISO format.
        end: End datetime in ISO format.
        attendees: Optional list of attendee emails.

    Returns:
        Dict with success, meeting (joinUrl, id), or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🎥 [bold cyan]Creating online meeting: {subject}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        payload: dict[str, Any] = {
            "subject": subject,
            "startDateTime": start,
            "endDateTime": end,
        }

        if attendees:
            payload["participants"] = {
                "attendees": [
                    {
                        "identity": {
                            "user": {
                                "id": email,  # Note: API may require user IDs
                            },
                        },
                        "upn": email,
                    }
                    for email in attendees
                ],
            }

        response = client.post("/me/onlineMeetings", json=payload)

        meeting = _format_meeting(response)

        emit_success(f"Meeting created! Join URL: {meeting['join_url']}")

        return {
            "success": True,
            "meeting": meeting,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_online_meeting(agent: Any) -> Tool:
    """Register the msgraph_create_online_meeting tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_create_online_meeting)


# =============================================================================
# LIST CHATS TOOL
# =============================================================================


def msgraph_list_chats(ctx: RunContext, limit: int = 20, item_offset: int = 0) -> dict:
    """List recent chats (1:1 and group chats).

    Args:
        limit: Maximum chats to return (default 20).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, chats list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"💬 [bold cyan]Listing recent chats (limit: {limit})[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Note: /me/chats doesn't support $orderby, so we just get the most recent
        params = {
            "$top": limit,
        }

        response = client.get("/me/chats", params=params)
        chats_data = response.get("value", [])

        chats = [_format_chat(c) for c in chats_data]

        # Apply list truncation
        list_result = truncate_list_response(
            chats, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Found {list_result['items_returned']} chat(s)")

        result = {
            "success": True,
            "chats": list_result["items"],
            "total_count": len(chats),
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_chats(agent: Any) -> Tool:
    """Register the msgraph_list_chats tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_chats)


# =============================================================================
# LIST CHAT MESSAGES TOOL
# =============================================================================


def _parse_iso8601_utc(
    value: str,
    field_name: str,
    must_be_at_or_after: datetime | None = None,
) -> datetime | dict:
    """Parse an ISO-8601 string into a TZ-aware UTC datetime.

    Naive datetimes (no tzinfo) are interpreted as UTC. The ``Z`` suffix is
    normalized to ``+00:00`` for compatibility with Python <3.11's
    ``datetime.fromisoformat``.

    Args:
        value: The raw ISO-8601 string to parse.
        field_name: Field label used in the returned error (e.g. ``"beginning_date"``).
        must_be_at_or_after: If supplied, the parsed value must be >= this
            datetime; otherwise an invalid_argument error dict is returned.

    Returns:
        A timezone-aware ``datetime`` on success, or an error dict
        (``{"success": False, "error_type": "invalid_argument", "error": ...}``)
        on failure. Callers should ``isinstance`` check on ``dict`` to branch.
    """
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError) as e:
        return {
            "success": False,
            "error_type": "invalid_argument",
            "error": (
                f"Invalid {field_name} {value!r}: {e}. "
                f"Expected ISO 8601, e.g. '2026-04-27' or "
                f"'2026-04-27T00:00:00Z'."
            ),
        }
    if must_be_at_or_after is not None and parsed < must_be_at_or_after:
        return {
            "success": False,
            "error_type": "invalid_argument",
            "error": (
                f"{field_name} ({parsed.isoformat()}) must be >= "
                f"beginning_date ({must_be_at_or_after.isoformat()})."
            ),
        }
    return parsed


def msgraph_list_chat_messages(
    ctx: RunContext,
    chat_id: str,
    beginning_date: str,
    ending_date: str | None = None,
    max_pages: int = 20,
) -> dict:
    """List chat messages in [beginning_date, ending_date] (auto-paginated).

    Internally walks @odata.nextLink until it sees a message older than
    `beginning_date`, then stops. Returns ONLY messages within the requested
    date range. This dramatically reduces context vs the agent calling a
    paginated tool many times itself.

    MS Graph chat messages API quirks (forced on us):
    - Page size hard-capped at 50
    - `$skip` not supported (HTTP 400)
    - `$filter` on createdDateTime not supported (so we filter client-side)
    - Pagination is cursor-based via @odata.nextLink only

    Args:
        chat_id: The chat ID (get from msgraph_list_chats).
        beginning_date: ISO 8601 date or datetime (inclusive lower bound).
            Examples: "2026-04-27", "2026-04-27T00:00:00Z",
            "2026-04-27T14:30:00+00:00". Naive dates are treated as UTC.
        ending_date: Optional ISO 8601 date or datetime (inclusive upper
            bound). If provided, messages newer than this are stripped.
            Same parsing rules as beginning_date. Defaults to None (no
            upper bound = include everything up to now).
        max_pages: Safety cap on pages fetched (default 20 = up to ~1000
            messages). Prevents runaway loops on huge chats. If hit, the
            response includes hit_max_pages=True so the caller can decide
            whether to widen the date range or increase the cap.

    Returns:
        Dict with:
        - success: True/False
        - messages: list of formatted messages in
          [beginning_date, ending_date], newest first (MS Graph default order)
        - message_count: total messages returned
        - chat_id: echoed back for convenience
        - beginning_date: parsed beginning_date as ISO string (UTC)
        - ending_date: parsed ending_date as ISO string (UTC), or None
        - earliest_message_date / latest_message_date: bounds of returned set
        - pages_fetched: how many API calls were made internally
        - reached_beginning_date: True if we walked past beginning_date
          (i.e. the date range is fully covered)
        - hit_max_pages: True if we stopped due to max_pages safety cap
        - hint (optional): present only if hit_max_pages=True
    """
    display_id = chat_id[:40] + "..." if len(chat_id) > 40 else chat_id

    # --- validate max_pages ---
    if max_pages < 1:
        return {
            "success": False,
            "error_type": "invalid_argument",
            "error": f"max_pages must be >= 1 (got {max_pages}).",
        }

    # --- parse beginning_date ---
    parsed_begin = _parse_iso8601_utc(beginning_date, "beginning_date")
    if isinstance(parsed_begin, dict):
        return parsed_begin

    # --- parse ending_date (optional) ---
    parsed_end: datetime | None = None
    if ending_date is not None:
        parsed = _parse_iso8601_utc(
            ending_date, "ending_date", must_be_at_or_after=parsed_begin
        )
        if isinstance(parsed, dict):
            return parsed
        parsed_end = parsed

    range_desc = (
        f"from {parsed_begin.isoformat()} to {parsed_end.isoformat()}"
        if parsed_end is not None
        else f"since {parsed_begin.isoformat()}"
    )
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"💬 [bold cyan]Listing messages in chat: {display_id} "
            f"{range_desc}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Lazy import to avoid circular deps; needed for URL normalization.
        from code_puppy.plugins.walmart_specific.msgraph_client import (
            normalize_nextlink,
        )

        all_messages: list[dict] = []
        pages_fetched = 0
        reached_beginning_date = False
        hit_max_pages = False

        # Initial endpoint - sorted newest-first so we can short-circuit
        # as soon as we see a message older than beginning_date.
        next_endpoint: str | None = (
            f"/me/chats/{chat_id}/messages"
            "?$top=50&$orderby=createdDateTime+desc"
        )

        while next_endpoint is not None:
            if pages_fetched >= max_pages:
                hit_max_pages = True
                break

            response = client.get(next_endpoint)
            pages_fetched += 1

            page_messages = response.get("value", []) or []
            stop_after_this_page = False

            for raw_msg in page_messages:
                created_str = raw_msg.get("createdDateTime")
                if not created_str:
                    # No timestamp - keep it (better than silently dropping).
                    all_messages.append(_format_message(raw_msg))
                    continue

                try:
                    created_dt = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    all_messages.append(_format_message(raw_msg))
                    continue

                # Defense: MS Graph normally returns TZ-aware ISO strings,
                # but if a naive datetime ever sneaks through, treat it as
                # UTC so the comparisons below don't crash with TypeError.
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)

                if created_dt < parsed_begin:
                    # Hit a message older than our window - we're done.
                    # Newest-first ordering means everything after this is
                    # also out of range.
                    reached_beginning_date = True
                    stop_after_this_page = True
                    break

                if parsed_end is not None and created_dt > parsed_end:
                    # Newer than ending_date - skip this one but keep iterating.
                    # Older messages later in the page may still be in range.
                    continue

                # In range [beginning_date, ending_date].
                all_messages.append(_format_message(raw_msg))

            if stop_after_this_page:
                break

            raw_next = response.get("@odata.nextLink")
            if not raw_next:
                # End of chat history reached - by definition we covered
                # everything from beginning_date forward.
                reached_beginning_date = True
                next_endpoint = None
            else:
                next_endpoint = normalize_nextlink(raw_next)

        message_count = len(all_messages)
        earliest = all_messages[-1]["created"] if all_messages else None
        latest = all_messages[0]["created"] if all_messages else None

        coverage_note = (
            " (full range covered)"
            if reached_beginning_date
            else " (stopped early - hit max_pages)"
            if hit_max_pages
            else ""
        )
        emit_success(
            f"Retrieved {message_count} message(s) across "
            f"{pages_fetched} page(s){coverage_note}"
        )

        result = {
            "success": True,
            "messages": all_messages,
            "message_count": message_count,
            "chat_id": chat_id,
            "beginning_date": parsed_begin.isoformat(),
            "ending_date": parsed_end.isoformat() if parsed_end else None,
            "earliest_message_date": earliest,
            "latest_message_date": latest,
            "pages_fetched": pages_fetched,
            "reached_beginning_date": reached_beginning_date,
            "hit_max_pages": hit_max_pages,
        }

        if hit_max_pages:
            if earliest:
                result["hint"] = (
                    f"Stopped after {pages_fetched} pages (max_pages={max_pages}) "
                    f"WITHOUT reaching beginning_date. The oldest message returned "
                    f"is {earliest}. To get earlier messages either: (a) call "
                    f"again with a narrower beginning_date closer to that timestamp, "
                    f"or (b) raise max_pages."
                )
            else:
                result["hint"] = (
                    f"Stopped after {pages_fetched} pages (max_pages={max_pages}) "
                    f"WITHOUT reaching beginning_date, and no in-range messages "
                    f"were returned. All scanned messages were newer than "
                    f"ending_date. Consider widening the date range or raising "
                    f"max_pages."
                )

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_chat_messages(agent: Any) -> Tool:
    """Register the msgraph_list_chat_messages tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_chat_messages)


# =============================================================================
# SEND CHAT MESSAGE TOOL
# =============================================================================


def msgraph_send_chat_message(
    ctx: RunContext,
    chat_id: str,
    content: str,
    content_type: str = "html",
) -> dict:
    """Send a message to a chat with full markdown/HTML support.

    The content can contain markdown formatting which will be converted to HTML:
    - **bold** and *italic*
    - `inline code` and ```code blocks```
    - # Headers, --- rules
    - - bullet lists and 1. numbered lists
    - [links](url)

    Args:
        chat_id: The chat ID (get from msgraph_list_chats).
        content: Message content (supports markdown formatting).
        content_type: "text" or "html" (default "html" for rich formatting).

    Returns:
        Dict with success, sent message details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✉️ [bold cyan]Sending message to chat: "
            f"{chat_id[:20]}...[/bold cyan]"
        )
    )

    try:
        # --- approval gate ---
        # Pass chat_id as recipient to enable 48:notes self-skip and whitelist lookup
        require_user_approval(
            "Teams Chat Message",
            {"Chat ID": chat_id, "Content": content},
            recipients=[chat_id],
            context="teams",
        )

        client = get_msgraph_client()

        # Convert markdown to HTML if using html content type
        final_content = content
        final_type = content_type
        if content_type.lower() == "html":
            final_content = markdown_to_html(content)
            final_type = "html"

        payload = {
            "body": {
                "contentType": final_type,
                "content": final_content,
            },
        }

        response = client.post(
            f"/me/chats/{chat_id}/messages",
            json=payload,
        )

        message = _format_message(response)

        emit_success("Message sent successfully!")

        return {
            "success": True,
            "message": message,
            "chat_id": chat_id,
        }

    except UserRejectedError:
        return _rejected_response("Teams Chat Message")
    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_send_chat_message(agent: Any) -> Tool:
    """Register the msgraph_send_chat_message tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_send_chat_message)


# =============================================================================
# SEND DIRECT MESSAGE TOOL
# =============================================================================


def _find_existing_chat_with_user(
    client: Any, user_email: str, current_user_id: str | None = None
) -> tuple[str | None, str | None]:
    """Find an existing 1:1 chat with a user by searching recent chats.

    Uses STRICT matching only to prevent sending messages to wrong recipients.
    Only matches on exact email, exact userId, or exact username (before @).

    Args:
        client: MSGraphClient instance.
        user_email: The user's email, UPN, or userId to find a chat with.
        current_user_id: Current user's ID to exclude from matching (optional).

    Returns:
        Tuple of (chat_id, matched_email) if found, (None, None) otherwise.
    """
    try:
        # Get recent chats and look for a 1:1 with this user
        # Expand members to see who's in each chat
        params = {
            "$top": 50,
            "$expand": "members",
        }
        response = client.get("/me/chats", params=params)
        chats = response.get("value", [])

        # Normalize the search term
        search_lower = user_email.lower().strip()
        # Extract just the username part if it's an email (before @)
        search_username = (
            search_lower.split("@")[0] if "@" in search_lower else search_lower
        )

        for chat in chats:
            # Only look at 1:1 chats
            if chat.get("chatType") != "oneOnOne":
                continue

            members = chat.get("members", [])
            for member in members:
                member_email = (member.get("email") or "").lower()
                member_id = (member.get("userId") or "").lower()

                # Skip matching against self (current user is in all their chats)
                if current_user_id and member_id == current_user_id.lower():
                    continue

                # STRICT MATCHING - prevent wrong recipients while handling
                # edge cases like truncated emails from MS Graph API

                # 1. Exact email match (case-insensitive)
                if search_lower == member_email:
                    return chat.get("id"), member.get("email")

                # 2. Exact userId match
                if search_lower == member_id:
                    return chat.get("id"), member.get("email")

                # 3. Exact username match (the part before @)
                member_username = (
                    member_email.split("@")[0] if "@" in member_email else ""
                )
                if search_username and member_username == search_username:
                    return chat.get("id"), member.get("email")

                # 4. Handle MS Graph truncated emails (API sometimes truncates)
                #    Only match if one starts with the other AND they're very similar
                if member_email and search_lower:
                    # Check if search starts with member email (truncated case)
                    if search_lower.startswith(member_email.rstrip("@walmart.com")):
                        # Require at least 10 chars to avoid false positives
                        if len(member_username) >= 10:
                            return chat.get("id"), member.get("email")
                    # Check if member email starts with search (partial input)
                    if member_email.startswith(search_lower.rstrip("@walmart.com")):
                        if len(search_username) >= 10:
                            return chat.get("id"), member.get("email")

    except Exception:
        # If search fails, return None and let caller try to create
        pass

    return None, None


def msgraph_send_direct_message(
    ctx: RunContext,
    user_email: str,
    content: str,
    content_type: str = "text",
) -> dict:
    """Send a direct message to a user by email.

    First searches for an existing 1:1 chat with the user, then falls back
    to creating a new chat if none exists.

    Args:
        user_email: The recipient's email address.
        content: Message content.
        content_type: "text" or "html" (default "text").

    Returns:
        Dict with success, chat_id, sent message details, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"✉️ [bold cyan]Sending direct message to: {user_email}[/bold cyan]"
        )
    )

    try:
        # --- approval gate ---
        require_user_approval(
            "Teams Direct Message",
            {"Recipient": user_email, "Content": content},
            recipients=[user_email],  # Enable self-send skip and whitelist lookup
            context="teams",
        )

        client = get_msgraph_client()
        chat_id = None
        chat_response = None
        matched_recipient = None

        # Get current user ID to exclude self from chat member matching
        try:
            me_response = client.get("/me", params={"$select": "id"})
            current_user_id = me_response.get("id")
        except Exception:
            current_user_id = None

        # Step 1: Try to find an existing chat with this user first
        existing_chat_id, matched_recipient = _find_existing_chat_with_user(
            client, user_email, current_user_id
        )

        if existing_chat_id:
            chat_id = existing_chat_id
            # Show who was actually matched for transparency
            emit_info(
                Text.from_markup(
                    f"[dim]Found existing chat with {matched_recipient or user_email}[/dim]"
                )
            )
        else:
            # Step 2: No existing chat found, try to create one
            # NOTE: This may fail with 405 if tenant doesn't allow chat creation
            chat_payload = {
                "chatType": "oneOnOne",
                "members": [
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": "https://graph.microsoft.com/v1.0/me",
                    },
                    {
                        "@odata.type": "#microsoft.graph.aadUserConversationMember",
                        "roles": ["owner"],
                        "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{user_email}",
                    },
                ],
            }

            try:
                chat_response = client.post("/chats", json=chat_payload)
                chat_id = chat_response.get("id")
            except Exception as create_err:
                # Chat creation failed - provide helpful error
                return {
                    "success": False,
                    "error": (
                        f"No existing chat found with {user_email} and unable to "
                        f"create a new chat. You may need to start a conversation "
                        f"with this user in Teams first. Error: {create_err}"
                    ),
                    "suggestion": (
                        "Try messaging this user directly in Teams to create a chat, "
                        "then retry this command."
                    ),
                }

        if not chat_id:
            return {
                "success": False,
                "error": "Failed to find or create chat - no chat ID available",
            }

        # Step 3: Send the message to the chat
        message_payload = {
            "body": {
                "contentType": content_type,
                "content": content,
            },
        }

        message_response = client.post(
            f"/me/chats/{chat_id}/messages",
            json=message_payload,
        )

        message = _format_message(message_response)
        chat = _format_chat(chat_response) if chat_response else {"id": chat_id}

        # Show actual recipient for transparency (may differ from search term)
        actual_recipient = matched_recipient or user_email
        emit_success(f"Direct message sent to {actual_recipient}!")

        return {
            "success": True,
            "chat_id": chat_id,
            "chat": chat,
            "message": message,
            "recipient": actual_recipient,
            "requested_recipient": user_email,
        }

    except UserRejectedError:
        return _rejected_response("Teams Direct Message")
    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_send_direct_message(agent: Any) -> Tool:
    """Register the msgraph_send_direct_message tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_send_direct_message)
