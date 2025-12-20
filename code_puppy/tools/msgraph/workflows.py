"""High-level workflow tools for Microsoft Graph.

These tools compose multiple primitives into common workflows,
making complex operations simple one-shot actions.

Design principles:
- Each workflow tool replaces 3-5 primitive calls
- Focused on real user pain points (meeting prep, inbox triage, scheduling)
- Return rich, actionable summaries
- Gracefully handle partial failures
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# WORKFLOW: PREPARE MEETING BRIEF
# =============================================================================


def msgraph_prepare_meeting_brief(
    ctx: RunContext[Any],
    *,
    event_id: str | None = None,
    meeting_subject: str | None = None,
) -> dict:
    """Prepare a comprehensive meeting brief with all context in one call.

    Gathers:
    - Event details (time, location, description)
    - Attendee list with response status
    - Attendee profiles (titles, departments)
    - Recent emails mentioning the meeting subject
    - Related files in OneDrive (if any)

    Args:
        ctx: The run context.
        event_id: The calendar event ID. If not provided, uses meeting_subject.
        meeting_subject: Search for meeting by subject (if event_id not provided).

    Returns:
        Dict with comprehensive meeting brief including attendees, context, and prep notes.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📋 [bold cyan]Preparing meeting brief...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        # Step 1: Find the event
        event = None
        if event_id:
            event = client.get(
                f"/me/events/{event_id}",
                params={
                    "$select": "id,subject,start,end,location,body,attendees,organizer,isOnlineMeeting,onlineMeetingUrl"
                },
            )
        elif meeting_subject:
            # Search for the meeting
            now = datetime.now(timezone.utc)
            events = client.get(
                "/me/events",
                params={
                    "$filter": f"start/dateTime ge '{now.isoformat()}'",
                    "$orderby": "start/dateTime",
                    "$top": 50,
                    "$select": "id,subject,start,end,location,body,attendees,organizer,isOnlineMeeting,onlineMeetingUrl",
                },
            )
            # Find matching event
            subject_lower = meeting_subject.lower()
            for e in events.get("value", []):
                if subject_lower in e.get("subject", "").lower():
                    event = e
                    break

            if not event:
                return {
                    "success": False,
                    "error": f"No upcoming meeting found matching '{meeting_subject}'",
                }
        else:
            return {
                "success": False,
                "error": "Either event_id or meeting_subject must be provided",
            }

        # Step 2: Analyze attendees
        attendees = event.get("attendees", [])
        attendee_details = []
        accepted = 0
        declined = 0
        tentative = 0
        no_response = 0

        for att in attendees:
            email_info = att.get("emailAddress", {})
            status = att.get("status", {}).get("response", "none")
            att_type = att.get("type", "required")

            # Try to get user profile for more context
            profile = {}
            try:
                email = email_info.get("address", "")
                if email:
                    user = client.get(
                        f"/users/{email}",
                        params={"$select": "displayName,jobTitle,department"},
                    )
                    profile = {
                        "title": user.get("jobTitle", ""),
                        "department": user.get("department", ""),
                    }
            except Exception:
                pass  # Profile lookup failed, continue without it

            if status == "accepted":
                accepted += 1
            elif status == "declined":
                declined += 1
            elif status == "tentativelyAccepted":
                tentative += 1
            else:
                no_response += 1

            attendee_details.append(
                {
                    "name": email_info.get("name", "Unknown"),
                    "email": email_info.get("address", ""),
                    "type": att_type,
                    "response": status,
                    "title": profile.get("title", ""),
                    "department": profile.get("department", ""),
                }
            )

        # Step 3: Search for related emails (last 7 days)
        related_emails = []
        try:
            subject = event.get("subject", "")
            if subject:
                # Extract key words from subject for search
                mail_results = client.get(
                    "/me/messages",
                    params={
                        "$search": f'"{subject[:50]}"',
                        "$top": 5,
                        "$select": "id,subject,from,receivedDateTime,bodyPreview",
                        "$orderby": "receivedDateTime desc",
                    },
                )
                for msg in mail_results.get("value", []):
                    related_emails.append(
                        {
                            "subject": msg.get("subject", ""),
                            "from": msg.get("from", {})
                            .get("emailAddress", {})
                            .get("name", ""),
                            "date": msg.get("receivedDateTime", ""),
                            "preview": msg.get("bodyPreview", "")[:200],
                        }
                    )
        except Exception:
            pass  # Email search failed, continue without it

        # Step 4: Build the brief
        organizer = event.get("organizer", {}).get("emailAddress", {})
        location = event.get("location", {})

        brief = {
            "success": True,
            "meeting": {
                "id": event.get("id"),
                "subject": event.get("subject", "(No subject)"),
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "location": location.get("displayName", "No location"),
                "is_online": event.get("isOnlineMeeting", False),
                "meeting_url": event.get("onlineMeetingUrl"),
                "organizer": organizer.get("name", "Unknown"),
                "organizer_email": organizer.get("address", ""),
            },
            "attendance": {
                "total": len(attendees),
                "accepted": accepted,
                "declined": declined,
                "tentative": tentative,
                "no_response": no_response,
                "acceptance_rate": round((accepted / len(attendees)) * 100, 1)
                if attendees
                else 0,
            },
            "attendees": attendee_details,
            "related_emails": related_emails,
            "prep_notes": [],
        }

        # Add prep notes based on analysis
        if declined > 0:
            brief["prep_notes"].append(
                f"⚠️ {declined} attendee(s) declined - may need to reschedule"
            )
        if no_response > len(attendees) / 2:
            brief["prep_notes"].append(
                f"📧 {no_response} attendee(s) haven't responded - consider sending reminder"
            )
        if not location.get("displayName") and not event.get("isOnlineMeeting"):
            brief["prep_notes"].append("📍 No location or meeting link - add one!")
        if related_emails:
            brief["prep_notes"].append(
                f"📨 Found {len(related_emails)} related email(s) for context"
            )

        emit_success(f"Meeting brief prepared for '{event.get('subject', 'meeting')}'")
        return brief

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_prepare_meeting_brief(agent: Any) -> Tool:
    """Register the prepare meeting brief workflow tool."""
    return agent.tool()(msgraph_prepare_meeting_brief)


