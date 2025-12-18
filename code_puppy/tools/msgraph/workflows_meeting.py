"""Meeting management workflow tools for Microsoft Graph.

These tools provide high-level meeting automation:
- Calls for content (remind presenters to submit materials)
- Meeting reminders (nudge non-responders)

Design Principles:
- Preview by default (safety first)
- Return structured data for chaining
- Support custom templates
- Track send/skip status
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# WORKFLOW: CALLS FOR CONTENT
# =============================================================================


def msgraph_calls_for_content(
    ctx: RunContext[Any],
    *,
    meeting_subject: str | None = None,
    event_id: str | None = None,
    days_before: int = 3,
    email_subject: str | None = None,
    email_body: str | None = None,
    cc_emails: list[str] | None = None,
    send_to_organizer: bool = False,
    send_to_all_attendees: bool = True,
    preview_only: bool = True,
) -> dict:
    """Send "Calls for Content" reminder emails to meeting attendees.

    This workflow automates the common pattern of reminding presenters
    to submit their materials before a meeting. It:
    1. Finds the meeting by subject or ID
    2. Gets the attendee list
    3. Generates or uses a custom email template
    4. Sends (or previews) the reminder emails

    Args:
        ctx: The run context.
        meeting_subject: Search for meeting by subject (partial match).
        event_id: Direct event ID (if known).
        days_before: Days before meeting to mention in email (default 3).
        email_subject: Custom email subject (uses template if not provided).
        email_body: Custom email body (uses template if not provided).
        cc_emails: List of email addresses to CC on all emails (e.g., support staff).
        send_to_organizer: Include the meeting organizer (default False).
        send_to_all_attendees: Send to all attendees (default True).
        preview_only: If True, preview emails without sending (default True).

    Returns:
        Dict with meeting info, recipient list, email content, and send status.

    Example:
        # Preview calls for content for Trade Prep meeting
        msgraph_calls_for_content(
            meeting_subject="Trade Prep",
            days_before=5,
            preview_only=True
        )

        # Send with custom message and CC support staff
        msgraph_calls_for_content(
            meeting_subject="Q4 Planning",
            email_body="Please submit your slides by EOD Friday.",
            cc_emails=["support@walmart.com"],
            preview_only=False
        )
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f4e2 [bold cyan]Preparing calls for content...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)

        result = {
            "success": True,
            "meeting": None,
            "recipients": [],
            "cc_recipients": cc_emails or [],
            "email": {
                "subject": None,
                "body": None,
            },
            "preview_only": preview_only,
            "sent_count": 0,
            "skipped": [],
        }

        # Step 1: Find the meeting
        event = None
        if event_id:
            try:
                event = client.get(
                    f"/me/events/{event_id}",
                    params={
                        "$select": "id,subject,start,end,location,attendees,organizer"
                    },
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Could not find event with ID {event_id}: {e}",
                }
        elif meeting_subject:
            # Search upcoming events
            events = client.get(
                "/me/events",
                params={
                    "$filter": f"start/dateTime ge '{now.isoformat()}'",
                    "$orderby": "start/dateTime",
                    "$top": 50,
                    "$select": "id,subject,start,end,location,attendees,organizer",
                },
            )
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
                "error": "Either meeting_subject or event_id must be provided",
            }

        # Parse meeting details
        meeting_info = {
            "id": event.get("id"),
            "subject": event.get("subject", "(No subject)"),
            "start": event.get("start", {}).get("dateTime"),
            "location": event.get("location", {}).get("displayName", ""),
        }
        result["meeting"] = meeting_info

        # Parse meeting date for email
        try:
            meeting_dt = datetime.fromisoformat(
                meeting_info["start"].replace("Z", "+00:00")
            )
            meeting_date_str = meeting_dt.strftime("%A, %B %d")
            deadline_dt = meeting_dt - timedelta(days=days_before)
            deadline_str = deadline_dt.strftime("%A, %B %d")
        except (ValueError, TypeError, AttributeError):
            meeting_date_str = "the upcoming meeting"
            deadline_str = f"{days_before} days before the meeting"

        # Step 2: Build recipient list
        organizer_email = (
            event.get("organizer", {})
            .get("emailAddress", {})
            .get("address", "")
            .lower()
        )
        attendees = event.get("attendees", [])

        for att in attendees:
            email_info = att.get("emailAddress", {})
            email = email_info.get("address", "").lower()
            name = email_info.get("name", email)

            # Skip organizer unless requested
            if email == organizer_email and not send_to_organizer:
                result["skipped"].append({"email": email, "reason": "organizer"})
                continue

            if send_to_all_attendees:
                result["recipients"].append({"email": email, "name": name})

        if not result["recipients"]:
            return {
                "success": False,
                "error": "No recipients found for this meeting",
                "meeting": meeting_info,
                "skipped": result["skipped"],
            }

        # Step 3: Build email content
        if email_subject:
            result["email"]["subject"] = email_subject
        else:
            result["email"]["subject"] = (
                f"\U0001f4cb Call for Content: {meeting_info['subject']}"
            )

        if email_body:
            result["email"]["body"] = email_body
        else:
            location = meeting_info["location"] or "See calendar invite"
            result["email"]["body"] = f"""Hi there,

This is a friendly reminder that you're invited to **{meeting_info["subject"]}** on **{meeting_date_str}**.

If you're presenting or have materials to share, please send them by **{deadline_str}** so we can compile the agenda.

**Meeting Details:**
- **When:** {meeting_date_str}
- **Where:** {location}

Please reply to this email with:
- Your presentation slides (if presenting)
- Any agenda items you'd like to add
- Topics you'd like to discuss

Thank you!

---
*This is an automated reminder from Code Puppy \U0001f436*
"""

        # Step 4: Send or preview
        cc_count = len(result["cc_recipients"])
        cc_msg = f" (CC: {cc_count})" if cc_count > 0 else ""

        if preview_only:
            emit_success(
                f"Preview ready: {len(result['recipients'])} recipients{cc_msg} for "
                f"'{meeting_info['subject']}'"
            )
            result["message"] = (
                f"Preview mode: Would send to {len(result['recipients'])} recipients{cc_msg}. "
                f"Set preview_only=False to send."
            )
        else:
            # Build CC recipients list
            cc_list = [
                {"emailAddress": {"address": cc_email}}
                for cc_email in (cc_emails or [])
            ]

            # Actually send the emails
            sent = 0
            for recipient in result["recipients"]:
                try:
                    message = {
                        "subject": result["email"]["subject"],
                        "body": {
                            "contentType": "text",
                            "content": result["email"]["body"],
                        },
                        "toRecipients": [
                            {
                                "emailAddress": {
                                    "address": recipient["email"],
                                    "name": recipient["name"],
                                }
                            }
                        ],
                    }

                    # Add CC if provided
                    if cc_list:
                        message["ccRecipients"] = cc_list

                    client.post("/me/sendMail", json={"message": message})
                    sent += 1
                except Exception as e:
                    result["skipped"].append(
                        {"email": recipient["email"], "reason": str(e)}
                    )

            result["sent_count"] = sent
            emit_success(
                f"Sent {sent} calls for content emails for '{meeting_info['subject']}'"
            )

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_calls_for_content(agent: Any) -> Tool:
    """Register the calls for content workflow tool."""
    return agent.tool()(msgraph_calls_for_content)


