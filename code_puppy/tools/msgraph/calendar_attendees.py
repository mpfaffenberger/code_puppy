"""Calendar Attendee Management tools for Microsoft Graph.

Provides tools for managing meeting attendees:
- Add attendees to existing events
- Remove attendees from events
- Search events by subject/text

These tools enable dynamic meeting management workflows
like handling reschedules and attendee changes.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# TOOL: ADD ATTENDEES TO EVENT
# =============================================================================


def msgraph_add_event_attendees(
    ctx: RunContext[Any],
    *,
    event_id: str,
    attendees: list[str],
    attendee_type: str = "required",
) -> dict:
    """Add attendees to an existing calendar event.

    Args:
        ctx: The run context.
        event_id: The ID of the calendar event to update.
        attendees: List of email addresses to add as attendees.
        attendee_type: Type of attendee - 'required' or 'optional' (default: required).

    Returns:
        Dict with success status and updated attendee list.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"➕ [bold cyan]Adding {len(attendees)} attendee(s)[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        # First, get the current event to preserve existing attendees
        event = client.get(
            f"/me/events/{event_id}",
            params={"$select": "id,subject,attendees"},
        )

        existing_attendees = event.get("attendees", [])

        # Build list of new attendees to add
        existing_emails = {
            a.get("emailAddress", {}).get("address", "").lower()
            for a in existing_attendees
        }

        new_attendees = []
        skipped = []
        for email in attendees:
            if email.lower() in existing_emails:
                skipped.append(email)
            else:
                new_attendees.append(
                    {
                        "emailAddress": {"address": email},
                        "type": attendee_type,
                    }
                )

        if not new_attendees:
            emit_warning("All attendees already on the invite")
            return {
                "success": True,
                "message": "All attendees already on the invite",
                "added": [],
                "skipped": skipped,
            }

        # Merge with existing attendees
        updated_attendees = existing_attendees + new_attendees

        # Update the event
        update_body = {"attendees": updated_attendees}
        client.patch(f"/me/events/{event_id}", json=update_body)

        added_emails = [a["emailAddress"]["address"] for a in new_attendees]
        emit_success(f"Added {len(added_emails)} attendee(s) to the event")

        return {
            "success": True,
            "event_id": event_id,
            "subject": event.get("subject", "(No subject)"),
            "added": added_emails,
            "skipped": skipped,
            "total_attendees": len(updated_attendees),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_add_event_attendees(agent: Any) -> Tool:
    """Register the add event attendees tool."""
    return agent.tool()(msgraph_add_event_attendees)


# =============================================================================
# TOOL: REMOVE ATTENDEE FROM EVENT
# =============================================================================


def msgraph_remove_event_attendee(
    ctx: RunContext[Any],
    *,
    event_id: str,
    attendee_email: str,
) -> dict:
    """Remove an attendee from a calendar event.

    Args:
        ctx: The run context.
        event_id: The ID of the calendar event to update.
        attendee_email: Email address of the attendee to remove.

    Returns:
        Dict with success status and updated attendee list.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"➖ [bold cyan]Removing attendee: {attendee_email}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        # Get the current event
        event = client.get(
            f"/me/events/{event_id}",
            params={"$select": "id,subject,attendees"},
        )

        existing_attendees = event.get("attendees", [])

        # Filter out the attendee to remove
        email_lower = attendee_email.lower()
        updated_attendees = [
            a
            for a in existing_attendees
            if a.get("emailAddress", {}).get("address", "").lower() != email_lower
        ]

        if len(updated_attendees) == len(existing_attendees):
            emit_warning(f"Attendee {attendee_email} not found on the invite")
            return {
                "success": False,
                "error": f"Attendee {attendee_email} not found on the invite",
            }

        # Update the event
        update_body = {"attendees": updated_attendees}
        client.patch(f"/me/events/{event_id}", json=update_body)

        emit_success(f"Removed {attendee_email} from the event")

        return {
            "success": True,
            "event_id": event_id,
            "subject": event.get("subject", "(No subject)"),
            "removed": attendee_email,
            "remaining_attendees": len(updated_attendees),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_remove_event_attendee(agent: Any) -> Tool:
    """Register the remove event attendee tool."""
    return agent.tool()(msgraph_remove_event_attendee)


# =============================================================================
# TOOL: SEARCH EVENTS BY SUBJECT
# =============================================================================


def msgraph_search_events(
    ctx: RunContext[Any],
    *,
    query: str,
    days_ahead: int = 30,
    days_back: int = 7,
    max_results: int = 20,
) -> dict:
    """Search calendar events by subject or body text.

    Args:
        ctx: The run context.
        query: Search text to look for in event subject/body.
        days_ahead: Number of days in the future to search (default 30).
        days_back: Number of days in the past to search (default 7).
        max_results: Maximum number of results to return (default 20).

    Returns:
        Dict with matching events.
    """
    from datetime import datetime, timedelta, timezone

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching events for: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        # Calculate date range
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days_back)
        end_date = now + timedelta(days=days_ahead)

        # Search events using $filter with contains
        # Note: Graph API text search is limited, so we'll filter client-side too
        params = {
            "$filter": (
                f"start/dateTime ge '{start_date.isoformat()}' and "
                f"start/dateTime le '{end_date.isoformat()}'"
            ),
            "$orderby": "start/dateTime",
            "$top": 100,  # Get more to filter client-side
            "$select": "id,subject,start,end,location,attendees,organizer,isOnlineMeeting",
        }

        response = client.get("/me/events", params=params)
        events = response.get("value", [])

        # Client-side filtering for the search query
        query_lower = query.lower()
        matches = []

        for event in events:
            subject = event.get("subject", "").lower()
            body_preview = event.get("bodyPreview", "").lower()
            location = event.get("location", {}).get("displayName", "").lower()

            if (
                query_lower in subject
                or query_lower in body_preview
                or query_lower in location
            ):
                organizer = event.get("organizer", {}).get("emailAddress", {})
                matches.append(
                    {
                        "id": event.get("id"),
                        "subject": event.get("subject"),
                        "start": event.get("start", {}).get("dateTime"),
                        "end": event.get("end", {}).get("dateTime"),
                        "location": event.get("location", {}).get("displayName"),
                        "organizer": organizer.get("name"),
                        "attendee_count": len(event.get("attendees", [])),
                        "is_online": event.get("isOnlineMeeting", False),
                    }
                )

                if len(matches) >= max_results:
                    break

        emit_success(f"Found {len(matches)} event(s) matching '{query}'")

        return {
            "success": True,
            "query": query,
            "events": matches,
            "total_found": len(matches),
            "search_range": {
                "days_back": days_back,
                "days_ahead": days_ahead,
            },
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_events(agent: Any) -> Tool:
    """Register the search events tool."""
    return agent.tool()(msgraph_search_events)


# =============================================================================
# TOOL: RESPOND TO EVENT (ACCEPT/DECLINE/TENTATIVE)
# =============================================================================


def msgraph_respond_to_event(
    ctx: RunContext[Any],
    *,
    event_id: str,
    response: str,
    comment: str | None = None,
    send_response: bool = True,
) -> dict:
    """Respond to a calendar event invitation.

    Args:
        ctx: The run context.
        event_id: The ID of the calendar event.
        response: Response type - 'accept', 'decline', or 'tentative'.
        comment: Optional message to include with response.
        send_response: Whether to send the response to the organizer (default True).

    Returns:
        Dict with success status.
    """
    response_lower = response.lower()
    if response_lower not in ("accept", "decline", "tentative"):
        return {
            "success": False,
            "error": "Response must be 'accept', 'decline', or 'tentative'",
        }

    emoji = {"accept": "✅", "decline": "❌", "tentative": "❓"}.get(
        response_lower, "📅"
    )

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"{emoji} [bold cyan]Responding to event: {response_lower}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        # Build the request body
        body: dict[str, Any] = {"sendResponse": send_response}
        if comment:
            body["comment"] = comment

        # Call the appropriate endpoint based on response type
        endpoint = f"/me/events/{event_id}/{response_lower}"
        client.post(endpoint, json=body)

        emit_success(f"Successfully responded: {response_lower}")

        return {
            "success": True,
            "event_id": event_id,
            "response": response_lower,
            "comment": comment,
            "notification_sent": send_response,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_respond_to_event(agent: Any) -> Tool:
    """Register the respond to event tool."""
    return agent.tool()(msgraph_respond_to_event)
