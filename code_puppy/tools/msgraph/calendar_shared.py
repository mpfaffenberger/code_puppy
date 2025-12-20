"""Shared Calendar tools for Microsoft Graph.

Provides tools for accessing and managing shared calendars:
- List calendars you have access to (including shared)
- View events from other users' calendars (with permissions)
- Find meeting times across multiple attendees

Note: Accessing shared calendars requires appropriate permissions.
The user must have been granted access to the calendar.
"""

from typing import Any
from datetime import datetime, timedelta, timezone

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import get_msgraph_client, _handle_msgraph_error


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_calendar(data: dict) -> dict:
    """Format a calendar response."""
    owner = data.get("owner", {})
    return {
        "id": data.get("id"),
        "name": data.get("name"),
        "color": data.get("color"),
        "can_edit": data.get("canEdit", False),
        "can_share": data.get("canShare", False),
        "can_view_private_items": data.get("canViewPrivateItems", False),
        "is_default": data.get("isDefaultCalendar", False),
        "owner_name": owner.get("name"),
        "owner_email": owner.get("address"),
    }


def _format_shared_event(data: dict) -> dict:
    """Format a calendar event from a shared calendar."""
    start = data.get("start", {})
    end = data.get("end", {})
    organizer = data.get("organizer", {}).get("emailAddress", {})
    location = data.get("location", {})

    return {
        "id": data.get("id"),
        "subject": data.get("subject"),
        "start": start.get("dateTime"),
        "start_timezone": start.get("timeZone"),
        "end": end.get("dateTime"),
        "end_timezone": end.get("timeZone"),
        "is_all_day": data.get("isAllDay", False),
        "show_as": data.get("showAs"),  # free, tentative, busy, oof, workingElsewhere
        "location": location.get("displayName"),
        "organizer_name": organizer.get("name"),
        "organizer_email": organizer.get("address"),
        "sensitivity": data.get(
            "sensitivity"
        ),  # normal, personal, private, confidential
    }


# =============================================================================
# SHARED CALENDAR TOOLS
# =============================================================================


