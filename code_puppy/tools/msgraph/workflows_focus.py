"""Daily Focus and Smart Prioritization Workflows.

This module provides high-level productivity tools:
- Daily focus: What to focus on today
- Smart agenda: Upcoming meetings with prep notes
- Action items: Synthesize actionable tasks from context

Design Principles:
- Combine multiple data sources for holistic view
- Prioritize by sender importance and deadlines
- Surface blockers and urgent items first
- Provide actionable recommendations
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# DAILY FOCUS
# =============================================================================


def msgraph_daily_focus(
    ctx: RunContext[Any],
    *,
    include_emails: bool = True,
    include_calendar: bool = True,
    include_tasks: bool = True,
    max_items_per_category: int = 5,
) -> dict:
    """Get a prioritized daily focus view.

    Combines inbox, calendar, and tasks to show:
    1. Urgent items requiring immediate attention
    2. Today's meetings with prep status
    3. Top priority emails (from VIPs)
    4. Tasks due today or overdue
    5. Suggested focus areas

    Args:
        include_emails: Include email analysis (default True).
        include_calendar: Include today's meetings (default True).
        include_tasks: Include To Do tasks (default True).
        max_items_per_category: Max items per section (default 5).

    Returns:
        Dict with prioritized daily focus data.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f3af [bold cyan]Generating daily focus...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    result = {
        "success": True,
        "generated_at": now.isoformat(),
        "date": today_start.strftime("%A, %B %d, %Y"),
        "urgent": [],
        "meetings_today": [],
        "priority_emails": [],
        "tasks_due": [],
        "focus_suggestions": [],
        "sources_status": {},
    }

    # === GET RELEVANCE-RANKED PEOPLE ===
    email_to_rank: dict[str, int] = {}
    try:
        people = client.get(
            "/me/people",
            params={"$top": 50, "$select": "displayName,emailAddresses"},
        )
        for idx, person in enumerate(people.get("value", [])):
            for email_obj in person.get("emailAddresses", []):
                addr = email_obj.get("address", "").lower()
                if addr and addr not in email_to_rank:
                    email_to_rank[addr] = idx + 1
        result["sources_status"]["people"] = "success"
    except Exception as e:
        result["sources_status"]["people"] = f"failed: {str(e)[:50]}"

    # === CALENDAR - TODAY'S MEETINGS ===
    if include_calendar:
        try:
            events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": today_start.isoformat(),
                    "endDateTime": today_end.isoformat(),
                    "$select": "id,subject,start,end,organizer,isOnlineMeeting,onlineMeeting,responseStatus,importance,bodyPreview",
                    "$orderby": "start/dateTime",
                    "$top": 20,
                },
            )

            for event in events.get("value", []):
                start_dt = event.get("start", {}).get("dateTime", "")
                end_dt = event.get("end", {}).get("dateTime", "")
                organizer = event.get("organizer", {}).get("emailAddress", {})
                response = event.get("responseStatus", {}).get("response", "none")

                meeting_info = {
                    "id": event.get("id"),
                    "subject": event.get("subject"),
                    "start": start_dt,
                    "end": end_dt,
                    "organizer": organizer.get("name"),
                    "organizer_email": organizer.get("address"),
                    "is_online": event.get("isOnlineMeeting"),
                    "join_url": event.get("onlineMeeting", {}).get("joinUrl"),
                    "response": response,
                    "importance": event.get("importance"),
                    "preview": event.get("bodyPreview", "")[:100],
                }

                # Check if organizer is a VIP
                org_email = organizer.get("address", "").lower()
                organizer_rank = email_to_rank.get(org_email, 999)
                meeting_info["organizer_rank"] = (
                    organizer_rank if organizer_rank < 999 else None
                )

                # Flag meetings needing response
                if response in ["none", "notResponded"]:
                    meeting_info["needs_response"] = True
                    result["urgent"].append(
                        {
                            "type": "meeting_response_needed",
                            "subject": event.get("subject"),
                            "start": start_dt,
                            "organizer": organizer.get("name"),
                            "organizer_rank": organizer_rank
                            if organizer_rank < 999
                            else None,
                        }
                    )

                result["meetings_today"].append(meeting_info)

            result["sources_status"]["calendar"] = "success"
        except Exception as e:
            result["sources_status"]["calendar"] = f"failed: {str(e)[:50]}"

    # === EMAILS - PRIORITY FROM VIPS ===
    if include_emails:
        try:
            emails = client.get(
                "/me/messages",
                params={
                    "$filter": "isRead eq false",
                    "$top": 50,
                    "$select": "id,subject,from,receivedDateTime,importance,bodyPreview",
                    "$orderby": "receivedDateTime desc",
                },
            )

            scored_emails = []
            for email in emails.get("value", []):
                from_info = email.get("from", {}).get("emailAddress", {})
                from_addr = from_info.get("address", "").lower()
                from_name = from_info.get("name", "Unknown")

                rank = email_to_rank.get(from_addr, 999)
                importance_boost = -50 if email.get("importance") == "high" else 0
                score = rank + importance_boost

                if rank <= 20 or email.get("importance") == "high":
                    scored_emails.append(
                        {
                            "id": email.get("id"),
                            "subject": email.get("subject"),
                            "from": from_name,
                            "from_email": from_addr,
                            "date": email.get("receivedDateTime"),
                            "importance": email.get("importance"),
                            "preview": email.get("bodyPreview", "")[:100],
                            "sender_rank": rank if rank < 999 else None,
                            "priority_score": score,
                        }
                    )

            # Sort by priority score and take top items
            scored_emails.sort(key=lambda x: x["priority_score"])
            result["priority_emails"] = scored_emails[:max_items_per_category]

            # Flag very high priority emails as urgent
            for email in scored_emails[:3]:
                if email.get("sender_rank") and email["sender_rank"] <= 5:
                    result["urgent"].append(
                        {
                            "type": "vip_email",
                            "subject": email["subject"],
                            "from": email["from"],
                            "sender_rank": email["sender_rank"],
                        }
                    )

            result["total_unread"] = len(emails.get("value", []))
            result["sources_status"]["emails"] = "success"
        except Exception as e:
            result["sources_status"]["emails"] = f"failed: {str(e)[:50]}"

    # === TASKS - DUE TODAY OR OVERDUE ===
    if include_tasks:
        try:
            # Get task lists
            lists = client.get("/me/todo/lists", params={"$top": 10})
            all_tasks = []

            for task_list in lists.get("value", []):
                list_id = task_list.get("id")
                list_name = task_list.get("displayName")

                try:
                    tasks = client.get(
                        f"/me/todo/lists/{list_id}/tasks",
                        params={
                            "$filter": "status ne 'completed'",
                            "$top": 20,
                            "$select": "id,title,dueDateTime,importance,status",
                        },
                    )

                    for task in tasks.get("value", []):
                        due = task.get("dueDateTime", {})
                        due_date = due.get("dateTime")

                        task_info = {
                            "id": task.get("id"),
                            "title": task.get("title"),
                            "list": list_name,
                            "due_date": due_date,
                            "importance": task.get("importance"),
                            "status": task.get("status"),
                        }

                        # Check if due today or overdue
                        if due_date:
                            due_dt = datetime.fromisoformat(
                                due_date.replace("Z", "+00:00")
                            )
                            if due_dt.date() <= now.date():
                                is_overdue = due_dt.date() < now.date()
                                task_info["is_overdue"] = is_overdue
                                all_tasks.append(task_info)

                                if is_overdue:
                                    result["urgent"].append(
                                        {
                                            "type": "overdue_task",
                                            "title": task.get("title"),
                                            "due_date": due_date,
                                            "list": list_name,
                                        }
                                    )
                except Exception:
                    continue

            # Sort: overdue first, then by importance
            all_tasks.sort(
                key=lambda x: (
                    not x.get("is_overdue", False),
                    x.get("importance") != "high",
                )
            )
            result["tasks_due"] = all_tasks[:max_items_per_category]
            result["sources_status"]["tasks"] = "success"
        except Exception as e:
            result["sources_status"]["tasks"] = f"failed: {str(e)[:50]}"

    # === GENERATE FOCUS SUGGESTIONS ===
    suggestions = []

    if result["urgent"]:
        suggestions.append(f"Address {len(result['urgent'])} urgent items first")

    if result["meetings_today"]:
        next_meeting = result["meetings_today"][0]
        suggestions.append(f"Prepare for {next_meeting['subject']} starting soon")

    if result.get("priority_emails"):
        vip_count = sum(
            1 for e in result["priority_emails"] if e.get("sender_rank", 999) <= 5
        )
        if vip_count:
            suggestions.append(f"Respond to {vip_count} emails from top contacts")

    if result.get("tasks_due"):
        overdue_count = sum(1 for t in result["tasks_due"] if t.get("is_overdue"))
        if overdue_count:
            suggestions.append(f"Clear {overdue_count} overdue tasks")

    if not suggestions:
        suggestions.append("No urgent items - focus on strategic work!")

    result["focus_suggestions"] = suggestions

    # === SUMMARY ===
    emit_success(
        f"Daily focus: {len(result['urgent'])} urgent, "
        f"{len(result['meetings_today'])} meetings, "
        f"{len(result['priority_emails'])} priority emails"
    )

    return result


