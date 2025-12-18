"""Executive Assistant workflow tools for Microsoft Graph.

These tools provide high-level EA functionality that goes beyond simple API calls:
- 1:1 meeting preparation with your manager
- Daily standup summaries
- Performance review / self-eval preparation

Design Principles:
- Each workflow returns structured data that can be enriched by other sub-agents
- Extensibility points marked with # EXTENSIBILITY for Jira, Confluence, etc.
- Graceful degradation - partial data is better than failure
- Human-readable summaries alongside structured data

Future Integration Points:
- Jira: Completed tickets, sprint progress, blockers
- Confluence: Authored/edited docs, relevant wikis
- GitHub: PRs merged, code reviews completed
- Learning platforms: Courses completed, certifications
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# WORKFLOW: 1:1 PREP WITH MANAGER
# =============================================================================


def msgraph_prep_one_on_one(
    ctx: RunContext[Any],
    *,
    manager_email: str | None = None,
    days_lookback: int = 14,
    include_talking_points: bool = True,
) -> dict:
    """Prepare comprehensive context for a 1:1 meeting with your manager.

    Gathers:
    - Your manager's info (auto-detected if not provided)
    - Upcoming 1:1 meeting details
    - Recent email threads with your manager
    - Meetings you've had since last 1:1
    - Your completed tasks (from To Do)
    - Suggested talking points

    Args:
        ctx: The run context.
        manager_email: Manager's email (auto-detected from org chart if not provided).
        days_lookback: Days to look back for context (default 14).
        include_talking_points: Generate suggested talking points (default True).

    Returns:
        Dict with comprehensive 1:1 prep including context, emails, and talking points.

    # EXTENSIBILITY: Future versions can add:
    # - Jira: Tickets completed, current sprint progress, blockers
    # - Confluence: Docs you authored/edited
    # - GitHub: PRs merged, code reviews done
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "👔 [bold cyan]Preparing 1:1 context...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)
        lookback_date = now - timedelta(days=days_lookback)

        prep = {
            "success": True,
            "generated_at": now.isoformat(),
            "lookback_days": days_lookback,
            "manager": {},
            "next_one_on_one": None,
            "last_one_on_one": None,
            "email_threads": [],
            "my_meetings": [],
            "completed_tasks": [],
            "talking_points": [],
            "extensibility": {
                "jira_available": False,
                "confluence_available": False,
                "github_available": False,
            },
        }

        # Step 1: Get manager info
        if not manager_email:
            try:
                manager = client.get("/me/manager")
                manager_email = manager.get("mail") or manager.get("userPrincipalName")
                prep["manager"] = {
                    "name": manager.get("displayName", "Unknown"),
                    "email": manager_email,
                    "title": manager.get("jobTitle", ""),
                }
            except Exception:
                emit_warning("Could not auto-detect manager from org chart")
                return {
                    "success": False,
                    "error": "Could not detect manager. Please provide manager_email.",
                }
        else:
            try:
                manager = client.get(
                    f"/users/{manager_email}",
                    params={"$select": "displayName,mail,jobTitle"},
                )
                prep["manager"] = {
                    "name": manager.get("displayName", "Unknown"),
                    "email": manager_email,
                    "title": manager.get("jobTitle", ""),
                }
            except Exception:
                prep["manager"] = {"email": manager_email, "name": "Unknown"}

        # Step 2: Find upcoming 1:1 with manager
        try:
            future_events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": now.isoformat(),
                    "endDateTime": (now + timedelta(days=30)).isoformat(),
                    "$orderby": "start/dateTime",
                    "$top": 100,
                    "$select": "id,subject,start,end,attendees",
                },
            )
            for event in future_events.get("value", []):
                attendees = event.get("attendees", [])
                for att in attendees:
                    att_email = att.get("emailAddress", {}).get("address", "").lower()
                    if att_email == manager_email.lower():
                        # Check if it looks like a 1:1 (2 attendees or subject hints)
                        subject = event.get("subject", "").lower()
                        if len(attendees) <= 2 or "1:1" in subject or "1-1" in subject:
                            prep["next_one_on_one"] = {
                                "id": event.get("id"),
                                "subject": event.get("subject"),
                                "start": event.get("start", {}).get("dateTime"),
                                "end": event.get("end", {}).get("dateTime"),
                            }
                            break
                if prep["next_one_on_one"]:
                    break
        except Exception as e:
            emit_warning(f"Could not search for 1:1 meeting: {e}")

        # Step 3: Find last 1:1 (for context)
        try:
            past_events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": lookback_date.isoformat(),
                    "endDateTime": now.isoformat(),
                    "$orderby": "start/dateTime desc",
                    "$top": 100,
                    "$select": "id,subject,start,end,attendees",
                },
            )
            for event in past_events.get("value", []):
                attendees = event.get("attendees", [])
                for att in attendees:
                    att_email = att.get("emailAddress", {}).get("address", "").lower()
                    if att_email == manager_email.lower():
                        subject = event.get("subject", "").lower()
                        if len(attendees) <= 2 or "1:1" in subject or "1-1" in subject:
                            prep["last_one_on_one"] = {
                                "id": event.get("id"),
                                "subject": event.get("subject"),
                                "start": event.get("start", {}).get("dateTime"),
                            }
                            break
                if prep["last_one_on_one"]:
                    break
        except Exception:
            pass

        # Step 4: Get recent email threads with manager
        try:
            emails = client.get(
                "/me/messages",
                params={
                    "$filter": f"from/emailAddress/address eq '{manager_email}' or "
                    f"toRecipients/any(r: r/emailAddress/address eq '{manager_email}')",
                    "$orderby": "receivedDateTime desc",
                    "$top": 10,
                    "$select": "id,subject,from,receivedDateTime,bodyPreview",
                },
            )
            for msg in emails.get("value", []):
                prep["email_threads"].append(
                    {
                        "subject": msg.get("subject", "(No subject)"),
                        "from": msg.get("from", {})
                        .get("emailAddress", {})
                        .get("name", ""),
                        "date": msg.get("receivedDateTime"),
                        "preview": msg.get("bodyPreview", "")[:150],
                    }
                )
        except Exception as e:
            emit_warning(f"Could not fetch emails with manager: {e}")

        # Step 5: Get meetings I've attended since last 1:1
        since_date = (
            prep["last_one_on_one"]["start"]
            if prep["last_one_on_one"]
            else lookback_date.isoformat()
        )
        try:
            my_meetings = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": since_date,
                    "endDateTime": now.isoformat(),
                    "$top": 50,
                    "$select": "subject,start,organizer",
                    "$orderby": "start/dateTime desc",
                },
            )
            for mtg in my_meetings.get("value", [])[:20]:
                prep["my_meetings"].append(
                    {
                        "subject": mtg.get("subject", "(No subject)"),
                        "date": mtg.get("start", {}).get("dateTime"),
                        "organizer": mtg.get("organizer", {})
                        .get("emailAddress", {})
                        .get("name", ""),
                    }
                )
        except Exception:
            pass

        # Step 6: Get completed tasks from To Do
        try:
            todo_lists = client.get("/me/todo/lists")
            for lst in todo_lists.get("value", [])[:5]:
                list_id = lst.get("id")
                tasks = client.get(
                    f"/me/todo/lists/{list_id}/tasks",
                    params={
                        "$filter": "status eq 'completed'",
                        "$top": 20,
                        "$select": "title,completedDateTime",
                    },
                )
                for task in tasks.get("value", []):
                    completed_dt = task.get("completedDateTime", {})
                    if completed_dt:
                        prep["completed_tasks"].append(
                            {
                                "title": task.get("title", ""),
                                "completed": completed_dt.get("dateTime"),
                            }
                        )
        except Exception:
            pass

        # Step 7: Generate talking points
        if include_talking_points:
            points = []

            # Accomplishments
            if prep["completed_tasks"]:
                points.append(
                    f"✅ Completed {len(prep['completed_tasks'])} tasks since last 1:1"
                )

            # Key meetings
            if prep["my_meetings"]:
                unique_meetings = set(m["subject"] for m in prep["my_meetings"][:5])
                points.append(
                    f"📅 Key meetings: {', '.join(list(unique_meetings)[:3])}"
                )

            # Email follow-ups
            if prep["email_threads"]:
                points.append(
                    f"📧 {len(prep['email_threads'])} email threads to potentially discuss"
                )

            # Standard prompts
            points.extend(
                [
                    "🎯 Current priorities and any blockers",
                    "📈 Career development / growth opportunities",
                    "💬 Feedback (giving and receiving)",
                    "🔮 What's coming up that I should know about?",
                ]
            )

            # EXTENSIBILITY: Add Jira-based talking points
            # if jira_available:
            #     points.append(f"🎫 Completed {jira_tickets_count} Jira tickets")
            #     points.append(f"🚧 Current blockers: {blockers}")

            prep["talking_points"] = points

        emit_success(
            f"1:1 prep ready for meeting with {prep['manager'].get('name', 'manager')}"
        )
        return prep

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_prep_one_on_one(agent: Any) -> Tool:
    """Register the 1:1 prep workflow tool."""
    return agent.tool()(msgraph_prep_one_on_one)


