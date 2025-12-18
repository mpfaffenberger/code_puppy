"""Unified Context Workflow for cross-system information gathering.

This module provides high-level workflows that:
1. Gather context from MS Graph (email, calendar, files)
2. Optionally delegate to other agents (Jira, Confluence)
3. Synthesize results into actionable intelligence

Design Principles:
- Partial success is acceptable (one source failing shouldn't break everything)
- Each data source is queried independently
- Results include metadata about what succeeded/failed
- Graceful degradation when APIs aren't available
"""

from datetime import datetime, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# GATHER CONTEXT
# =============================================================================


def msgraph_gather_context(
    ctx: RunContext[Any],
    *,
    topic: str,
    days_back: int = 30,
    include_emails: bool = True,
    include_files: bool = True,
    include_events: bool = True,
    include_teams: bool = False,
    max_results_per_type: int = 10,
) -> dict:
    """Gather all context about a topic from MS Graph.

    Searches across multiple data sources and combines results.
    Handles partial failures gracefully - returns what succeeded.

    Args:
        topic: The topic to search for (e.g., "Platform Migration", "Q4 Planning").
        days_back: How far back to search (default 30 days).
        include_emails: Search emails (default True).
        include_files: Search files in OneDrive/SharePoint (default True).
        include_events: Search calendar events (default True).
        include_teams: Search Teams messages (default False - can be slow).
        max_results_per_type: Maximum results per data type (default 10).

    Returns:
        Dict with context from each source and synthesis metadata.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\U0001f50d [bold cyan]Gathering context: {topic}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    # Track what succeeded/failed
    results = {
        "success": True,
        "topic": topic,
        "gathered_at": datetime.now(timezone.utc).isoformat(),
        "sources": {},
        "sources_succeeded": [],
        "sources_failed": [],
        "total_items": 0,
    }

    # Note: days_back is available for future filtering if needed
    _ = days_back  # Currently using search which doesn't need date filter

    # === EMAILS ===
    if include_emails:
        try:
            email_response = client.get(
                "/me/messages",
                params={
                    "$search": f'"{topic}"',
                    "$top": max_results_per_type,
                    "$select": "id,subject,from,receivedDateTime,bodyPreview,importance",
                    "$orderby": "receivedDateTime desc",
                },
            )
            emails = [
                {
                    "id": m.get("id"),
                    "subject": m.get("subject"),
                    "from": m.get("from", {}).get("emailAddress", {}).get("name"),
                    "from_email": m.get("from", {})
                    .get("emailAddress", {})
                    .get("address"),
                    "date": m.get("receivedDateTime"),
                    "preview": m.get("bodyPreview", "")[:150],
                    "importance": m.get("importance"),
                }
                for m in email_response.get("value", [])
            ]
            results["sources"]["emails"] = {
                "count": len(emails),
                "items": emails,
            }
            results["sources_succeeded"].append("emails")
            results["total_items"] += len(emails)
        except Exception as e:
            results["sources"]["emails"] = {"error": str(e)}
            results["sources_failed"].append("emails")

    # === FILES ===
    if include_files:
        try:
            # Use search endpoint for files
            file_response = client.get(
                "/me/drive/search(q='{}')".format(topic.replace("'", "''")),
                params={
                    "$top": max_results_per_type,
                    "$select": "id,name,webUrl,lastModifiedDateTime,createdBy,size",
                },
            )
            files = [
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "web_url": f.get("webUrl"),
                    "last_modified": f.get("lastModifiedDateTime"),
                    "created_by": f.get("createdBy", {})
                    .get("user", {})
                    .get("displayName"),
                    "size": f.get("size"),
                }
                for f in file_response.get("value", [])
            ]
            results["sources"]["files"] = {
                "count": len(files),
                "items": files,
            }
            results["sources_succeeded"].append("files")
            results["total_items"] += len(files)
        except Exception as e:
            results["sources"]["files"] = {"error": str(e)}
            results["sources_failed"].append("files")

    # === CALENDAR EVENTS ===
    if include_events:
        try:
            # Search events by subject
            event_response = client.get(
                "/me/events",
                params={
                    "$filter": f"contains(subject, '{topic}')",
                    "$top": max_results_per_type,
                    "$select": "id,subject,start,end,organizer,attendees,location",
                    "$orderby": "start/dateTime desc",
                },
            )
            events = [
                {
                    "id": e.get("id"),
                    "subject": e.get("subject"),
                    "start": e.get("start", {}).get("dateTime"),
                    "end": e.get("end", {}).get("dateTime"),
                    "organizer": e.get("organizer", {})
                    .get("emailAddress", {})
                    .get("name"),
                    "location": e.get("location", {}).get("displayName"),
                    "attendee_count": len(e.get("attendees", [])),
                }
                for e in event_response.get("value", [])
            ]
            results["sources"]["events"] = {
                "count": len(events),
                "items": events,
            }
            results["sources_succeeded"].append("events")
            results["total_items"] += len(events)
        except Exception as e:
            results["sources"]["events"] = {"error": str(e)}
            results["sources_failed"].append("events")

    # === TEAMS MESSAGES (optional, can be slow) ===
    if include_teams:
        try:
            # Search recent chats for topic mentions
            # Note: This searches chat messages, not channel messages
            chats_response = client.get(
                "/me/chats",
                params={
                    "$top": 20,
                    "$expand": "lastMessagePreview",
                },
            )
            # Filter chats that mention the topic
            relevant_chats = []
            for chat in chats_response.get("value", []):
                preview = chat.get("lastMessagePreview", {})
                body = preview.get("body", {}).get("content", "")
                if topic.lower() in body.lower():
                    relevant_chats.append(
                        {
                            "id": chat.get("id"),
                            "topic": chat.get("topic"),
                            "chat_type": chat.get("chatType"),
                            "last_message": body[:150],
                            "last_updated": chat.get("lastUpdatedDateTime"),
                        }
                    )
                    if len(relevant_chats) >= max_results_per_type:
                        break

            results["sources"]["teams_chats"] = {
                "count": len(relevant_chats),
                "items": relevant_chats,
            }
            results["sources_succeeded"].append("teams_chats")
            results["total_items"] += len(relevant_chats)
        except Exception as e:
            results["sources"]["teams_chats"] = {"error": str(e)}
            results["sources_failed"].append("teams_chats")

    # === SYNTHESIS ===
    success_count = len(results["sources_succeeded"])
    fail_count = len(results["sources_failed"])

    if success_count == 0:
        results["success"] = False
        results["summary"] = "All sources failed to return data"
        emit_warning("All context sources failed")
    else:
        results["summary"] = (
            f"Found {results['total_items']} items across {success_count} sources"
        )
        if fail_count > 0:
            results["summary"] += f" ({fail_count} sources failed)"
            emit_warning(f"Partial success: {fail_count} sources failed")
        else:
            emit_success(
                f"Gathered {results['total_items']} items from {success_count} sources"
            )

    return results


def register_msgraph_gather_context(agent: Any) -> Tool:
    """Register the gather context tool."""
    return agent.tool()(msgraph_gather_context)


# =============================================================================
# PRIORITIZED INBOX SCAN
# =============================================================================


def msgraph_prioritized_inbox(
    ctx: RunContext[Any],
    *,
    top: int = 20,
) -> dict:
    """Get unread emails prioritized by sender importance.

    Combines inbox data with People API to rank emails by:
    1. Sender's relevance rank (from /me/people)
    2. Email importance flag
    3. Recency

    Args:
        top: Maximum emails to analyze (default 20).

    Returns:
        Dict with prioritized email list.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\u2b50 [bold cyan]Getting prioritized inbox...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Step 1: Get relevant people (for priority ranking)
        people_response = client.get(
            "/me/people",
            params={
                "$top": 100,
                "$select": "displayName,emailAddresses",
            },
        )
        # Build email -> rank mapping
        email_to_rank: dict[str, int] = {}
        for idx, person in enumerate(people_response.get("value", [])):
            for email_obj in person.get("emailAddresses", []):
                addr = email_obj.get("address", "").lower()
                if addr and addr not in email_to_rank:
                    email_to_rank[addr] = idx + 1

        # Step 2: Get unread emails
        emails_response = client.get(
            "/me/messages",
            params={
                "$filter": "isRead eq false",
                "$top": top,
                "$select": "id,subject,from,receivedDateTime,importance,bodyPreview",
                "$orderby": "receivedDateTime desc",
            },
        )

        # Step 3: Score and sort emails
        scored_emails = []
        for email in emails_response.get("value", []):
            from_addr = (
                email.get("from", {}).get("emailAddress", {}).get("address", "").lower()
            )
            from_name = (
                email.get("from", {}).get("emailAddress", {}).get("name", "Unknown")
            )

            # Calculate priority score (lower is more important)
            sender_rank = email_to_rank.get(from_addr, 999)
            importance_boost = -50 if email.get("importance") == "high" else 0
            priority_score = sender_rank + importance_boost

            # Determine priority tier
            if sender_rank <= 5:
                tier = "critical"
            elif sender_rank <= 15:
                tier = "high"
            elif sender_rank <= 30:
                tier = "medium"
            elif sender_rank <= 100:
                tier = "normal"
            else:
                tier = "low"

            scored_emails.append(
                {
                    "id": email.get("id"),
                    "subject": email.get("subject"),
                    "from": from_name,
                    "from_email": from_addr,
                    "date": email.get("receivedDateTime"),
                    "importance": email.get("importance"),
                    "preview": email.get("bodyPreview", "")[:100],
                    "sender_rank": sender_rank if sender_rank < 999 else None,
                    "priority_tier": tier,
                    "priority_score": priority_score,
                }
            )

        # Sort by priority score
        scored_emails.sort(key=lambda x: x["priority_score"])

        # Group by tier
        by_tier = {"critical": [], "high": [], "medium": [], "normal": [], "low": []}
        for email in scored_emails:
            by_tier[email["priority_tier"]].append(email)

        emit_success(
            f"Prioritized {len(scored_emails)} emails: "
            f"{len(by_tier['critical'])} critical, "
            f"{len(by_tier['high'])} high priority"
        )

        return {
            "success": True,
            "total": len(scored_emails),
            "by_priority": by_tier,
            "emails": scored_emails,
            "summary": {
                "critical": len(by_tier["critical"]),
                "high": len(by_tier["high"]),
                "medium": len(by_tier["medium"]),
                "normal": len(by_tier["normal"]),
                "low": len(by_tier["low"]),
            },
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_prioritized_inbox(agent: Any) -> Tool:
    """Register the prioritized inbox tool."""
    return agent.tool()(msgraph_prioritized_inbox)


# =============================================================================
# DRAFT RESPONSE
# =============================================================================


def msgraph_draft_response(
    ctx: RunContext[Any],
    *,
    email_id: str,
    intent: str,
    tone: str = "professional",
) -> dict:
    """Prepare context for drafting a response to an email.

    Does NOT send the email - just gathers context and suggests a structure.
    The LLM should use this context to draft the actual response.

    Args:
        email_id: ID of the email to respond to.
        intent: What you want to say (e.g., "accept the meeting", "decline politely",
                "ask for more details", "confirm receipt").
        tone: Desired tone - "professional", "friendly", "brief", "formal".

    Returns:
        Dict with email context and response structure suggestions.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\u270d\ufe0f [bold cyan]Preparing response context...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    try:
        # Get the original email
        email = client.get(
            f"/me/messages/{email_id}",
            params={
                "$select": "id,subject,from,toRecipients,ccRecipients,body,receivedDateTime,importance,conversationId",
            },
        )

        from_info = email.get("from", {}).get("emailAddress", {})
        body_content = email.get("body", {}).get("content", "")

        # Get conversation history if available
        conversation_id = email.get("conversationId")
        thread_context = []
        if conversation_id:
            try:
                thread = client.get(
                    "/me/messages",
                    params={
                        "$filter": f"conversationId eq '{conversation_id}'",
                        "$top": 5,
                        "$select": "subject,from,receivedDateTime,bodyPreview",
                        "$orderby": "receivedDateTime desc",
                    },
                )
                thread_context = [
                    {
                        "from": m.get("from", {}).get("emailAddress", {}).get("name"),
                        "date": m.get("receivedDateTime"),
                        "preview": m.get("bodyPreview", "")[:100],
                    }
                    for m in thread.get("value", [])
                ]
            except Exception:
                pass  # Thread context is optional

        # Build response structure based on intent
        intent_lower = intent.lower()
        if "accept" in intent_lower or "confirm" in intent_lower:
            suggested_structure = [
                "Thank them / acknowledge",
                "Confirm the specific item",
                "Add any relevant details",
                "Close warmly",
            ]
        elif "decline" in intent_lower:
            suggested_structure = [
                "Thank them for the opportunity/invitation",
                "Politely decline with brief reason (optional)",
                "Offer alternative if applicable",
                "Close positively",
            ]
        elif "ask" in intent_lower or "question" in intent_lower:
            suggested_structure = [
                "Reference the context",
                "State your question(s) clearly",
                "Provide any relevant background",
                "Thank them in advance",
            ]
        else:
            suggested_structure = [
                "Open with context/acknowledgment",
                "Main message content",
                "Any action items or next steps",
                "Close appropriately",
            ]

        emit_success("Response context prepared")

        return {
            "success": True,
            "original_email": {
                "id": email_id,
                "subject": email.get("subject"),
                "from_name": from_info.get("name"),
                "from_email": from_info.get("address"),
                "date": email.get("receivedDateTime"),
                "body_preview": body_content[:500] if body_content else "",
                "importance": email.get("importance"),
            },
            "thread_context": thread_context,
            "response_guidance": {
                "intent": intent,
                "tone": tone,
                "suggested_structure": suggested_structure,
                "reply_to": from_info.get("address"),
                "suggested_subject": f"RE: {email.get('subject', '')}",
            },
            "note": "Use this context to draft a response. Call msgraph_send_mail or msgraph_reply_to_message to send.",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_draft_response(agent: Any) -> Tool:
    """Register the draft response tool."""
    return agent.tool()(msgraph_draft_response)
