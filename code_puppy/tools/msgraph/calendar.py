"""Microsoft Graph Calendar tools.

Provides tools for:
- Listing calendar events
- Getting specific events
- Creating events (with optional Teams meeting)
- Updating events
- Deleting events
- Checking free/busy availability
- Listing calendars
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
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


def _ensure_utc_format(dt_str: str) -> str:
    """Ensure datetime string is in UTC ISO format for MS Graph.

    Args:
        dt_str: ISO datetime string (may or may not include timezone).

    Returns:
        ISO datetime string with Z suffix (UTC).
    """
    if not dt_str:
        return dt_str

    # If already has timezone info, return as-is
    if dt_str.endswith("Z") or "+" in dt_str or "-" in dt_str[-6:]:
        return dt_str

    # Assume UTC and add Z suffix
    return f"{dt_str}Z" if not dt_str.endswith("Z") else dt_str


def _format_datetime_for_graph(dt_str: str) -> dict:
    """Format a datetime string for MS Graph API.

    Args:
        dt_str: ISO datetime string.

    Returns:
        Dict with dateTime and timeZone for MS Graph.
    """
    # MS Graph expects datetime without Z and a separate timeZone
    clean_dt = dt_str.replace("Z", "")
    if "+" in clean_dt:
        clean_dt = clean_dt.split("+")[0]

    return {
        "dateTime": clean_dt,
        "timeZone": "UTC",
    }


def _format_event(event: dict) -> dict:
    """Format an event for display.

    Args:
        event: Raw event data from MS Graph API.

    Returns:
        Formatted event dict with key fields.
    """
    start = event.get("start", {})
    end = event.get("end", {})
    location = event.get("location", {})
    organizer = event.get("organizer", {})
    organizer_email = organizer.get("emailAddress", {})

    # Get attendees
    attendees_raw = event.get("attendees", [])
    attendees = []
    for att in attendees_raw:
        email_addr = att.get("emailAddress", {})
        attendees.append(
            {
                "name": email_addr.get("name"),
                "email": email_addr.get("address"),
                "type": att.get("type"),
                "response": att.get("status", {}).get("response"),
            }
        )

    # Get body content
    body_data = event.get("body", {})
    body_content = body_data.get("content", "")

    # Check for online meeting
    online_meeting = event.get("onlineMeeting")
    teams_link = None
    if online_meeting:
        teams_link = online_meeting.get("joinUrl")

    return {
        "id": event.get("id"),
        "subject": event.get("subject", "(No Subject)"),
        "start": start.get("dateTime"),
        "start_timezone": start.get("timeZone"),
        "end": end.get("dateTime"),
        "end_timezone": end.get("timeZone"),
        "location": location.get("displayName"),
        "organizer": {
            "name": organizer_email.get("name"),
            "email": organizer_email.get("address"),
        },
        "attendees": attendees,
        "body": body_content,
        "is_all_day": event.get("isAllDay", False),
        "is_cancelled": event.get("isCancelled", False),
        "is_online_meeting": event.get("isOnlineMeeting", False),
        "teams_link": teams_link,
        "web_link": event.get("webLink"),
        "response_status": event.get("responseStatus", {}).get("response"),
    }


def _format_event_preview(event: dict) -> dict:
    """Format an event for list/preview display.

    Args:
        event: Raw event data from MS Graph API.

    Returns:
        Formatted event dict with preview fields.
    """
    start = event.get("start", {})
    end = event.get("end", {})
    location = event.get("location", {})

    return {
        "id": event.get("id"),
        "subject": event.get("subject", "(No Subject)"),
        "start": start.get("dateTime"),
        "start_timezone": start.get("timeZone"),
        "end": end.get("dateTime"),
        "end_timezone": end.get("timeZone"),
        "location": location.get("displayName"),
        "is_all_day": event.get("isAllDay", False),
        "is_online_meeting": event.get("isOnlineMeeting", False),
        "response_status": event.get("responseStatus", {}).get("response"),
    }


def _format_calendar(calendar: dict) -> dict:
    """Format a calendar for display.

    Args:
        calendar: Raw calendar data from MS Graph API.

    Returns:
        Formatted calendar dict.
    """
    return {
        "id": calendar.get("id"),
        "name": calendar.get("name"),
        "color": calendar.get("color"),
        "is_default": calendar.get("isDefaultCalendar", False),
        "can_edit": calendar.get("canEdit", False),
        "can_share": calendar.get("canShare", False),
        "owner": calendar.get("owner", {}).get("address"),
    }


# =============================================================================
# LIST EVENTS TOOL
# =============================================================================


def msgraph_list_events(
    ctx: RunContext,
    start: str | None = None,
    end: str | None = None,
    limit: int = 10,
    item_offset: int = 0,
) -> dict:
    """List calendar events.

    Args:
        start: Start datetime in ISO format (default: now).
        end: End datetime in ISO format (default: 7 days from now).
        limit: Maximum events to return (default 10).
        item_offset: Item offset for response truncation (default 0).
            If response exceeds 10,000 chars, use next_offset to continue.

    Returns:
        Dict with success, events list, or error.
        If truncated: truncated=True, next_offset, items_returned.
    """
    # Set defaults for start and end
    now = datetime.now(timezone.utc)
    if start is None:
        start = now.isoformat().replace("+00:00", "Z")
    else:
        start = _ensure_utc_format(start)

    if end is None:
        end_dt = now + timedelta(days=7)
        end = end_dt.isoformat().replace("+00:00", "Z")
    else:
        end = _ensure_utc_format(end)

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Listing events from {start[:10]} to {end[:10]}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Use calendarView for time-range queries (handles recurring events)
        endpoint = "/me/calendarView"
        params = {
            "startDateTime": start,
            "endDateTime": end,
            "$top": limit,
            "$orderby": "start/dateTime",
            "$select": "id,subject,start,end,location,isAllDay,"
            "isOnlineMeeting,responseStatus",
        }

        response = client.get(endpoint, params=params)
        events_data = response.get("value", [])

        events = [_format_event_preview(e) for e in events_data]

        # Apply list truncation
        list_result = truncate_list_response(
            events, char_offset=item_offset, max_chars=MAX_RESPONSE_CHARS
        )

        emit_success(f"Found {list_result['items_returned']} event(s)")

        result = {
            "success": True,
            "events": list_result["items"],
            "total_count": len(events),
            "start": start,
            "end": end,
            "truncated": list_result["truncated"],
            "items_returned": list_result["items_returned"],
        }

        if list_result["truncated"]:
            result["next_offset"] = list_result["next_offset"]
            result["truncation_message"] = list_result.get("message")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_events(agent: Any) -> Tool:
    """Register the msgraph_list_events tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_events)