def msgraph_list_shared_calendars(ctx: RunContext) -> dict:
    """List all calendars including shared calendars.

    Returns calendars that have been shared with you by other users.

    Returns:
        Dict with success, calendars list, or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📅 [bold cyan]Listing all calendars (including shared)[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        response = client.get("/me/calendars", params={"$top": 50})
        calendars_data = response.get("value", [])

        calendars = [_format_calendar(c) for c in calendars_data]

        # Separate own vs shared
        own_calendars = [c for c in calendars if not c.get("owner_email")]
        shared_calendars = [c for c in calendars if c.get("owner_email")]

        emit_success(
            f"Found {len(calendars)} calendar(s): "
            f"{len(own_calendars)} own, {len(shared_calendars)} shared"
        )

        return {
            "success": True,
            "calendars": calendars,
            "own_count": len(own_calendars),
            "shared_count": len(shared_calendars),
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_list_shared_calendars(agent: Any) -> Tool:
    """Register the msgraph_list_shared_calendars tool."""
    return agent.tool(msgraph_list_shared_calendars)


def msgraph_get_user_calendar_events(
    ctx: RunContext,
    user_email: str,
    days_ahead: int = 7,
    limit: int = 25,
) -> dict:
    """Get events from another user's calendar.

    Requires you to have permission to view their calendar.
    Works with users who have shared their calendar with you.

    Args:
        user_email: Email address of the user whose calendar to view.
        days_ahead: Number of days to look ahead (default 7).
        limit: Maximum events to return.

    Returns:
        Dict with success, events list, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Getting calendar events for {user_email}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Calculate date range
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(days=days_ahead)

        params = {
            "startDateTime": start_time.isoformat() + "Z",
            "endDateTime": end_time.isoformat() + "Z",
            "$top": limit,
            "$select": "id,subject,start,end,location,organizer,isAllDay,showAs,sensitivity",
            "$orderby": "start/dateTime",
        }

        response = client.get(f"/users/{user_email}/calendarView", params=params)
        events_data = response.get("value", [])

        events = [_format_shared_event(e) for e in events_data]

        emit_success(f"Found {len(events)} event(s) for {user_email}")

        return {
            "success": True,
            "user_email": user_email,
            "events": events,
            "total_count": len(events),
            "date_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_user_calendar_events(agent: Any) -> Tool:
    """Register the msgraph_get_user_calendar_events tool."""
    return agent.tool(msgraph_get_user_calendar_events)


def msgraph_find_meeting_times(
    ctx: RunContext,
    attendees: list[str],
    duration_minutes: int = 30,
    days_ahead: int = 7,
    max_candidates: int = 5,
) -> dict:
    """Find available meeting times for multiple attendees.

    This is more powerful than get_availability - it suggests
    specific time slots when all attendees are free.

    Args:
        attendees: List of attendee email addresses.
        duration_minutes: Meeting duration in minutes.
        days_ahead: How many days ahead to search.
        max_candidates: Maximum number of time suggestions.

    Returns:
        Dict with success, suggested meeting times, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Finding meeting times for {len(attendees)} attendee(s)[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        # Build request
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(days=days_ahead)

        request_body = {
            "attendees": [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendees
            ],
            "timeConstraint": {
                "timeslots": [
                    {
                        "start": {
                            "dateTime": start_time.isoformat(),
                            "timeZone": "UTC",
                        },
                        "end": {
                            "dateTime": end_time.isoformat(),
                            "timeZone": "UTC",
                        },
                    }
                ]
            },
            "meetingDuration": f"PT{duration_minutes}M",
            "maxCandidates": max_candidates,
            "isOrganizerOptional": False,
            "returnSuggestionReasons": True,
        }

        response = client.post("/me/findMeetingTimes", json=request_body)

        suggestions = []
        for slot in response.get("meetingTimeSuggestions", []):
            time_slot = slot.get("meetingTimeSlot", {})
            start = time_slot.get("start", {})
            end = time_slot.get("end", {})

            suggestions.append(
                {
                    "start": start.get("dateTime"),
                    "end": end.get("dateTime"),
                    "timezone": start.get("timeZone"),
                    "confidence": slot.get("confidence"),
                    "organizer_availability": slot.get("organizerAvailability"),
                    "suggestion_reason": slot.get("suggestionReason"),
                }
            )

        empty_reason = response.get("emptySuggestionsReason", "")
        if empty_reason:
            emit_warning(f"Limited availability: {empty_reason}")

        emit_success(f"Found {len(suggestions)} suggested meeting time(s)")

        return {
            "success": True,
            "attendees": attendees,
            "duration_minutes": duration_minutes,
            "suggestions": suggestions,
            "empty_reason": empty_reason,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_find_meeting_times(agent: Any) -> Tool:
    """Register the msgraph_find_meeting_times tool."""
    return agent.tool(msgraph_find_meeting_times)


def msgraph_get_schedule(
    ctx: RunContext,
    schedules: list[str],
    start_time: str,
    end_time: str,
) -> dict:
    """Get free/busy schedule for multiple users.

    This shows when people are busy without revealing meeting details.
    Useful for finding overlapping free time.

    Args:
        schedules: List of email addresses to check.
        start_time: Start of range (ISO format, e.g., "2025-12-18T09:00:00").
        end_time: End of range (ISO format).

    Returns:
        Dict with success, schedule info per user, or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"📅 [bold cyan]Getting schedules for {len(schedules)} user(s)[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()

        request_body = {
            "schedules": schedules,
            "startTime": {
                "dateTime": start_time,
                "timeZone": "UTC",
            },
            "endTime": {
                "dateTime": end_time,
                "timeZone": "UTC",
            },
            "availabilityViewInterval": 30,  # 30-minute slots
        }

        response = client.post("/me/calendar/getSchedule", json=request_body)

        schedules_result = []
        for schedule in response.get("value", []):
            email = schedule.get("scheduleId")
            availability = schedule.get("availabilityView", "")

            # Decode availability string (0=free, 1=tentative, 2=busy, 3=oof, 4=workingElsewhere)
            items = []
            for item in schedule.get("scheduleItems", []):
                start = item.get("start", {})
                end = item.get("end", {})
                items.append(
                    {
                        "start": start.get("dateTime"),
                        "end": end.get("dateTime"),
                        "status": item.get("status"),
                        "subject": item.get(
                            "subject"
                        ),  # May be hidden based on permissions
                    }
                )

            schedules_result.append(
                {
                    "email": email,
                    "availability_view": availability,
                    "schedule_items": items,
                    "working_hours": schedule.get("workingHours"),
                }
            )

        emit_success(f"Retrieved schedules for {len(schedules_result)} user(s)")

        return {
            "success": True,
            "schedules": schedules_result,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_schedule(agent: Any) -> Tool:
    """Register the msgraph_get_schedule tool."""
    return agent.tool(msgraph_get_schedule)
