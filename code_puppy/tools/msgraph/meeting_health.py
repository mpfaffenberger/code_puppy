"""Meeting Health Monitoring tools for Microsoft Graph.

Provides proactive meeting health analysis and remediation:
- Detect upcoming meetings with issues (room cancellations, low acceptance)
- Analyze meeting response rates
- Suggest remediation actions (find new rooms, reschedule)
- Monitor recurring meeting health over time

These tools enable executive assistant workflows for proactive
meeting management rather than reactive scrambling.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _calculate_acceptance_rate(attendees: list[dict]) -> dict:
    """Calculate meeting acceptance statistics.

    Returns dict with total, accepted, declined, tentative,
    no_response counts and acceptance_rate percentage.
    """
    total = len(attendees)
    if total == 0:
        return {
            "total": 0,
            "accepted": 0,
            "declined": 0,
            "tentative": 0,
            "no_response": 0,
            "acceptance_rate": 0.0,
        }

    accepted = sum(
        1 for a in attendees if a.get("status", {}).get("response") == "accepted"
    )
    declined = sum(
        1 for a in attendees if a.get("status", {}).get("response") == "declined"
    )
    tentative = sum(
        1
        for a in attendees
        if a.get("status", {}).get("response") == "tentativelyAccepted"
    )
    no_response = sum(
        1
        for a in attendees
        if a.get("status", {}).get("response") in ("none", "notResponded", None)
    )

    acceptance_rate = (accepted / total) * 100 if total > 0 else 0.0

    return {
        "total": total,
        "accepted": accepted,
        "declined": declined,
        "tentative": tentative,
        "no_response": no_response,
        "acceptance_rate": round(acceptance_rate, 1),
    }


def _check_room_status(location: dict | None) -> dict:
    """Check if a meeting room/location might be problematic.

    Returns dict with has_room, room_name, and potential issues.
    """
    if not location:
        return {
            "has_room": False,
            "room_name": None,
            "issues": ["No location specified"],
        }

    display_name = location.get("displayName", "")
    location_type = location.get("locationType", "")

    issues = []

    # Check for empty or TBD locations
    if not display_name or display_name.lower() in ("tbd", "tba", "to be determined"):
        issues.append("Location not confirmed")

    # Check if it's a conference room type
    is_room = location_type == "conferenceRoom" or "room" in display_name.lower()

    return {
        "has_room": is_room and not issues,
        "room_name": display_name if display_name else None,
        "location_type": location_type,
        "issues": issues,
    }


def _assess_meeting_health(event: dict) -> dict:
    """Assess overall health of a meeting.

    Returns health assessment with issues and severity.
    """
    issues = []
    severity = "healthy"  # healthy, warning, critical

    # Check acceptance rate
    attendees = event.get("attendees", [])
    acceptance = _calculate_acceptance_rate(attendees)

    if acceptance["total"] > 0:
        if acceptance["acceptance_rate"] < 50:
            issues.append(
                {
                    "type": "low_acceptance",
                    "message": f"Only {acceptance['acceptance_rate']}% acceptance rate",
                    "details": acceptance,
                }
            )
            severity = "critical" if acceptance["acceptance_rate"] < 25 else "warning"

        if acceptance["declined"] > 0:
            declined_names = [
                a.get("emailAddress", {}).get("name", "Unknown")
                for a in attendees
                if a.get("status", {}).get("response") == "declined"
            ]
            issues.append(
                {
                    "type": "has_declines",
                    "message": f"{acceptance['declined']} attendee(s) declined",
                    "declined_by": declined_names,
                }
            )

    # Check room/location
    location = event.get("location")
    room_status = _check_room_status(location)
    if room_status["issues"]:
        issues.append(
            {
                "type": "location_issue",
                "message": room_status["issues"][0],
                "details": room_status,
            }
        )
        if severity == "healthy":
            severity = "warning"

    # Check if meeting is soon with no responses
    start_str = event.get("start", {}).get("dateTime", "")
    if start_str and acceptance["no_response"] > acceptance["total"] / 2:
        try:
            # Parse the start time
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_until = (start_dt - now).total_seconds() / 3600

            if hours_until < 24 and hours_until > 0:
                issues.append(
                    {
                        "type": "pending_responses_urgent",
                        "message": f"Meeting in {hours_until:.1f} hours with {acceptance['no_response']} pending responses",
                        "hours_until": round(hours_until, 1),
                    }
                )
                severity = "critical"
        except (ValueError, TypeError):
            pass

    return {
        "health": severity,
        "issues": issues,
        "acceptance": acceptance,
        "room_status": room_status,
    }


# =============================================================================
# TOOL: ANALYZE UPCOMING MEETINGS HEALTH
# =============================================================================


def msgraph_analyze_meeting_health(
    ctx: RunContext[Any],
    *,
    days_ahead: int = 7,
    include_healthy: bool = False,
) -> dict:
    """Analyze health of upcoming meetings and identify potential issues.

    Scans upcoming calendar events and identifies:
    - Low acceptance rates
    - Missing/declined responses
    - Room/location issues
    - Urgent meetings with pending responses

    Args:
        ctx: The run context.
        days_ahead: Number of days ahead to scan (default 7).
        include_healthy: Include healthy meetings in results (default False).

    Returns:
        Dict with meetings categorized by health status and actionable insights.
    """
    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error("Not authenticated")

    emit_info(f"🔍 Analyzing meeting health for next {days_ahead} days...")

    # Calculate time range
    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days_ahead)

    params = {
        "$filter": f"start/dateTime ge '{now.isoformat()}' and start/dateTime le '{end_date.isoformat()}'",
        "$orderby": "start/dateTime",
        "$top": 50,
        "$select": "id,subject,start,end,location,attendees,organizer,isOnlineMeeting,onlineMeetingUrl",
    }

    try:
        response = client.get("/me/events", params=params)
    except Exception as e:
        return _handle_msgraph_error(e)

    events = response.get("value", [])

    # Analyze each meeting
    critical = []
    warning = []
    healthy = []

    for event in events:
        health = _assess_meeting_health(event)

        meeting_info = {
            "id": event.get("id"),
            "subject": event.get("subject", "(No subject)"),
            "start": event.get("start", {}).get("dateTime"),
            "location": event.get("location", {}).get("displayName"),
            "is_online": event.get("isOnlineMeeting", False),
            "health": health,
        }

        if health["health"] == "critical":
            critical.append(meeting_info)
        elif health["health"] == "warning":
            warning.append(meeting_info)
        else:
            healthy.append(meeting_info)

    # Build summary
    total = len(events)

    result = {
        "success": True,
        "summary": {
            "total_meetings": total,
            "critical_count": len(critical),
            "warning_count": len(warning),
            "healthy_count": len(healthy),
            "scan_range_days": days_ahead,
        },
        "critical": critical,
        "warning": warning,
    }

    if include_healthy:
        result["healthy"] = healthy

    # Add recommendations
    recommendations = []
    if critical:
        recommendations.append(
            f"🚨 {len(critical)} meeting(s) need immediate attention"
        )
    if warning:
        recommendations.append(
            f"⚠️ {len(warning)} meeting(s) have potential issues to review"
        )

    result["recommendations"] = recommendations

    if critical:
        emit_warning(f"Found {len(critical)} critical meeting issue(s)!")
    else:
        emit_success(f"Analyzed {total} meetings - {len(healthy)} healthy!")

    return result


def register_msgraph_analyze_meeting_health(agent: Any) -> Tool:
    """Register the analyze meeting health tool."""
    return agent.tool()(msgraph_analyze_meeting_health)


# =============================================================================
# TOOL: GET MEETING ACCEPTANCE DETAILS
# =============================================================================


def msgraph_get_meeting_responses(
    ctx: RunContext[Any],
    *,
    event_id: str,
) -> dict:
    """Get detailed response status for a specific meeting.

    Shows who has accepted, declined, tentatively accepted,
    or not responded to a meeting invitation.

    Args:
        ctx: The run context.
        event_id: The ID of the calendar event.

    Returns:
        Dict with attendees grouped by response status.
    """
    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error("Not authenticated")

    emit_info("📊 Getting meeting response details...")

    try:
        response = client.get(
            f"/me/events/{event_id}",
            params={"$select": "id,subject,start,attendees,organizer"},
        )
    except Exception as e:
        return _handle_msgraph_error(e)

    attendees = response.get("attendees", [])

    # Group by response status
    accepted = []
    declined = []
    tentative = []
    no_response = []

    for attendee in attendees:
        email_info = attendee.get("emailAddress", {})
        status = attendee.get("status", {}).get("response", "none")
        attendee_type = attendee.get("type", "required")

        info = {
            "name": email_info.get("name", "Unknown"),
            "email": email_info.get("address", ""),
            "type": attendee_type,
        }

        if status == "accepted":
            accepted.append(info)
        elif status == "declined":
            declined.append(info)
        elif status == "tentativelyAccepted":
            tentative.append(info)
        else:
            no_response.append(info)

    stats = _calculate_acceptance_rate(attendees)

    emit_success(f"Retrieved responses for {len(attendees)} attendees")

    return {
        "success": True,
        "event_id": event_id,
        "subject": response.get("subject", "(No subject)"),
        "start": response.get("start", {}).get("dateTime"),
        "statistics": stats,
        "accepted": accepted,
        "declined": declined,
        "tentative": tentative,
        "no_response": no_response,
    }


def register_msgraph_get_meeting_responses(agent: Any) -> Tool:
    """Register the get meeting responses tool."""
    return agent.tool()(msgraph_get_meeting_responses)


# =============================================================================
# TOOL: FIND MEETINGS NEEDING RSVP FOLLOW-UP
# =============================================================================


def msgraph_find_pending_rsvps(
    ctx: RunContext[Any],
    *,
    hours_ahead: int = 48,
    min_no_response_pct: float = 50.0,
) -> dict:
    """Find upcoming meetings where many attendees haven't responded.

    Useful for proactively following up before meetings to ensure attendance.

    Args:
        ctx: The run context.
        hours_ahead: How many hours ahead to look (default 48).
        min_no_response_pct: Minimum % of no-responses to flag (default 50).

    Returns:
        Dict with meetings needing RSVP follow-up.
    """
    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error("Not authenticated")

    emit_info(
        f"🔔 Finding meetings needing RSVP follow-up in next {hours_ahead} hours..."
    )

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(hours=hours_ahead)

    params = {
        "$filter": f"start/dateTime ge '{now.isoformat()}' and start/dateTime le '{end_date.isoformat()}'",
        "$orderby": "start/dateTime",
        "$top": 30,
        "$select": "id,subject,start,attendees,organizer",
    }

    try:
        response = client.get("/me/events", params=params)
    except Exception as e:
        return _handle_msgraph_error(e)

    events = response.get("value", [])
    needs_followup = []

    for event in events:
        attendees = event.get("attendees", [])
        if not attendees:
            continue

        stats = _calculate_acceptance_rate(attendees)
        no_response_pct = (
            (stats["no_response"] / stats["total"]) * 100 if stats["total"] > 0 else 0
        )

        if no_response_pct >= min_no_response_pct:
            # Get names of non-responders
            non_responders = [
                a.get("emailAddress", {}).get("name", "Unknown")
                for a in attendees
                if a.get("status", {}).get("response") in ("none", "notResponded", None)
            ]

            needs_followup.append(
                {
                    "id": event.get("id"),
                    "subject": event.get("subject", "(No subject)"),
                    "start": event.get("start", {}).get("dateTime"),
                    "total_attendees": stats["total"],
                    "no_response_count": stats["no_response"],
                    "no_response_pct": round(no_response_pct, 1),
                    "non_responders": non_responders[:10],  # Limit to first 10
                }
            )

    emit_success(f"Found {len(needs_followup)} meeting(s) needing follow-up")

    return {
        "success": True,
        "hours_ahead": hours_ahead,
        "threshold_pct": min_no_response_pct,
        "meetings_needing_followup": needs_followup,
        "total_found": len(needs_followup),
    }


def register_msgraph_find_pending_rsvps(agent: Any) -> Tool:
    """Register the find pending RSVPs tool."""
    return agent.tool()(msgraph_find_pending_rsvps)


# =============================================================================
# TOOL: CHECK MEETINGS I HAVEN'T RESPONDED TO
# =============================================================================


def msgraph_find_my_pending_responses(
    ctx: RunContext[Any],
    *,
    days_ahead: int = 7,
) -> dict:
    """Find meeting invitations you haven't responded to yet.

    Helps maintain good meeting hygiene by identifying outstanding RSVPs.

    Args:
        ctx: The run context.
        days_ahead: Number of days ahead to scan (default 7).

    Returns:
        Dict with meetings awaiting your response.
    """
    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error("Not authenticated")

    emit_info("📬 Finding meetings awaiting your response...")

    now = datetime.now(timezone.utc)
    end_date = now + timedelta(days=days_ahead)

    params = {
        "$filter": f"start/dateTime ge '{now.isoformat()}' and start/dateTime le '{end_date.isoformat()}' and responseStatus/response eq 'notResponded'",
        "$orderby": "start/dateTime",
        "$top": 50,
        "$select": "id,subject,start,end,location,organizer,isOnlineMeeting",
    }

    try:
        response = client.get("/me/events", params=params)
    except Exception as e:
        return _handle_msgraph_error(e)

    events = response.get("value", [])

    pending = []
    for event in events:
        organizer = event.get("organizer", {}).get("emailAddress", {})

        pending.append(
            {
                "id": event.get("id"),
                "subject": event.get("subject", "(No subject)"),
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "location": event.get("location", {}).get("displayName"),
                "organizer_name": organizer.get("name"),
                "organizer_email": organizer.get("address"),
                "is_online": event.get("isOnlineMeeting", False),
            }
        )

    emit_success(f"Found {len(pending)} meeting(s) awaiting your response")

    return {
        "success": True,
        "days_ahead": days_ahead,
        "pending_responses": pending,
        "total_pending": len(pending),
    }


def register_msgraph_find_my_pending_responses(agent: Any) -> Tool:
    """Register the find my pending responses tool."""
    return agent.tool()(msgraph_find_my_pending_responses)


# =============================================================================
# TOOL: SUGGEST RESCHEDULE TIMES
# =============================================================================


def msgraph_suggest_reschedule(
    ctx: RunContext[Any],
    *,
    event_id: str,
    duration_minutes: int | None = None,
) -> dict:
    """Suggest better meeting times based on attendee availability.

    Uses the findMeetingTimes API to suggest times when more
    attendees are available.

    Args:
        ctx: The run context.
        event_id: The ID of the meeting to reschedule.
        duration_minutes: Meeting duration (uses original if not specified).

    Returns:
        Dict with suggested alternative times and availability info.
    """
    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error("Not authenticated")

    emit_info("🗓️ Finding better times for this meeting...")

    # First get the meeting details
    try:
        event = client.get(
            f"/me/events/{event_id}",
            params={"$select": "id,subject,start,end,attendees"},
        )
    except Exception as e:
        return _handle_msgraph_error(e)

    attendees = event.get("attendees", [])
    if not attendees:
        return {
            "success": False,
            "error": "No attendees on this meeting to check availability",
        }

    # Calculate duration from original meeting if not specified
    if not duration_minutes:
        start_str = event.get("start", {}).get("dateTime", "")
        end_str = event.get("end", {}).get("dateTime", "")
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
        except (ValueError, TypeError):
            duration_minutes = 60  # Default to 1 hour

    # Build findMeetingTimes request
    attendee_list = [
        {
            "emailAddress": a.get("emailAddress"),
            "type": a.get("type", "required"),
        }
        for a in attendees
    ]

    body = {
        "attendees": attendee_list,
        "meetingDuration": f"PT{duration_minutes}M",
        "maxCandidates": 5,
        "isOrganizerOptional": False,
    }

    try:
        response = client.post("/me/findMeetingTimes", json=body)
    except Exception as e:
        return _handle_msgraph_error(e)

    suggestions = response.get("meetingTimeSuggestions", [])

    formatted_suggestions = []
    for suggestion in suggestions:
        time_slot = suggestion.get("meetingTimeSlot", {})
        start = time_slot.get("start", {}).get("dateTime")
        end = time_slot.get("end", {}).get("dateTime")
        confidence = suggestion.get("confidence", 0)

        # Get attendee availability for this slot
        attendee_availability = []
        for att in suggestion.get("attendeeAvailability", []):
            attendee_availability.append(
                {
                    "name": att.get("attendee", {}).get("emailAddress", {}).get("name"),
                    "availability": att.get("availability"),
                }
            )

        formatted_suggestions.append(
            {
                "start": start,
                "end": end,
                "confidence": confidence,
                "attendee_availability": attendee_availability,
            }
        )

    emit_success(f"Found {len(formatted_suggestions)} potential time slots")

    return {
        "success": True,
        "event_id": event_id,
        "subject": event.get("subject", "(No subject)"),
        "original_start": event.get("start", {}).get("dateTime"),
        "duration_minutes": duration_minutes,
        "suggestions": formatted_suggestions,
        "total_suggestions": len(formatted_suggestions),
    }


def register_msgraph_suggest_reschedule(agent: Any) -> Tool:
    """Register the suggest reschedule tool."""
    return agent.tool()(msgraph_suggest_reschedule)