# =============================================================================
# WORKFLOW: DAILY STANDUP PREP
# =============================================================================


def msgraph_standup_prep(
    ctx: RunContext[Any],
    *,
    include_yesterday: bool = True,
) -> dict:
    """Generate a daily standup summary: yesterday, today, blockers.

    Gathers:
    - What you did yesterday (meetings attended, emails sent, tasks completed)
    - What you're doing today (calendar + top tasks)
    - Blockers (overdue tasks, unanswered important emails)

    Args:
        ctx: The run context.
        include_yesterday: Include yesterday's activities (default True).

    Returns:
        Dict with standup-ready summary in "yesterday/today/blockers" format.

    # EXTENSIBILITY: Future versions can add:
    # - Jira: Tickets moved to Done, In Progress tickets, blocked tickets
    # - GitHub: PRs merged, PRs awaiting review
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🌅 [bold cyan]Generating standup prep...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        today_end = today_start + timedelta(days=1)

        standup = {
            "success": True,
            "generated_at": now.isoformat(),
            "yesterday": {
                "meetings": [],
                "emails_sent": 0,
                "tasks_completed": [],
                "summary": "",
            },
            "today": {
                "meetings": [],
                "tasks_due": [],
                "focus_time_hours": 0,
                "summary": "",
            },
            "blockers": [],
            "extensibility": {
                "jira_available": False,
                "github_available": False,
            },
        }

        # === YESTERDAY ===
        if include_yesterday:
            # Yesterday's meetings
            try:
                yesterday_events = client.get(
                    "/me/calendarView",
                    params={
                        "startDateTime": yesterday_start.isoformat(),
                        "endDateTime": today_start.isoformat(),
                        "$select": "subject,start,end",
                        "$orderby": "start/dateTime",
                    },
                )
                for event in yesterday_events.get("value", []):
                    standup["yesterday"]["meetings"].append(
                        event.get("subject", "(No subject)")
                    )
            except Exception:
                pass

            # Emails sent yesterday
            try:
                sent_folder = client.get(
                    "/me/mailFolders/sentItems/messages",
                    params={
                        "$filter": f"sentDateTime ge {yesterday_start.isoformat()}",
                        "$count": "true",
                        "$top": 1,
                    },
                )
                standup["yesterday"]["emails_sent"] = sent_folder.get(
                    "@odata.count", len(sent_folder.get("value", []))
                )
            except Exception:
                pass

            # Tasks completed yesterday
            try:
                todo_lists = client.get("/me/todo/lists", params={"$top": 5})
                for lst in todo_lists.get("value", []):
                    list_id = lst.get("id")
                    tasks = client.get(
                        f"/me/todo/lists/{list_id}/tasks",
                        params={
                            "$filter": "status eq 'completed'",
                            "$top": 10,
                            "$select": "title,completedDateTime",
                        },
                    )
                    for task in tasks.get("value", []):
                        completed_dt = task.get("completedDateTime", {})
                        if completed_dt:
                            dt_str = completed_dt.get("dateTime", "")
                            try:
                                dt = datetime.fromisoformat(
                                    dt_str.replace("Z", "+00:00")
                                )
                                if yesterday_start <= dt < today_start:
                                    standup["yesterday"]["tasks_completed"].append(
                                        task.get("title", "")
                                    )
                            except (ValueError, TypeError):
                                pass
            except Exception:
                pass

            # Build yesterday summary
            parts = []
            if standup["yesterday"]["meetings"]:
                parts.append(
                    f"Attended {len(standup['yesterday']['meetings'])} meetings"
                )
            if standup["yesterday"]["emails_sent"]:
                parts.append(f"Sent {standup['yesterday']['emails_sent']} emails")
            if standup["yesterday"]["tasks_completed"]:
                parts.append(
                    f"Completed {len(standup['yesterday']['tasks_completed'])} tasks"
                )
            standup["yesterday"]["summary"] = "; ".join(parts) if parts else "Light day"

        # === TODAY ===
        # Today's meetings
        try:
            today_events = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": today_start.isoformat(),
                    "endDateTime": today_end.isoformat(),
                    "$select": "subject,start,end,isAllDay",
                    "$orderby": "start/dateTime",
                },
            )
            total_meeting_minutes = 0
            for event in today_events.get("value", []):
                if not event.get("isAllDay"):
                    standup["today"]["meetings"].append(
                        {
                            "subject": event.get("subject", "(No subject)"),
                            "start": event.get("start", {}).get("dateTime"),
                        }
                    )
                    # Calculate meeting time
                    try:
                        start = datetime.fromisoformat(
                            event["start"]["dateTime"].replace("Z", "+00:00")
                        )
                        end = datetime.fromisoformat(
                            event["end"]["dateTime"].replace("Z", "+00:00")
                        )
                        total_meeting_minutes += (end - start).seconds // 60
                    except (KeyError, ValueError, TypeError):
                        pass

            # Estimate focus time (8 hours - meeting time)
            standup["today"]["focus_time_hours"] = round(
                max(0, 8 - (total_meeting_minutes / 60)), 1
            )
        except Exception:
            pass

        # Tasks due today
        try:
            todo_lists = client.get("/me/todo/lists", params={"$top": 5})
            for lst in todo_lists.get("value", []):
                list_id = lst.get("id")
                tasks = client.get(
                    f"/me/todo/lists/{list_id}/tasks",
                    params={
                        "$filter": "status ne 'completed'",
                        "$top": 20,
                        "$select": "title,dueDateTime,importance",
                    },
                )
                for task in tasks.get("value", []):
                    due = task.get("dueDateTime", {})
                    if due:
                        dt_str = due.get("dateTime", "")
                        try:
                            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            if dt.date() == now.date():
                                standup["today"]["tasks_due"].append(
                                    {
                                        "title": task.get("title", ""),
                                        "importance": task.get("importance", "normal"),
                                    }
                                )
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

        # Build today summary
        standup["today"]["summary"] = (
            f"{len(standup['today']['meetings'])} meetings, "
            f"~{standup['today']['focus_time_hours']}h focus time"
        )

        # === BLOCKERS ===
        # Overdue tasks
        try:
            todo_lists = client.get("/me/todo/lists", params={"$top": 5})
            for lst in todo_lists.get("value", []):
                list_id = lst.get("id")
                tasks = client.get(
                    f"/me/todo/lists/{list_id}/tasks",
                    params={
                        "$filter": "status ne 'completed'",
                        "$top": 20,
                        "$select": "title,dueDateTime",
                    },
                )
                for task in tasks.get("value", []):
                    due = task.get("dueDateTime", {})
                    if due:
                        dt_str = due.get("dateTime", "")
                        try:
                            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                            if dt < now:
                                standup["blockers"].append(
                                    f"⏰ Overdue: {task.get('title', 'Unknown task')}"
                                )
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

        # Unanswered important emails (high priority, unread)
        try:
            urgent = client.get(
                "/me/messages",
                params={
                    "$filter": "importance eq 'high' and isRead eq false",
                    "$top": 5,
                    "$select": "subject,from",
                },
            )
            for msg in urgent.get("value", []):
                sender = msg.get("from", {}).get("emailAddress", {}).get("name", "")
                standup["blockers"].append(
                    f"🚨 Urgent email from {sender}: {msg.get('subject', '')[:50]}"
                )
        except Exception:
            pass

        # Pending meeting responses
        try:
            pending = client.get(
                "/me/calendarView",
                params={
                    "startDateTime": now.isoformat(),
                    "endDateTime": (now + timedelta(days=2)).isoformat(),
                    "$filter": "responseStatus/response eq 'notResponded'",
                    "$top": 5,
                    "$select": "subject,start",
                },
            )
            for event in pending.get("value", []):
                standup["blockers"].append(
                    f"📅 Need to RSVP: {event.get('subject', '')[:40]}"
                )
        except Exception:
            pass

        # EXTENSIBILITY: Add Jira blockers
        # if jira_available:
        #     blocked_tickets = get_jira_blocked_tickets()
        #     for ticket in blocked_tickets:
        #         standup["blockers"].append(f"🎫 Blocked: {ticket.key} - {ticket.summary}")

        emit_success(
            f"Standup ready: {len(standup['today']['meetings'])} meetings today, "
            f"{len(standup['blockers'])} blockers"
        )
        return standup

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_standup_prep(agent: Any) -> Tool:
    """Register the standup prep workflow tool."""
    return agent.tool()(msgraph_standup_prep)


# =============================================================================
# WORKFLOW: PERFORMANCE SUMMARY (Self-Eval Prep)
# =============================================================================


def msgraph_performance_summary(
    ctx: RunContext[Any],
    *,
    days: int = 90,
    include_metrics: bool = True,
) -> dict:
    """Generate a performance summary for self-evaluation or review prep.

    Aggregates over the specified period:
    - Meetings organized vs attended
    - Emails sent (volume, recipients)
    - Tasks completed
    - Key collaborators (who you work with most)
    - Activity patterns

    Args:
        ctx: The run context.
        days: Number of days to analyze (default 90 for quarterly).
        include_metrics: Include quantitative metrics (default True).

    Returns:
        Dict with performance metrics and insights for self-eval.

    # EXTENSIBILITY: Future versions can add:
    # - Jira: Story points delivered, tickets by type, velocity
    # - Confluence: Docs authored, pages edited
    # - GitHub: PRs merged, lines of code, code review participation
    # - Learning: Courses completed, certifications earned
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📊 [bold cyan]Generating performance summary...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=days)

        # Get current user info
        me = client.get("/me", params={"$select": "displayName,jobTitle,department"})

        summary = {
            "success": True,
            "generated_at": now.isoformat(),
            "period": {
                "start": start_date.isoformat(),
                "end": now.isoformat(),
                "days": days,
            },
            "user": {
                "name": me.get("displayName", "Unknown"),
                "title": me.get("jobTitle", ""),
                "department": me.get("department", ""),
            },
            "meetings": {
                "total": 0,
                "organized": 0,
                "attended": 0,
                "hours": 0,
            },
            "email": {
                "sent": 0,
                "top_recipients": [],
            },
            "tasks": {
                "completed": 0,
            },
            "collaborators": [],
            "insights": [],
            "extensibility": {
                "jira_available": False,
                "confluence_available": False,
                "github_available": False,
            },
        }

        my_email = me.get("mail") or me.get("userPrincipalName", "").lower()

        # === MEETINGS ===
        if include_metrics:
            try:
                # Get all meetings in period (paginated)
                all_meetings = []
                events = client.get(
                    "/me/calendarView",
                    params={
                        "startDateTime": start_date.isoformat(),
                        "endDateTime": now.isoformat(),
                        "$top": 100,
                        "$select": "subject,start,end,organizer,isAllDay",
                    },
                )
                all_meetings.extend(events.get("value", []))

                # Follow pagination
                next_link = events.get("@odata.nextLink")
                page_count = 0
                while next_link and page_count < 10:
                    page_count += 1
                    # Extract relative path
                    if "graph.microsoft.com" in next_link:
                        next_path = next_link.split("graph.microsoft.com/v1.0")[1]
                    else:
                        next_path = next_link
                    more_events = client.get(next_path)
                    all_meetings.extend(more_events.get("value", []))
                    next_link = more_events.get("@odata.nextLink")

                total_minutes = 0
                organized = 0
                collaborator_counts: dict[str, int] = {}

                for event in all_meetings:
                    if event.get("isAllDay"):
                        continue

                    # Count as organized if I'm the organizer
                    org_email = (
                        event.get("organizer", {})
                        .get("emailAddress", {})
                        .get("address", "")
                        .lower()
                    )
                    if org_email == my_email:
                        organized += 1

                    # Track collaborators
                    if org_email and org_email != my_email:
                        org_name = (
                            event.get("organizer", {})
                            .get("emailAddress", {})
                            .get("name", org_email)
                        )
                        collaborator_counts[org_name] = (
                            collaborator_counts.get(org_name, 0) + 1
                        )

                    # Calculate duration
                    try:
                        start_dt = datetime.fromisoformat(
                            event["start"]["dateTime"].replace("Z", "+00:00")
                        )
                        end_dt = datetime.fromisoformat(
                            event["end"]["dateTime"].replace("Z", "+00:00")
                        )
                        total_minutes += (end_dt - start_dt).seconds // 60
                    except (KeyError, ValueError, TypeError):
                        pass

                summary["meetings"]["total"] = len(all_meetings)
                summary["meetings"]["organized"] = organized
                summary["meetings"]["attended"] = len(all_meetings) - organized
                summary["meetings"]["hours"] = round(total_minutes / 60, 1)

                # Top collaborators from meetings
                top_collabs = sorted(collaborator_counts.items(), key=lambda x: -x[1])[
                    :10
                ]
                summary["collaborators"] = [
                    {"name": name, "meetings": count} for name, count in top_collabs
                ]

            except Exception as e:
                emit_warning(f"Could not analyze meetings: {e}")

        # === EMAIL ===
        if include_metrics:
            try:
                # Count sent emails
                sent = client.get(
                    "/me/mailFolders/sentItems/messages",
                    params={
                        "$filter": f"sentDateTime ge {start_date.isoformat()}",
                        "$top": 200,
                        "$select": "toRecipients",
                    },
                )
                summary["email"]["sent"] = len(sent.get("value", []))

                # Track top recipients
                recipient_counts: dict[str, int] = {}
                for msg in sent.get("value", []):
                    for recip in msg.get("toRecipients", []):
                        name = recip.get("emailAddress", {}).get("name", "Unknown")
                        recipient_counts[name] = recipient_counts.get(name, 0) + 1

                top_recips = sorted(recipient_counts.items(), key=lambda x: -x[1])[:5]
                summary["email"]["top_recipients"] = [
                    {"name": name, "count": count} for name, count in top_recips
                ]

            except Exception as e:
                emit_warning(f"Could not analyze emails: {e}")

        # === TASKS ===
        if include_metrics:
            try:
                completed_count = 0
                todo_lists = client.get("/me/todo/lists", params={"$top": 10})
                for lst in todo_lists.get("value", []):
                    list_id = lst.get("id")
                    tasks = client.get(
                        f"/me/todo/lists/{list_id}/tasks",
                        params={
                            "$filter": "status eq 'completed'",
                            "$top": 100,
                            "$select": "completedDateTime",
                        },
                    )
                    for task in tasks.get("value", []):
                        completed_dt = task.get("completedDateTime", {})
                        if completed_dt:
                            dt_str = completed_dt.get("dateTime", "")
                            try:
                                dt = datetime.fromisoformat(
                                    dt_str.replace("Z", "+00:00")
                                )
                                if dt >= start_date:
                                    completed_count += 1
                            except (ValueError, TypeError):
                                pass

                summary["tasks"]["completed"] = completed_count
            except Exception:
                pass

        # === INSIGHTS ===
        insights = []

        # Meeting load
        if summary["meetings"]["total"] > 0:
            avg_meetings_per_week = summary["meetings"]["total"] / (days / 7)
            insights.append(
                f"📅 Averaged {avg_meetings_per_week:.1f} meetings/week "
                f"({summary['meetings']['hours']:.0f} hours total)"
            )

        # Leadership indicator
        if summary["meetings"]["organized"] > 0:
            org_pct = (
                summary["meetings"]["organized"] / summary["meetings"]["total"]
            ) * 100
            if org_pct > 30:
                insights.append(
                    f"🎯 Organized {org_pct:.0f}% of your meetings - strong initiative"
                )

        # Communication
        if summary["email"]["sent"] > 0:
            avg_emails_per_week = summary["email"]["sent"] / (days / 7)
            insights.append(f"📧 Sent ~{avg_emails_per_week:.0f} emails/week")

        # Task completion
        if summary["tasks"]["completed"] > 0:
            insights.append(
                f"✅ Completed {summary['tasks']['completed']} tasks in To Do"
            )

        # Collaboration
        if summary["collaborators"]:
            top_collab = summary["collaborators"][0]["name"]
            insights.append(f"🤝 Top collaborator: {top_collab}")

        # EXTENSIBILITY: Add Jira insights
        # if jira_available:
        #     insights.append(f"🎫 Delivered {story_points} story points")
        #     insights.append(f"🐛 Closed {bugs_closed} bugs")

        summary["insights"] = insights

        emit_success(
            f"Performance summary: {summary['meetings']['total']} meetings, "
            f"{summary['email']['sent']} emails, {summary['tasks']['completed']} tasks"
        )
        return summary

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_performance_summary(agent: Any) -> Tool:
    """Register the performance summary workflow tool."""
    return agent.tool()(msgraph_performance_summary)