# =============================================================================
# WORKFLOW: MEETING REMINDER
# =============================================================================


def msgraph_send_meeting_reminder(
    ctx: RunContext[Any],
    *,
    meeting_subject: str | None = None,
    event_id: str | None = None,
    custom_message: str | None = None,
    include_non_responders_only: bool = False,
    preview_only: bool = True,
) -> dict:
    """Send reminder emails to meeting attendees who haven't responded.

    This workflow helps ensure meeting attendance by:
    1. Finding the meeting
    2. Checking RSVP status of each attendee
    3. Sending reminders to non-responders (or all attendees)

    Args:
        ctx: The run context.
        meeting_subject: Search for meeting by subject.
        event_id: Direct event ID.
        custom_message: Custom message to include in reminder.
        include_non_responders_only: Only send to those who haven't RSVP'd (default False).
        preview_only: Preview without sending (default True).

    Returns:
        Dict with attendee status and send results.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f514 [bold cyan]Preparing meeting reminder...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)

        result = {
            "success": True,
            "meeting": None,
            "attendee_status": {
                "accepted": [],
                "declined": [],
                "tentative": [],
                "no_response": [],
            },
            "will_send_to": [],
            "preview_only": preview_only,
            "sent_count": 0,
        }

        # Find the meeting
        event = None
        if event_id:
            event = client.get(
                f"/me/events/{event_id}",
                params={"$select": "id,subject,start,end,attendees,organizer"},
            )
        elif meeting_subject:
            events = client.get(
                "/me/events",
                params={
                    "$filter": f"start/dateTime ge '{now.isoformat()}'",
                    "$orderby": "start/dateTime",
                    "$top": 50,
                    "$select": "id,subject,start,end,attendees,organizer",
                },
            )
            subject_lower = meeting_subject.lower()
            for e in events.get("value", []):
                if subject_lower in e.get("subject", "").lower():
                    event = e
                    break
        else:
            return {
                "success": False,
                "error": "Either meeting_subject or event_id required",
            }

        if not event:
            return {
                "success": False,
                "error": f"No meeting found matching '{meeting_subject}'",
            }

        result["meeting"] = {
            "id": event.get("id"),
            "subject": event.get("subject"),
            "start": event.get("start", {}).get("dateTime"),
        }

        # Parse meeting date
        try:
            meeting_dt = datetime.fromisoformat(
                event["start"]["dateTime"].replace("Z", "+00:00")
            )
            meeting_date_str = meeting_dt.strftime("%A, %B %d at %I:%M %p")
        except (ValueError, TypeError, KeyError):
            meeting_date_str = "the scheduled time"

        # Categorize attendees by response
        for att in event.get("attendees", []):
            email_info = att.get("emailAddress", {})
            email = email_info.get("address", "")
            name = email_info.get("name", email)
            response = att.get("status", {}).get("response", "none")

            attendee_info = {"email": email, "name": name}

            if response == "accepted":
                result["attendee_status"]["accepted"].append(attendee_info)
            elif response == "declined":
                result["attendee_status"]["declined"].append(attendee_info)
            elif response == "tentativelyAccepted":
                result["attendee_status"]["tentative"].append(attendee_info)
            else:
                result["attendee_status"]["no_response"].append(attendee_info)

        # Determine who to send to
        if include_non_responders_only:
            result["will_send_to"] = result["attendee_status"]["no_response"]
        else:
            # Send to non-responders + tentative
            result["will_send_to"] = (
                result["attendee_status"]["no_response"]
                + result["attendee_status"]["tentative"]
            )

        if not result["will_send_to"]:
            result["message"] = "Everyone has responded! No reminders needed."
            emit_success("All attendees have responded - no reminders needed")
            return result

        # Build reminder email
        subject = f"\U0001f514 Reminder: {event.get('subject', 'Meeting')}"
        meeting_name = event.get("subject", "our upcoming meeting")
        body = f"""Hi,