# =============================================================================
# WORKFLOW: DAILY DIGEST
# =============================================================================


def msgraph_daily_digest(
    ctx: RunContext[Any],
    *,
    include_tomorrow: bool = True,
) -> dict:
    """Get a comprehensive daily digest of calendar, mail, and tasks.

    Gathers in one call:
    - Today's meetings with attendance status
    - Tomorrow's meetings (optional)
    - Unread emails (top 10)
    - Meetings you haven't responded to
    - High-priority action items

    Args:
        ctx: The run context.
        include_tomorrow: Include tomorrow's calendar (default True).

    Returns:
        Dict with comprehensive daily summary.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "☀️ [bold cyan]Generating daily digest...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        tomorrow_end = today_start + timedelta(days=2)

        digest = {
            "success": True,
            "generated_at": now.isoformat(),
            "today": [],
            "tomorrow": [],
            "unread_emails": [],
            "pending_responses": [],
            "action_items": [],
        }

        # Step 1: Get today's events
        try:
            today_events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": today_start.isoformat(),
                    "endDateTime": today_end.isoformat(),
                    "$orderby": "start/dateTime",
                    "$select": "id,subject,start,end,location,attendees,isOnlineMeeting,responseStatus",
                },
            )
            for event in today_events.get("value", []):
                attendees = event.get("attendees", [])
                accepted = sum(
                    1
                    for a in attendees
                    if a.get("status", {}).get("response") == "accepted"
                )
                digest["today"].append(
                    {
                        "id": event.get("id"),
                        "subject": event.get("subject", "(No subject)"),
                        "start": event.get("start", {}).get("dateTime"),
                        "end": event.get("end", {}).get("dateTime"),
                        "location": event.get("location", {}).get("displayName", ""),
                        "attendee_count": len(attendees),
                        "accepted_count": accepted,
                        "your_response": event.get("responseStatus", {}).get(
                            "response", "none"
                        ),
                    }
                )

                # Check if you haven't responded
                my_response = event.get("responseStatus", {}).get("response", "none")
                if my_response in ("none", "notResponded"):
                    digest["pending_responses"].append(
                        {
                            "id": event.get("id"),
                            "subject": event.get("subject", "(No subject)"),
                            "start": event.get("start", {}).get("dateTime"),
                        }
                    )
        except Exception as e:
            digest["action_items"].append(f"⚠️ Could not fetch today's calendar: {e}")

        # Step 2: Get tomorrow's events
        if include_tomorrow:
            try:
                tomorrow_events = client.get(
                    "/me/calendarView",
                    params={
                        "startDateTime": today_end.isoformat(),
                        "endDateTime": tomorrow_end.isoformat(),
                        "$orderby": "start/dateTime",
                        "$select": "id,subject,start,end,location,isOnlineMeeting,responseStatus",
                    },
                )
                for event in tomorrow_events.get("value", []):
                    digest["tomorrow"].append(
                        {
                            "id": event.get("id"),
                            "subject": event.get("subject", "(No subject)"),
                            "start": event.get("start", {}).get("dateTime"),
                            "location": event.get("location", {}).get(
                                "displayName", ""
                            ),
                        }
                    )
            except Exception:
                pass  # Tomorrow's events not critical

        # Step 3: Get unread emails
        try:
            unread = client.get(
                "/me/mailFolders/inbox/messages",
                params={
                    "$filter": "isRead eq false",
                    "$orderby": "receivedDateTime desc",
                    "$top": 10,
                    "$select": "id,subject,from,receivedDateTime,importance",
                },
            )
            for msg in unread.get("value", []):
                digest["unread_emails"].append(
                    {
                        "id": msg.get("id"),
                        "subject": msg.get("subject", "(No subject)"),
                        "from": msg.get("from", {})
                        .get("emailAddress", {})
                        .get("name", "Unknown"),
                        "received": msg.get("receivedDateTime"),
                        "importance": msg.get("importance", "normal"),
                    }
                )
        except Exception as e:
            digest["action_items"].append(f"⚠️ Could not fetch unread emails: {e}")

        # Step 4: Build action items summary
        if digest["pending_responses"]:
            digest["action_items"].append(
                f"📬 Respond to {len(digest['pending_responses'])} meeting invite(s)"
            )
        if len(digest["unread_emails"]) >= 10:
            digest["action_items"].append(
                "📧 10+ unread emails - consider inbox triage"
            )
        high_priority = [
            e for e in digest["unread_emails"] if e.get("importance") == "high"
        ]
        if high_priority:
            digest["action_items"].append(
                f"🚨 {len(high_priority)} high-priority email(s) need attention"
            )

        # Summary stats
        digest["summary"] = {
            "meetings_today": len(digest["today"]),
            "meetings_tomorrow": len(digest["tomorrow"]),
            "unread_count": len(digest["unread_emails"]),
            "pending_rsvps": len(digest["pending_responses"]),
            "action_items_count": len(digest["action_items"]),
        }

        emit_success(
            f"Daily digest: {len(digest['today'])} meetings today, "
            f"{len(digest['unread_emails'])} unread emails"
        )
        return digest

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_daily_digest(agent: Any) -> Tool:
    """Register the daily digest workflow tool."""
    return agent.tool()(msgraph_daily_digest)


# =============================================================================
# WORKFLOW: SMART SCHEDULE MEETING
# =============================================================================


def msgraph_smart_schedule(
    ctx: RunContext[Any],
    *,
    subject: str,
    attendees: list[str],
    duration_minutes: int = 60,
    description: str = "",
    prefer_morning: bool = False,
    days_to_search: int = 5,
    auto_create: bool = False,
) -> dict:
    """Find the best meeting time and optionally create the event.

    Combines findMeetingTimes + createEvent into one smart workflow:
    1. Finds times when all attendees are available
    2. Ranks by preference (morning vs afternoon)
    3. Optionally creates the event automatically

    Args:
        ctx: The run context.
        subject: Meeting subject/title.
        attendees: List of attendee email addresses.
        duration_minutes: Meeting duration (default 60 minutes).
        description: Optional meeting description/body.
        prefer_morning: If True, prefer morning time slots (default False).
        days_to_search: Number of days to search (default 5).
        auto_create: If True, create the event at the best time (default False).

    Returns:
        Dict with suggested times and optionally the created event.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📅 [bold cyan]Finding optimal meeting time...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error("Not authenticated")

        if not attendees:
            return {"success": False, "error": "At least one attendee required"}

        # Step 1: Find meeting times
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days_to_search)

        attendee_list = [
            {"emailAddress": {"address": email}, "type": "required"}
            for email in attendees
        ]

        find_body = {
            "attendees": attendee_list,
            "timeConstraint": {
                "timeslots": [
                    {
                        "start": {"dateTime": now.isoformat(), "timeZone": "UTC"},
                        "end": {"dateTime": end_date.isoformat(), "timeZone": "UTC"},
                    }
                ]
            },
            "meetingDuration": f"PT{duration_minutes}M",
            "maxCandidates": 10,
            "isOrganizerOptional": False,
        }

        find_result = client.post("/me/findMeetingTimes", json=find_body)
        suggestions = find_result.get("meetingTimeSuggestions", [])

        if not suggestions:
            return {
                "success": True,
                "message": "No available times found for all attendees",
                "suggestions": [],
                "recommendation": "Try different attendees or a longer search window",
            }

        # Step 2: Rank and format suggestions
        formatted_suggestions = []
        for i, suggestion in enumerate(suggestions):
            time_slot = suggestion.get("meetingTimeSlot", {})
            start = time_slot.get("start", {}).get("dateTime", "")
            end = time_slot.get("end", {}).get("dateTime", "")
            confidence = suggestion.get("confidence", 0)

            # Parse time for morning preference
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                is_morning = start_dt.hour < 12
            except (ValueError, TypeError):
                is_morning = False

            # Score based on preferences
            score = confidence
            if prefer_morning and is_morning:
                score += 10
            elif not prefer_morning and not is_morning:
                score += 5

            formatted_suggestions.append(
                {
                    "rank": i + 1,
                    "start": start,
                    "end": end,
                    "confidence": confidence,
                    "is_morning": is_morning,
                    "score": score,
                }
            )

        # Sort by score
        formatted_suggestions.sort(key=lambda x: -x["score"])

        # Re-rank after sorting
        for i, s in enumerate(formatted_suggestions):
            s["rank"] = i + 1

        best = formatted_suggestions[0]

        result = {
            "success": True,
            "subject": subject,
            "duration_minutes": duration_minutes,
            "attendees": attendees,
            "suggestions": formatted_suggestions,
            "best_time": best,
        }

        # Step 3: Optionally create the event
        if auto_create:
            emit_info("📅 Creating event at best available time...")

            event_body = {
                "subject": subject,
                "start": {
                    "dateTime": best["start"],
                    "timeZone": "UTC",
                },
                "end": {
                    "dateTime": best["end"],
                    "timeZone": "UTC",
                },
                "attendees": attendee_list,
            }

            if description:
                event_body["body"] = {"contentType": "text", "content": description}

            created_event = client.post("/me/events", json=event_body)
            result["created_event"] = {
                "id": created_event.get("id"),
                "web_link": created_event.get("webLink"),
            }
            emit_success(f"Meeting '{subject}' created!")
        else:
            emit_success(
                f"Found {len(formatted_suggestions)} available times. "
                f"Best: {best['start'][:16]}"
            )

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_smart_schedule(agent: Any) -> Tool:
    """Register the smart schedule workflow tool."""
    return agent.tool()(msgraph_smart_schedule)