# =============================================================================
# GET EVENT TOOL
# =============================================================================


def msgraph_get_event(
    ctx: RunContext, event_id: str, char_offset: int = 0
) -> dict:
    """Get a specific calendar event.

    Args:
        event_id: The event ID.
        char_offset: Character offset for paginating large event bodies (default 0).
            If body exceeds 10,000 chars, use body_next_offset to continue.

    Returns:
        Dict with success, event details, or error.
        If body is truncated: body_truncated=True, body_next_offset, body_total_chars.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Getting event: {event_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/me/events/{event_id}"
        params = {
            "$select": "id,subject,start,end,location,body,organizer,"
            "attendees,isAllDay,isCancelled,isOnlineMeeting,"
            "onlineMeeting,webLink,responseStatus",
        }

        event_data = client.get(endpoint, params=params)
        event = _format_event(event_data)

        # Apply truncation to the body if it's large
        body_content = event.get("body", "")
        if len(body_content) > MAX_RESPONSE_CHARS:
            body_truncation = truncate_content(
                body_content, char_offset=char_offset, max_chars=MAX_RESPONSE_CHARS
            )
            event["body"] = body_truncation["content"]
            event["body_truncated"] = body_truncation["truncated"]
            event["body_char_offset"] = body_truncation["char_offset"]
            event["body_next_offset"] = body_truncation["next_offset"]
            event["body_total_chars"] = body_truncation["total_chars"]
        else:
            event["body_truncated"] = False
            event["body_total_chars"] = len(body_content)

        emit_success(f"Retrieved event: {event['subject']}")

        return {
            "success": True,
            "event": event,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_event(agent: Any) -> Tool:
    """Register the msgraph_get_event tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_event)