This is a friendly reminder about **{meeting_name}** on **{meeting_date_str}**.

Please respond to the calendar invite to confirm your attendance.

"""
        if custom_message:
            body += f"{custom_message}\n\n"

        body += """Thank you!

---
*This is an automated reminder from Code Puppy \U0001f436*
"""

        result["email"] = {"subject": subject, "body": body}

        # Send or preview
        if preview_only:
            emit_success(
                f"Preview: Would remind {len(result['will_send_to'])} attendees"
            )
            result["message"] = (
                f"Preview mode: Would send to {len(result['will_send_to'])} attendees. "
                f"Set preview_only=False to send."
            )
        else:
            sent = 0
            for recipient in result["will_send_to"]:
                try:
                    client.post(
                        "/me/sendMail",
                        json={
                            "message": {
                                "subject": subject,
                                "body": {"contentType": "text", "content": body},
                                "toRecipients": [
                                    {
                                        "emailAddress": {
                                            "address": recipient["email"],
                                            "name": recipient["name"],
                                        }
                                    }
                                ],
                            }
                        },
                    )
                    sent += 1
                except Exception:
                    pass

            result["sent_count"] = sent
            emit_success(f"Sent {sent} reminder emails")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_send_meeting_reminder(agent: Any) -> Tool:
    """Register the meeting reminder workflow tool."""
    return agent.tool()(msgraph_send_meeting_reminder)
