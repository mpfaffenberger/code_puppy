"""Quick Actions for Fast EA-Style Responses.

This module provides fast, relationship-aware action tools:
- Quick acknowledgment ("Got it, will review")
- Suggest response (draft based on context)
- Quick calendar response (accept/decline with note)
- Quick delegate (forward with context)

Design Principles:
- NEVER auto-send without explicit confirmation
- All tools return drafts by default
- Relationship-aware tone adjustment
- Input validation before any API call
- Clear preview of what will be sent
"""

from datetime import datetime, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# QUICK ACKNOWLEDGE
# =============================================================================


def msgraph_quick_acknowledge(
    ctx: RunContext[Any],
    *,
    email_id: str,
    acknowledgment_type: str = "received",
    custom_message: str | None = None,
    send: bool = False,
) -> dict:
    """Send a quick acknowledgment to an email.

    Generates and optionally sends a brief acknowledgment appropriate
    for the sender's relationship to you.

    Args:
        email_id: ID of the email to acknowledge.
        acknowledgment_type: Type of acknowledgment:
            - "received": "Thanks, got it!"
            - "reviewing": "Thanks, I'll review and get back to you."
            - "noted": "Noted, thanks for sharing."
            - "will_follow_up": "Thanks, I'll follow up on this."
        custom_message: Optional custom message (overrides type).
        send: If True, actually send. Default False (preview only).

    Returns:
        Dict with the acknowledgment draft and send status.
    """
    if not email_id or not email_id.strip():
        return {
            "success": False,
            "error": "email_id cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\u2705 [bold cyan]Preparing acknowledgment...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Get the original email
        email = client.get(
            f"/me/messages/{email_id}",
            params={"$select": "id,subject,from,conversationId"},
        )

        from_info = email.get("from", {}).get("emailAddress", {})
        from_name = from_info.get("name", "there")
        from_email = from_info.get("address", "")
        subject = email.get("subject", "")

        # Get relationship context to adjust tone
        relationship_type = "unknown"
        try:
            # Check if sender is manager
            manager = client.get("/me/manager", params={"$select": "mail"})
            if manager.get("mail", "").lower() == from_email.lower():
                relationship_type = "manager"
        except Exception:
            pass

        if relationship_type == "unknown":
            # Check People API for relevance
            try:
                people = client.get(
                    "/me/people",
                    params={"$top": 20, "$select": "emailAddresses"},
                )
                for idx, person in enumerate(people.get("value", [])):
                    emails = [
                        e.get("address", "").lower()
                        for e in person.get("emailAddresses", [])
                    ]
                    if from_email.lower() in emails:
                        if idx < 5:
                            relationship_type = "vip"
                        elif idx < 15:
                            relationship_type = "collaborator"
                        else:
                            relationship_type = "contact"
                        break
            except Exception:
                pass

        # Generate acknowledgment based on type and relationship
        acknowledgments = {
            "received": {
                "manager": f"Thanks {from_name.split()[0]}, got it!",
                "vip": f"Thanks {from_name.split()[0]}, received!",
                "default": "Thanks, got it!",
            },
            "reviewing": {
                "manager": f"Thanks {from_name.split()[0]}, I'll review this and get back to you.",
                "vip": f"Thanks {from_name.split()[0]}, I'll review and follow up.",
                "default": "Thanks, I'll review and get back to you.",
            },
            "noted": {
                "manager": f"Noted, thanks for sharing {from_name.split()[0]}.",
                "vip": "Noted, thanks for sharing.",
                "default": "Noted, thanks for sharing.",
            },
            "will_follow_up": {
                "manager": f"Thanks {from_name.split()[0]}, I'll follow up on this.",
                "vip": f"Thanks {from_name.split()[0]}, I'll take care of this.",
                "default": "Thanks, I'll follow up on this.",
            },
        }

        if custom_message:
            body = custom_message
        else:
            ack_options = acknowledgments.get(
                acknowledgment_type, acknowledgments["received"]
            )
            if relationship_type in ack_options:
                body = ack_options[relationship_type]
            else:
                body = ack_options["default"]

        result = {
            "success": True,
            "mode": "sent" if send else "preview",
            "original_email": {
                "id": email_id,
                "subject": subject,
                "from": from_name,
                "from_email": from_email,
            },
            "relationship_detected": relationship_type,
            "reply": {
                "to": from_email,
                "subject": f"RE: {subject}",
                "body": body,
            },
        }

        if send:
            # Actually send the reply
            client.post(
                f"/me/messages/{email_id}/reply",
                json={
                    "message": {
                        "body": {
                            "contentType": "text",
                            "content": body,
                        },
                    },
                },
            )
            result["sent"] = True
            emit_success(f"Acknowledgment sent to {from_name}")
        else:
            result["sent"] = False
            emit_warning("Preview only - set send=True to actually send")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_quick_acknowledge(agent: Any) -> Tool:
    """Register the quick acknowledge tool."""
    return agent.tool()(msgraph_quick_acknowledge)


# =============================================================================
# SUGGEST RESPONSE
# =============================================================================


def msgraph_suggest_response(
    ctx: RunContext[Any],
    *,
    email_id: str,
    intent: str,
    additional_context: str | None = None,
) -> dict:
    """Generate a suggested response based on email content and relationship.

    Analyzes the email and your relationship with the sender to suggest
    an appropriate response. Returns a draft for review - never auto-sends.

    Args:
        email_id: ID of the email to respond to.
        intent: What you want to communicate:
            - "accept": Accept a proposal/invitation
            - "decline": Politely decline
            - "clarify": Ask for clarification
            - "delegate": Redirect to someone else
            - "defer": Delay response/action
            - "thank": Express appreciation
            - "update": Provide an update
            - "custom": Use additional_context for guidance
        additional_context: Extra context for the response.

    Returns:
        Dict with suggested response, relationship context, and guidance.
    """
    if not email_id or not email_id.strip():
        return {
            "success": False,
            "error": "email_id cannot be empty",
        }

    if not intent or not intent.strip():
        return {
            "success": False,
            "error": "intent cannot be empty",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\u270d\ufe0f [bold cyan]Generating response suggestion: {intent}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Get the original email with full body
        email = client.get(
            f"/me/messages/{email_id}",
            params={
                "$select": "id,subject,from,body,receivedDateTime,importance,toRecipients,ccRecipients"
            },
        )

        from_info = email.get("from", {}).get("emailAddress", {})
        from_name = from_info.get("name", "there")
        from_email = from_info.get("address", "")
        subject = email.get("subject", "")
        body_content = email.get("body", {}).get("content", "")[
            :1000
        ]  # Limit for analysis
        importance = email.get("importance", "normal")

        # Determine relationship
        relationship_type = "peer"
        relationship_urgency = "normal"

        try:
            manager = client.get("/me/manager", params={"$select": "mail,displayName"})
            if manager.get("mail", "").lower() == from_email.lower():
                relationship_type = "manager"
                relationship_urgency = "high"
        except Exception:
            pass

        if relationship_type == "peer":
            try:
                people = client.get(
                    "/me/people",
                    params={"$top": 30, "$select": "emailAddresses"},
                )
                for idx, person in enumerate(people.get("value", [])):
                    emails = [
                        e.get("address", "").lower()
                        for e in person.get("emailAddresses", [])
                    ]
                    if from_email.lower() in emails:
                        if idx < 5:
                            relationship_type = "vip"
                            relationship_urgency = "high"
                        elif idx < 15:
                            relationship_type = "close_collaborator"
                            relationship_urgency = "medium"
                        break
            except Exception:
                pass

        # Generate response structure based on intent
        first_name = from_name.split()[0] if from_name else "there"

        intent_templates = {
            "accept": {
                "opening": f"Thanks {first_name},",
                "body": "I'd be happy to [accept/participate/help with this].",
                "closing": "Looking forward to it.",
                "tone_note": "Enthusiastic and positive",
            },
            "decline": {
                "opening": f"Thanks for thinking of me, {first_name}.",
                "body": "Unfortunately, I won't be able to [participate/attend/take this on] due to [brief reason].",
                "closing": "I hope it goes well, and please keep me in mind for future opportunities.",
                "tone_note": "Gracious but firm",
            },
            "clarify": {
                "opening": f"Thanks {first_name},",
                "body": "Before I proceed, I wanted to clarify a few things:\n- [Question 1]\n- [Question 2]",
                "closing": "Once I have this context, I can move forward.",
                "tone_note": "Curious and constructive",
            },
            "delegate": {
                "opening": f"Thanks for reaching out, {first_name}.",
                "body": "I think [Person Name] would be better positioned to help with this. I'm CC'ing them here.",
                "closing": "[Person] - can you take a look at this?",
                "tone_note": "Helpful redirect",
            },
            "defer": {
                "opening": f"Thanks {first_name},",
                "body": "I'd like to give this proper attention. Can we revisit this [timeframe - next week/after the holidays]?",
                "closing": "I'll follow up then.",
                "tone_note": "Respectful delay",
            },
            "thank": {
                "opening": f"Hi {first_name},",
                "body": "Just wanted to say thank you for [specific thing]. I really appreciate [impact/value].",
                "closing": "Thanks again!",
                "tone_note": "Warm and genuine",
            },
            "update": {
                "opening": f"Hi {first_name},",
                "body": "Quick update on [topic]:\n\n[Key update points]\n\nNext steps: [what's happening next]",
                "closing": "Let me know if you have questions.",
                "tone_note": "Clear and informative",
            },
            "custom": {
                "opening": f"Hi {first_name},",
                "body": additional_context or "[Your response here]",
                "closing": "Best,",
                "tone_note": "Customize based on context",
            },
        }

        template = intent_templates.get(intent, intent_templates["custom"])

        # Adjust for relationship
        if relationship_type == "manager":
            template["tone_adjustment"] = (
                "More formal, proactive, address concerns before they're raised"
            )
        elif relationship_type == "vip":
            template["tone_adjustment"] = "Prompt, professional, action-oriented"
        elif relationship_type == "close_collaborator":
            template["tone_adjustment"] = "Friendly but professional, collaborative"
        else:
            template["tone_adjustment"] = "Standard professional"

        result = {
            "success": True,
            "mode": "suggestion",
            "original_email": {
                "id": email_id,
                "subject": subject,
                "from": from_name,
                "from_email": from_email,
                "importance": importance,
                "preview": body_content[:200],
            },
            "relationship": {
                "type": relationship_type,
                "urgency": relationship_urgency,
            },
            "suggested_response": {
                "to": from_email,
                "subject": f"RE: {subject}",
                "structure": template,
                "draft": f"{template['opening']}\n\n{template['body']}\n\n{template['closing']}",
            },
            "guidance": {
                "intent": intent,
                "tone_note": template.get("tone_note"),
                "relationship_adjustment": template.get("tone_adjustment"),
                "additional_context": additional_context,
            },
            "next_steps": [
                "Review and customize the draft",
                "Use msgraph_send_mail or msgraph_reply_to_message to send",
            ],
        }

        emit_success(f"Response suggestion ready for {intent} intent")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_suggest_response(agent: Any) -> Tool:
    """Register the suggest response tool."""
    return agent.tool()(msgraph_suggest_response)


# =============================================================================
# QUICK CALENDAR ACTION
# =============================================================================


def msgraph_quick_calendar_action(
    ctx: RunContext[Any],
    *,
    event_id: str,
    action: str,
    message: str | None = None,
    propose_new_time: str | None = None,
    send: bool = False,
) -> dict:
    """Quickly respond to a calendar invitation.

    Args:
        event_id: ID of the calendar event.
        action: Action to take:
            - "accept": Accept the invitation
            - "tentative": Tentatively accept
            - "decline": Decline the invitation
        message: Optional message to include with response.
        propose_new_time: If declining, suggest alternative time (ISO format).
        send: If True, actually respond. Default False (preview only).

    Returns:
        Dict with action preview/result.
    """
    if not event_id or not event_id.strip():
        return {
            "success": False,
            "error": "event_id cannot be empty",
        }

    valid_actions = ["accept", "tentative", "decline"]
    if action not in valid_actions:
        return {
            "success": False,
            "error": f"action must be one of: {valid_actions}",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\U0001f4c5 [bold cyan]Calendar action: {action}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Get event details
        event = client.get(
            f"/me/events/{event_id}",
            params={"$select": "id,subject,start,end,organizer,responseStatus"},
        )

        organizer = event.get("organizer", {}).get("emailAddress", {})
        current_response = event.get("responseStatus", {}).get("response")

        # Generate appropriate message if not provided
        if not message:
            if action == "accept":
                message = "Thanks, I'll be there!"
            elif action == "tentative":
                message = "I'll try to make it, but may have a conflict."
            elif action == "decline":
                if propose_new_time:
                    message = f"Unfortunately I can't make this time. Would {propose_new_time} work instead?"
                else:
                    message = "Unfortunately I won't be able to attend. Apologies for the inconvenience."

        result = {
            "success": True,
            "mode": "sent" if send else "preview",
            "event": {
                "id": event_id,
                "subject": event.get("subject"),
                "start": event.get("start", {}).get("dateTime"),
                "end": event.get("end", {}).get("dateTime"),
                "organizer": organizer.get("name"),
                "organizer_email": organizer.get("address"),
                "current_response": current_response,
            },
            "action": {
                "type": action,
                "message": message,
                "propose_new_time": propose_new_time,
            },
        }

        if send:
            # Map action to Graph API endpoint
            action_endpoints = {
                "accept": "accept",
                "tentative": "tentativelyAccept",
                "decline": "decline",
            }

            endpoint = action_endpoints[action]
            request_body = {
                "sendResponse": True,
            }
            if message:
                request_body["comment"] = message

            client.post(
                f"/me/events/{event_id}/{endpoint}",
                json=request_body,
            )

            result["sent"] = True
            emit_success(f"Calendar response sent: {action}")
        else:
            result["sent"] = False
            emit_warning("Preview only - set send=True to actually respond")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_quick_calendar_action(agent: Any) -> Tool:
    """Register the quick calendar action tool."""
    return agent.tool()(msgraph_quick_calendar_action)


# =============================================================================
# QUICK DELEGATE
# =============================================================================


def msgraph_quick_delegate(
    ctx: RunContext[Any],
    *,
    email_id: str,
    delegate_to: str,
    context_for_delegate: str,
    cc_original_sender: bool = True,
    send: bool = False,
) -> dict:
    """Quickly delegate an email to someone else.

    Forwards the email with context and optionally CCs the original sender.

    Args:
        email_id: ID of the email to delegate.
        delegate_to: Email address of the person to delegate to.
        context_for_delegate: Context/instructions for the delegate.
        cc_original_sender: Whether to CC the original sender (default True).
        send: If True, actually send. Default False (preview only).

    Returns:
        Dict with delegation preview/result.
    """
    if not email_id or not email_id.strip():
        return {
            "success": False,
            "error": "email_id cannot be empty",
        }

    if not delegate_to or not delegate_to.strip():
        return {
            "success": False,
            "error": "delegate_to cannot be empty",
        }

    if not context_for_delegate or not context_for_delegate.strip():
        return {
            "success": False,
            "error": "context_for_delegate cannot be empty - please provide context for the delegate",
        }

    # Basic email validation
    if "@" not in delegate_to:
        return {
            "success": False,
            "error": "delegate_to must be a valid email address",
        }

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\U0001f4e4 [bold cyan]Preparing delegation to {delegate_to}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Get original email
        email = client.get(
            f"/me/messages/{email_id}",
            params={"$select": "id,subject,from,body,receivedDateTime"},
        )

        from_info = email.get("from", {}).get("emailAddress", {})
        original_sender = from_info.get("address", "")
        original_sender_name = from_info.get("name", "the sender")
        subject = email.get("subject", "")

        # Build forward message
        forward_body = f"{context_for_delegate}\n\n"
        forward_body += (
            f"---\nForwarded from {original_sender_name} ({original_sender})"
        )

        result = {
            "success": True,
            "mode": "sent" if send else "preview",
            "original_email": {
                "id": email_id,
                "subject": subject,
                "from": original_sender_name,
                "from_email": original_sender,
            },
            "delegation": {
                "to": delegate_to,
                "cc": original_sender if cc_original_sender else None,
                "subject": f"FW: {subject}",
                "context": context_for_delegate,
            },
        }

        if send:
            # Build recipients
            to_recipients = [{"emailAddress": {"address": delegate_to}}]
            cc_recipients = []
            if cc_original_sender and original_sender:
                cc_recipients.append({"emailAddress": {"address": original_sender}})

            # Forward the email
            client.post(
                f"/me/messages/{email_id}/forward",
                json={
                    "comment": context_for_delegate,
                    "toRecipients": to_recipients,
                },
            )

            result["sent"] = True
            emit_success(f"Delegated to {delegate_to}")
        else:
            result["sent"] = False
            emit_warning("Preview only - set send=True to actually delegate")

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_quick_delegate(agent: Any) -> Tool:
    """Register the quick delegate tool."""
    return agent.tool()(msgraph_quick_delegate)


# =============================================================================
# PROACTIVE SUGGESTIONS
# =============================================================================


def msgraph_proactive_suggestions(
    ctx: RunContext[Any],
) -> dict:
    """Generate proactive suggestions based on current context.

    Analyzes time of day, calendar, inbox, and relationships to suggest
    actions the user should consider taking.

    Returns:
        Dict with prioritized suggestions and rationale.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f4a1 [bold cyan]Generating proactive suggestions...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    now = datetime.now(timezone.utc)
    hour = now.hour

    result = {
        "success": True,
        "generated_at": now.isoformat(),
        "suggestions": [],
        "context": {
            "time_of_day": "morning"
            if hour < 12
            else "afternoon"
            if hour < 17
            else "evening",
        },
    }

    # === CHECK PENDING MEETING RESPONSES ===
    try:
        # Look for events today that need response
        from datetime import timedelta

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        events = client.get(
            "/me/calendarView",
            params={
                "startDateTime": today_start.isoformat(),
                "endDateTime": today_end.isoformat(),
                "$select": "subject,start,responseStatus,organizer",
                "$top": 20,
            },
        )

        pending_responses = []
        for event in events.get("value", []):
            response = event.get("responseStatus", {}).get("response")
            if response in ["none", "notResponded"]:
                pending_responses.append(
                    {
                        "subject": event.get("subject"),
                        "start": event.get("start", {}).get("dateTime"),
                        "organizer": event.get("organizer", {})
                        .get("emailAddress", {})
                        .get("name"),
                    }
                )

        if pending_responses:
            result["suggestions"].append(
                {
                    "priority": "high",
                    "category": "calendar",
                    "action": f"Respond to {len(pending_responses)} meeting invitation(s)",
                    "details": pending_responses[:3],
                    "rationale": "Pending RSVPs - organizers are waiting for your response",
                }
            )
    except Exception:
        pass

    # === CHECK VIP UNREAD EMAILS ===
    try:
        # Get top contacts
        people = client.get(
            "/me/people",
            params={"$top": 10, "$select": "emailAddresses"},
        )
        vip_emails = set()
        for person in people.get("value", []):
            for email_obj in person.get("emailAddresses", []):
                vip_emails.add(email_obj.get("address", "").lower())

        # Check unread from VIPs
        unread = client.get(
            "/me/messages",
            params={
                "$filter": "isRead eq false",
                "$top": 50,
                "$select": "from,subject,receivedDateTime",
                "$orderby": "receivedDateTime desc",
            },
        )

        vip_unread = []
        for msg in unread.get("value", []):
            from_email = (
                msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
            )
            if from_email in vip_emails:
                vip_unread.append(
                    {
                        "from": msg.get("from", {}).get("emailAddress", {}).get("name"),
                        "subject": msg.get("subject"),
                    }
                )

        if vip_unread:
            result["suggestions"].append(
                {
                    "priority": "high",
                    "category": "email",
                    "action": f"Review {len(vip_unread)} unread email(s) from important contacts",
                    "details": vip_unread[:3],
                    "rationale": "These are from your most frequently contacted people",
                }
            )
    except Exception:
        pass

    # === TIME-BASED SUGGESTIONS ===
    if hour < 10:
        result["suggestions"].append(
            {
                "priority": "medium",
                "category": "productivity",
                "action": "Review today's calendar and prepare for first meeting",
                "rationale": "Morning prep sets up the day for success",
            }
        )
    elif hour >= 16:
        result["suggestions"].append(
            {
                "priority": "medium",
                "category": "productivity",
                "action": "Send end-of-day updates and prepare tomorrow's priorities",
                "rationale": "Good time to wrap up and plan ahead",
            }
        )

    # === CHECK HIGH UNREAD COUNT ===
    try:
        inbox = client.get(
            "/me/mailFolders/inbox", params={"$select": "unreadItemCount"}
        )
        unread_count = inbox.get("unreadItemCount", 0)

        if unread_count > 50:
            result["suggestions"].append(
                {
                    "priority": "medium",
                    "category": "email",
                    "action": f"Inbox triage recommended - {unread_count} unread emails",
                    "rationale": "High unread count can cause important messages to be missed",
                }
            )
    except Exception:
        pass

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    result["suggestions"].sort(key=lambda x: priority_order.get(x.get("priority"), 99))

    emit_success(f"Generated {len(result['suggestions'])} suggestions")

    return result


def register_msgraph_proactive_suggestions(agent: Any) -> Tool:
    """Register the proactive suggestions tool."""
    return agent.tool()(msgraph_proactive_suggestions)