# =============================================================================
# CREATE EVENT TOOL
# =============================================================================


def msgraph_create_event(
    ctx: RunContext,
    subject: str,
    start: str,
    end: str,
    attendees: list[str] | None = None,
    body: str | None = None,
    location: str | None = None,
    is_online_meeting: bool = False,
) -> dict:
    """Create a calendar event.

    Args:
        subject: Event title.
        start: Start datetime in ISO format (e.g., "2025-12-18T10:00:00").
        end: End datetime in ISO format.
        attendees: Optional list of attendee email addresses.
        body: Optional event body/description.
        location: Optional location string.
        is_online_meeting: If True, create a Teams meeting.

    Returns:
        Dict with success, created event (id, webLink), or error.
    """
    meeting_type = "Teams meeting" if is_online_meeting else "event"
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Creating {meeting_type}: {subject}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build event payload
        event_payload: dict[str, Any] = {
            "subject": subject,
            "start": _format_datetime_for_graph(start),
            "end": _format_datetime_for_graph(end),
        }

        # Add optional fields
        if body:
            event_payload["body"] = {
                "contentType": "Text",
                "content": body,
            }

        if location:
            event_payload["location"] = {
                "displayName": location,
            }

        if attendees:
            event_payload["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ]

        if is_online_meeting:
            event_payload["isOnlineMeeting"] = True
            event_payload["onlineMeetingProvider"] = "teamsForBusiness"

        # Create the event
        endpoint = "/me/calendar/events"
        response = client.post(endpoint, json=event_payload)

        # Extract key info from response
        event_id = response.get("id")
        web_link = response.get("webLink")
        teams_link = None
        if response.get("onlineMeeting"):
            teams_link = response.get("onlineMeeting", {}).get("joinUrl")

        emit_success(f"Created {meeting_type}: {subject}")

        result = {
            "success": True,
            "event": {
                "id": event_id,
                "subject": subject,
                "start": start,
                "end": end,
                "web_link": web_link,
            },
        }

        if teams_link:
            result["event"]["teams_link"] = teams_link

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_create_event(agent: Any) -> Tool:
    """Register the msgraph_create_event tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_create_event)


# =============================================================================
# UPDATE EVENT TOOL
# =============================================================================


def msgraph_update_event(
    ctx: RunContext,
    event_id: str,
    subject: str | None = None,
    start: str | None = None,
    end: str | None = None,
    body: str | None = None,
    location: str | None = None,
) -> dict:
    """Update an existing calendar event.

    Args:
        event_id: The event ID to update.
        subject: New subject (optional).
        start: New start datetime (optional).
        end: New end datetime (optional).
        body: New body (optional).
        location: New location (optional).

    Returns:
        Dict with success, updated event, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Updating event: {event_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build update payload (only include provided fields)
        update_payload: dict[str, Any] = {}

        if subject is not None:
            update_payload["subject"] = subject

        if start is not None:
            update_payload["start"] = _format_datetime_for_graph(start)

        if end is not None:
            update_payload["end"] = _format_datetime_for_graph(end)

        if body is not None:
            update_payload["body"] = {
                "contentType": "Text",
                "content": body,
            }

        if location is not None:
            update_payload["location"] = {
                "displayName": location,
            }

        if not update_payload:
            return {
                "success": False,
                "error": "No fields provided to update",
                "error_type": "validation",
            }

        # Update the event
        endpoint = f"/me/events/{event_id}"
        response = client.patch(endpoint, json=update_payload)

        event = _format_event(response)

        emit_success(f"Updated event: {event['subject']}")

        return {
            "success": True,
            "event": event,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_update_event(agent: Any) -> Tool:
    """Register the msgraph_update_event tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_update_event)


# =============================================================================
# DELETE EVENT TOOL
# =============================================================================


def msgraph_delete_event(ctx: RunContext, event_id: str) -> dict:
    """Delete a calendar event.

    Args:
        event_id: The event ID to delete.

    Returns:
        Dict with success, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Deleting event: {event_id[:20]}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = f"/me/events/{event_id}"
        client.delete(endpoint)

        emit_success("Event deleted successfully")

        return {
            "success": True,
            "message": "Event deleted successfully",
            "event_id": event_id,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_delete_event(agent: Any) -> Tool:
    """Register the msgraph_delete_event tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_delete_event)


# =============================================================================
# GET AVAILABILITY TOOL
# =============================================================================


def msgraph_get_availability(
    ctx: RunContext,
    emails: list[str],
    start: str,
    end: str,
    interval_minutes: int = 30,
) -> dict:
    """Check free/busy availability for users.

    Args:
        emails: List of email addresses to check.
        start: Start datetime in ISO format.
        end: End datetime in ISO format.
        interval_minutes: Time slot interval in minutes (default 30).

    Returns:
        Dict with success, schedules (free/busy info per user), or error.
    """
    emails_str = ", ".join(emails[:3])
    if len(emails) > 3:
        emails_str += f" (+{len(emails) - 3} more)"

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Checking availability for: {emails_str}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build the getSchedule request payload
        payload = {
            "schedules": emails,
            "startTime": _format_datetime_for_graph(start),
            "endTime": _format_datetime_for_graph(end),
            "availabilityViewInterval": interval_minutes,
        }

        endpoint = "/me/calendar/getSchedule"
        response = client.post(endpoint, json=payload)

        schedules_data = response.get("value", [])

        # Format schedules for output
        schedules = []
        for schedule in schedules_data:
            schedule_items = schedule.get("scheduleItems", [])
            formatted_items = []
            for item in schedule_items:
                formatted_items.append(
                    {
                        "status": item.get("status"),
                        "subject": item.get("subject"),
                        "location": item.get("location"),
                        "start": item.get("start", {}).get("dateTime"),
                        "end": item.get("end", {}).get("dateTime"),
                    }
                )

            schedules.append(
                {
                    "email": schedule.get("scheduleId"),
                    "availability_view": schedule.get("availabilityView"),
                    "schedule_items": formatted_items,
                    "working_hours": schedule.get("workingHours"),
                }
            )

        emit_success(f"Retrieved availability for {len(schedules)} user(s)")

        return {
            "success": True,
            "schedules": schedules,
            "start": start,
            "end": end,
            "interval_minutes": interval_minutes,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_availability(agent: Any) -> Tool:
    """Register the msgraph_get_availability tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_get_availability)


# =============================================================================
# LIST CALENDARS TOOL
# =============================================================================


def msgraph_list_calendars(ctx: RunContext) -> dict:
    """List all calendars for the current user.

    Returns:
        Dict with success, calendars list, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📅 [bold cyan]Listing calendars[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        endpoint = "/me/calendars"
        params = {
            "$select": "id,name,color,isDefaultCalendar,canEdit,canShare,owner",
        }

        response = client.get(endpoint, params=params)
        calendars_data = response.get("value", [])

        calendars = [_format_calendar(c) for c in calendars_data]
        total_count = len(calendars)

        emit_success(f"Found {total_count} calendar(s)")

        return {
            "success": True,
            "calendars": calendars,
            "total_count": total_count,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_calendars(agent: Any) -> Tool:
    """Register the msgraph_list_calendars tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance.

    Returns:
        The registered Tool instance.
    """
    return agent.tool(msgraph_list_calendars)
