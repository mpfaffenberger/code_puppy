"""Meeting management workflow tools for Microsoft Graph.

These tools provide high-level meeting automation:
- Email meeting attendees (bulk notify with filtering)
- Nudge non-responders to RSVP

Design Principles:
- Preview by default (safety first)
- Return structured data for chaining
- Require explicit email content (no bespoke templates)
- Track send/skip status
"""

from datetime import datetime, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# WORKFLOW: EMAIL MEETING ATTENDEES
# =============================================================================


def msgraph_email_meeting_attendees(
    ctx: RunContext[Any],
    *,
    email_subject: str,
    email_body: str,
    meeting_subject: str | None = None,
    event_id: str | None = None,
    cc_emails: list[str] | None = None,
    include_organizer: bool = False,
    preview_only: bool = True,
) -> dict:
    """Send an email to all attendees of a meeting.

    This workflow finds a meeting and sends a custom email to its attendees.
    Useful for: meeting prep reminders, follow-ups, material requests, etc.

    Args:
        ctx: The run context.
        email_subject: Subject line for the email (REQUIRED).
        email_body: Body content for the email (REQUIRED).
        meeting_subject: Search for meeting by subject (partial match).
        event_id: Direct event ID (if known).
        cc_emails: List of email addresses to CC on all emails.
        include_organizer: Include the meeting organizer in recipients (default False).
        preview_only: If True, preview without sending (default True).

    Returns:
        Dict with:
        - success: bool
        - meeting: Meeting details (id, subject, start)
        - recipients: List of {email, name} who will receive/received email
        - cc_recipients: List of CC email addresses
        - email: {subject, body} that will be/was sent
        - preview_only: Whether this was a preview
        - sent_count: Number of emails sent (0 if preview)
        - skipped: List of {email, reason} for skipped recipients

    Example:
        # Preview sending prep reminder
        msgraph_email_meeting_attendees(
            meeting_subject="Q4 Planning",
            email_subject="Please submit your slides",
            email_body="Hi, please send your slides by Friday EOD.",
            preview_only=True
        )

        # Send with CC to admin
        msgraph_email_meeting_attendees(
            meeting_subject="Trade Prep",
            email_subject="Materials needed for Monday",
            email_body="Please submit your deck updates.",
            cc_emails=["admin@company.com"],
            preview_only=False
        )
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f4e7 [bold cyan]Preparing to email meeting attendees...[/bold cyan]"
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
                "subject": email_subject,
                "body": email_body,
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
            if email == organizer_email and not include_organizer:
                result["skipped"].append({"email": email, "reason": "organizer"})
                continue

            result["recipients"].append({"email": email, "name": name})

        if not result["recipients"]:
            emit_warning("No recipients found for this meeting")
            return {
                "success": False,
                "error": "No recipients found for this meeting",
                "meeting": meeting_info,
                "skipped": result["skipped"],
            }

        # Step 3: Send or preview
        cc_count = len(result["cc_recipients"])
        cc_msg = f" (CC: {cc_count})" if cc_count > 0 else ""

        if preview_only:
            emit_success(
                f"Preview: {len(result['recipients'])} recipients{cc_msg} for "
                f"'{meeting_info['subject']}'"
            )
            result["message"] = (
                f"Preview mode: Would send to {len(result['recipients'])} "
                f"recipients{cc_msg}. Set preview_only=False to send."
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
                        "subject": email_subject,
                        "body": {
                            "contentType": "text",
                            "content": email_body,
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
            emit_success(f"Sent {sent} emails for '{meeting_info['subject']}'")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_email_meeting_attendees(agent: Any) -> Tool:
    """Register the email meeting attendees workflow tool."""
    return agent.tool()(msgraph_email_meeting_attendees)


# =============================================================================
# WORKFLOW: NUDGE NON-RESPONDERS
# =============================================================================


def msgraph_nudge_non_responders(
    ctx: RunContext[Any],
    *,
    email_subject: str,
    email_body: str,
    meeting_subject: str | None = None,
    event_id: str | None = None,
    include_tentative: bool = True,
    preview_only: bool = True,
) -> dict:
    """Send reminder emails to meeting attendees who haven't responded.

    This workflow finds attendees who haven't RSVP'd and sends them a reminder.

    Args:
        ctx: The run context.
        email_subject: Subject line for the reminder (REQUIRED).
        email_body: Body content for the reminder (REQUIRED).
        meeting_subject: Search for meeting by subject.
        event_id: Direct event ID.
        include_tentative: Also nudge tentative responders (default True).
        preview_only: Preview without sending (default True).

    Returns:
        Dict with:
        - success: bool
        - meeting: Meeting details
        - attendee_status: {accepted, declined, tentative, no_response} lists
        - will_send_to: Recipients who will receive/received the nudge
        - email: {subject, body}
        - preview_only: Whether this was a preview
        - sent_count: Number of emails sent

    Example:
        msgraph_nudge_non_responders(
            meeting_subject="Team Standup",
            email_subject="Please RSVP: Team Standup",
            email_body="Hi, please respond to the calendar invite.",
            preview_only=True
        )
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f514 [bold cyan]Finding non-responders...[/bold cyan]"
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
            "email": {
                "subject": email_subject,
                "body": email_body,
            },
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
        result["will_send_to"] = list(result["attendee_status"]["no_response"])
        if include_tentative:
            result["will_send_to"].extend(result["attendee_status"]["tentative"])

        if not result["will_send_to"]:
            result["message"] = "Everyone has responded! No nudges needed."
            emit_success("All attendees have responded - no nudges needed")
            return result

        # Send or preview
        if preview_only:
            emit_success(
                f"Preview: Would nudge {len(result['will_send_to'])} attendees"
            )
            result["message"] = (
                f"Preview mode: Would send to {len(result['will_send_to'])} "
                f"attendees. Set preview_only=False to send."
            )
        else:
            sent = 0
            for recipient in result["will_send_to"]:
                try:
                    client.post(
                        "/me/sendMail",
                        json={
                            "message": {
                                "subject": email_subject,
                                "body": {
                                    "contentType": "text",
                                    "content": email_body,
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
                        },
                    )
                    sent += 1
                except Exception:
                    pass

            result["sent_count"] = sent
            emit_success(f"Sent {sent} nudge emails")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_nudge_non_responders(agent: Any) -> Tool:
    """Register the nudge non-responders workflow tool."""
    return agent.tool()(msgraph_nudge_non_responders)