def register_msgraph_daily_focus(agent: Any) -> Tool:
    """Register the daily focus tool."""
    return agent.tool()(msgraph_daily_focus)


# =============================================================================
# SMART MEETING PREP
# =============================================================================


def msgraph_smart_meeting_prep(
    ctx: RunContext[Any],
    *,
    meeting_subject: str | None = None,
    event_id: str | None = None,
    hours_ahead: int = 24,
) -> dict:
    """Get comprehensive prep for an upcoming meeting.

    Gathers:
    1. Meeting details (attendees, agenda, join link)
    2. Recent email threads with attendees
    3. Related documents (by subject search)
    4. Attendee relationship data (how often you interact)
    5. Previous meetings with same subject

    Args:
        meeting_subject: Search for meeting by subject (partial match).
        event_id: Or provide specific event ID.
        hours_ahead: Look for meetings within this many hours (default 24).

    Returns:
        Dict with comprehensive meeting prep data.
    """
    if not meeting_subject and not event_id:
        return {
            "success": False,
            "error": "Must provide either meeting_subject or event_id",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\U0001f4cb [bold cyan]Preparing for meeting: {meeting_subject or event_id}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Find the meeting
        if event_id:
            event = client.get(
                f"/me/events/{event_id}",
                params={
                    "$select": "id,subject,start,end,organizer,attendees,body,location,isOnlineMeeting,onlineMeeting,importance",
                },
            )
        else:
            now = datetime.now(timezone.utc)
            end_time = now + timedelta(hours=hours_ahead)

            events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": now.isoformat(),
                    "endDateTime": end_time.isoformat(),
                    "$filter": f"contains(subject, '{meeting_subject}')",
                    "$select": "id,subject,start,end,organizer,attendees,body,location,isOnlineMeeting,onlineMeeting,importance",
                    "$orderby": "start/dateTime",
                    "$top": 1,
                },
            )

            if not events.get("value"):
                return {
                    "success": False,
                    "error": f"No meeting found matching '{meeting_subject}' in next {hours_ahead} hours",
                }

            event = events["value"][0]

        # Build meeting context
        result = {
            "success": True,
            "meeting": {
                "id": event.get("id"),
                "subject": event.get("subject"),
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "location": event.get("location", {}).get("displayName"),
                "is_online": event.get("isOnlineMeeting"),
                "join_url": event.get("onlineMeeting", {}).get("joinUrl"),
                "importance": event.get("importance"),
                "agenda": event.get("body", {}).get("content", "")[:500],
            },
            "organizer": {
                "name": event.get("organizer", {}).get("emailAddress", {}).get("name"),
                "email": event.get("organizer", {})
                .get("emailAddress", {})
                .get("address"),
            },
            "attendees": [],
            "recent_threads": [],
            "related_files": [],
            "previous_meetings": [],
        }

        # Process attendees
        attendee_emails = []
        for attendee in event.get("attendees", []):
            email_info = attendee.get("emailAddress", {})
            email = email_info.get("address", "")
            attendee_emails.append(email)

            result["attendees"].append(
                {
                    "name": email_info.get("name"),
                    "email": email,
                    "type": attendee.get("type"),
                    "response": attendee.get("status", {}).get("response"),
                }
            )

        # Get recent email threads with attendees
        if attendee_emails:
            try:
                # Search for emails from/to attendees about meeting subject
                subject_words = event.get("subject", "").split()[:3]  # First 3 words
                search_query = " ".join(subject_words)

                threads = client.get(
                    "/me/messages",
                    params={
                        "$search": f'"{search_query}"',
                        "$top": 5,
                        "$select": "id,subject,from,receivedDateTime,bodyPreview",
                        "$orderby": "receivedDateTime desc",
                    },
                )

                for msg in threads.get("value", []):
                    result["recent_threads"].append(
                        {
                            "subject": msg.get("subject"),
                            "from": msg.get("from", {})
                            .get("emailAddress", {})
                            .get("name"),
                            "date": msg.get("receivedDateTime"),
                            "preview": msg.get("bodyPreview", "")[:100],
                        }
                    )
            except Exception:
                pass

        # Search for related files
        try:
            subject_words = event.get("subject", "").split()[:3]
            file_query = " ".join(subject_words)

            files = client.get(
                f"/me/drive/search(q='{file_query.replace(chr(39), chr(39) + chr(39))}')",
                params={
                    "$top": 5,
                    "$select": "id,name,webUrl,lastModifiedDateTime",
                },
            )

            for f in files.get("value", []):
                result["related_files"].append(
                    {
                        "name": f.get("name"),
                        "url": f.get("webUrl"),
                        "modified": f.get("lastModifiedDateTime"),
                    }
                )
        except Exception:
            pass

        # Find previous meetings with same subject
        try:
            now = datetime.now(timezone.utc)
            past_start = now - timedelta(days=90)

            past_events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": past_start.isoformat(),
                    "endDateTime": now.isoformat(),
                    "$filter": f"contains(subject, '{event.get('subject', '')[:30]}')",
                    "$select": "id,subject,start",
                    "$orderby": "start/dateTime desc",
                    "$top": 5,
                },
            )

            for past_event in past_events.get("value", []):
                if past_event.get("id") != event.get("id"):
                    result["previous_meetings"].append(
                        {
                            "subject": past_event.get("subject"),
                            "date": past_event.get("start", {}).get("dateTime"),
                        }
                    )
        except Exception:
            pass

        emit_success(
            f"Meeting prep ready: {len(result['attendees'])} attendees, "
            f"{len(result['recent_threads'])} threads, {len(result['related_files'])} files"
        )

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_smart_meeting_prep(agent: Any) -> Tool:
    """Register the smart meeting prep tool."""
    return agent.tool()(msgraph_smart_meeting_prep)
