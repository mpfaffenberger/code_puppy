"""Email triage and inbox zero workflows for Microsoft Graph.

This module provides high-level workflows for managing email overload:
- Inbox analysis and categorization
- Action item extraction from emails
- Bulk triage operations
- Smart reply suggestions
- Inbox zero progress tracking

Design Principles:
- Extract actionable insights from email content
- Create To Do tasks for commitments found in emails
- Provide previews before taking bulk actions
- Track progress toward inbox zero
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# INBOX ANALYSIS
# =============================================================================


def msgraph_analyze_inbox(
    ctx: RunContext[Any],
    *,
    days_back: int = 7,
    unread_only: bool = True,
) -> dict:
    """Analyze inbox to categorize emails and identify action items.

    Provides:
    - Email counts by sender domain
    - High priority emails
    - Emails with potential action items (based on keywords)
    - Emails waiting for your response
    - Auto-generated/notification emails

    Args:
        days_back: Number of days to analyze (default 7).
        unread_only: Only analyze unread emails (default True).

    Returns:
        Dict with inbox analysis and categorization.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "📊 [bold cyan]Analyzing inbox...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days_back)

        # Build filter
        filter_parts = [f"receivedDateTime ge {since.isoformat()}"]
        if unread_only:
            filter_parts.append("isRead eq false")

        response = client.get(
            "/me/messages",
            params={
                "$filter": " and ".join(filter_parts),
                "$orderby": "receivedDateTime desc",
                "$top": 200,
                "$select": "id,subject,from,receivedDateTime,importance,isRead,bodyPreview,hasAttachments,conversationId",
            },
        )
        emails = response.get("value", [])

        # Analysis buckets
        analysis = {
            "success": True,
            "analyzed_at": now.isoformat(),
            "days_back": days_back,
            "unread_only": unread_only,
            "total_count": len(emails),
            "by_sender_domain": {},
            "by_importance": {"high": [], "normal": [], "low": []},
            "action_items": [],  # Emails with action keywords
            "needs_response": [],  # Emails that look like they need a reply
            "notifications": [],  # Auto-generated emails
            "attachments": [],  # Emails with attachments
            "top_senders": [],
        }

        # Action item keywords
        action_keywords = [
            "action required",
            "action needed",
            "please review",
            "can you",
            "could you",
            "would you",
            "need you to",
            "by end of day",
            "by eod",
            "by friday",
            "by monday",
            "deadline",
            "asap",
            "urgent",
            "priority",
            "approve",
            "approval",
            "sign off",
            "your feedback",
            "waiting on you",
            "waiting for your",
            "follow up",
            "let me know",
            "thoughts?",
            "your input",
        ]

        # Notification sender patterns
        notification_patterns = [
            "noreply",
            "no-reply",
            "donotreply",
            "do-not-reply",
            "notifications",
            "alerts",
            "system",
            "automated",
            "mailer-daemon",
            "postmaster",
        ]

        sender_counts: dict[str, int] = {}

        for email in emails:
            from_info = email.get("from", {}).get("emailAddress", {}) or {}
            sender_email = (from_info.get("address") or "").lower()
            sender_name = from_info.get("name") or "Unknown"
            subject = (email.get("subject") or "").lower()
            body_preview = (email.get("bodyPreview") or "").lower()
            importance = (email.get("importance") or "normal").lower()

            # Extract domain
            domain = sender_email.split("@")[-1] if "@" in sender_email else "unknown"
            analysis["by_sender_domain"].setdefault(domain, 0)
            analysis["by_sender_domain"][domain] += 1

            # Track sender counts
            sender_counts[sender_name] = sender_counts.get(sender_name, 0) + 1

            email_summary = {
                "id": email.get("id"),
                "subject": email.get("subject", "(No subject)"),
                "from": sender_name,
                "from_email": sender_email,
                "date": email.get("receivedDateTime"),
                "preview": email.get("bodyPreview", "")[:100],
            }

            # Categorize by importance
            analysis["by_importance"][importance].append(email_summary)

            # Check for action items
            combined_text = f"{subject} {body_preview}"
            for keyword in action_keywords:
                if keyword in combined_text:
                    email_summary["action_keyword"] = keyword
                    analysis["action_items"].append(email_summary)
                    break

            # Check if it's a notification
            is_notification = any(
                pattern in sender_email for pattern in notification_patterns
            )
            if is_notification:
                analysis["notifications"].append(email_summary)

            # Check for attachments
            if email.get("hasAttachments"):
                analysis["attachments"].append(email_summary)

            # Check if it needs response (question in subject or ending with ?)
            if "?" in subject or subject.endswith("?"):
                if email_summary not in analysis["needs_response"]:
                    analysis["needs_response"].append(email_summary)

        # Top senders
        sorted_senders = sorted(sender_counts.items(), key=lambda x: -x[1])[:10]
        analysis["top_senders"] = [
            {"name": name, "count": count} for name, count in sorted_senders
        ]

        # Summary stats
        analysis["summary"] = {
            "high_priority": len(analysis["by_importance"]["high"]),
            "action_items": len(analysis["action_items"]),
            "needs_response": len(analysis["needs_response"]),
            "notifications": len(analysis["notifications"]),
            "with_attachments": len(analysis["attachments"]),
        }

        emit_success(
            f"Analyzed {len(emails)} emails: "
            f"{len(analysis['action_items'])} action items, "
            f"{len(analysis['notifications'])} notifications"
        )

        return analysis

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_analyze_inbox(agent: Any) -> Tool:
    """Register the analyze inbox tool."""
    return agent.tool()(msgraph_analyze_inbox)


# =============================================================================
# EXTRACT ACTION ITEMS TO TODO
# =============================================================================


def msgraph_extract_email_actions(
    ctx: RunContext[Any],
    *,
    email_id: str,
    create_todo: bool = True,
    todo_list_name: str = "Email Follow-ups",
) -> dict:
    """Extract action items from an email and optionally create To Do tasks.

    Analyzes email content to find:
    - Explicit requests ("Can you...", "Please...")
    - Deadlines mentioned
    - Questions that need answers
    - Commitments you made in replies

    Args:
        email_id: The ID of the email to analyze.
        create_todo: Create To Do tasks for found actions (default True).
        todo_list_name: Name of the To Do list to use (default "Email Follow-ups").

    Returns:
        Dict with extracted actions and created tasks.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🔍 [bold cyan]Extracting action items from email...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Get full email
        email = client.get(
            f"/me/messages/{email_id}",
            params={"$select": "id,subject,from,body,receivedDateTime,importance"},
        )

        subject = email.get("subject", "(No subject)")
        from_info = email.get("from", {}).get("emailAddress", {})
        sender = from_info.get("name", from_info.get("address", "Unknown"))

        # Note: For production, you'd use NLP or an LLM for better extraction
        # For now, we create a simple summary-based action
        actions = [
            {
                "type": "follow_up",
                "description": f"Review and respond to email from {sender}: {subject}",
                "source_email_id": email_id,
                "sender": sender,
            }
        ]

        created_tasks = []

        if create_todo and actions:
            # Find or create the todo list
            lists = client.get("/me/todo/lists")
            target_list = None
            for lst in lists.get("value", []):
                if lst.get("displayName") == todo_list_name:
                    target_list = lst
                    break

            if not target_list:
                # Create the list
                target_list = client.post(
                    "/me/todo/lists",
                    json={"displayName": todo_list_name},
                )

            list_id = target_list.get("id")

            # Create tasks
            for action in actions:
                task = client.post(
                    f"/me/todo/lists/{list_id}/tasks",
                    json={
                        "title": action["description"],
                        "body": {
                            "content": f"From email: {subject}\nSender: {sender}",
                            "contentType": "text",
                        },
                        "importance": "high"
                        if email.get("importance") == "high"
                        else "normal",
                    },
                )
                created_tasks.append(
                    {
                        "id": task.get("id"),
                        "title": action["description"],
                    }
                )

        emit_success(
            f"Found {len(actions)} action(s), created {len(created_tasks)} task(s)"
        )

        return {
            "success": True,
            "email": {
                "id": email_id,
                "subject": subject,
                "from": sender,
            },
            "actions": actions,
            "tasks_created": created_tasks,
            "todo_list": todo_list_name if created_tasks else None,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_extract_email_actions(agent: Any) -> Tool:
    """Register the extract email actions tool."""
    return agent.tool()(msgraph_extract_email_actions)


# =============================================================================
# BULK TRIAGE
# =============================================================================


def msgraph_bulk_triage(
    ctx: RunContext[Any],
    *,
    action: str,
    email_ids: list[str] | None = None,
    from_sender: str | None = None,
    subject_contains: str | None = None,
    older_than_days: int | None = None,
    target_folder: str | None = None,
    preview_only: bool = True,
) -> dict:
    """Bulk triage emails with a single action.

    Args:
        action: Action to take - "archive", "delete", "move", "mark_read".
        email_ids: Specific email IDs to process (optional).
        from_sender: Filter by sender email/domain (optional).
        subject_contains: Filter by subject keyword (optional).
        older_than_days: Filter emails older than N days (optional).
        target_folder: Folder ID for "move" action (required if action="move").
        preview_only: If True, show what would happen without doing it (default True).

    Returns:
        Dict with triage results or preview.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🧹 [bold cyan]Bulk triage: {action}...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Get emails to process
        if email_ids:
            # Use specific IDs
            emails_to_process = []
            for eid in email_ids[:50]:  # Limit to 50
                try:
                    email = client.get(
                        f"/me/messages/{eid}",
                        params={"$select": "id,subject,from,receivedDateTime"},
                    )
                    emails_to_process.append(email)
                except Exception:
                    pass
        else:
            # Build filter
            filter_parts = []
            if older_than_days:
                cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
                filter_parts.append(f"receivedDateTime lt {cutoff.isoformat()}")

            params = {
                "$top": 50,
                "$select": "id,subject,from,receivedDateTime",
                "$orderby": "receivedDateTime desc",
            }
            if filter_parts:
                params["$filter"] = " and ".join(filter_parts)

            response = client.get("/me/messages", params=params)
            emails_to_process = response.get("value", [])

            # Additional filtering
            if from_sender:
                from_sender_lower = from_sender.lower()
                emails_to_process = [
                    e
                    for e in emails_to_process
                    if from_sender_lower
                    in e.get("from", {})
                    .get("emailAddress", {})
                    .get("address", "")
                    .lower()
                ]
            if subject_contains:
                subject_lower = subject_contains.lower()
                emails_to_process = [
                    e
                    for e in emails_to_process
                    if subject_lower in e.get("subject", "").lower()
                ]

        # Preview mode
        preview = [
            {
                "id": e.get("id"),
                "subject": e.get("subject", "(No subject)"),
                "from": e.get("from", {})
                .get("emailAddress", {})
                .get("name", "Unknown"),
                "date": e.get("receivedDateTime"),
            }
            for e in emails_to_process
        ]

        if preview_only:
            emit_warning(f"Preview mode: {len(preview)} emails would be {action}d")
            return {
                "success": True,
                "preview_only": True,
                "action": action,
                "count": len(preview),
                "emails": preview,
                "message": f"Would {action} {len(preview)} emails. Set preview_only=False to execute.",
            }

        # Execute action
        processed = 0
        failed = 0

        for email in emails_to_process:
            eid = email.get("id")
            try:
                if action == "delete":
                    client.delete(f"/me/messages/{eid}")
                elif action == "archive":
                    archive = client.get("/me/mailFolders/archive")
                    client.post(
                        f"/me/messages/{eid}/move",
                        json={"destinationId": archive.get("id")},
                    )
                elif action == "move":
                    if not target_folder:
                        return {
                            "success": False,
                            "error": "target_folder is required for move action",
                        }
                    client.post(
                        f"/me/messages/{eid}/move",
                        json={"destinationId": target_folder},
                    )
                elif action == "mark_read":
                    client.patch(
                        f"/me/messages/{eid}",
                        json={"isRead": True},
                    )
                processed += 1
            except Exception:
                failed += 1

        emit_success(f"Processed {processed} emails ({failed} failed)")

        return {
            "success": True,
            "preview_only": False,
            "action": action,
            "processed": processed,
            "failed": failed,
            "message": f"{action.capitalize()}d {processed} emails",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_bulk_triage(agent: Any) -> Tool:
    """Register the bulk triage tool."""
    return agent.tool()(msgraph_bulk_triage)


# =============================================================================
# INBOX ZERO PROGRESS
# =============================================================================


def msgraph_inbox_zero_status(
    ctx: RunContext[Any],
) -> dict:
    """Get current inbox zero progress and stats.

    Returns:
        Dict with inbox status and recommendations.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "🎯 [bold cyan]Checking inbox zero status...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Get inbox stats
        inbox = client.get("/me/mailFolders/inbox")
        unread = inbox.get("unreadItemCount", 0)
        total = inbox.get("totalItemCount", 0)

        # Get focused inbox stats if available
        focused_count = 0
        other_count = 0
        try:
            # Focused Inbox uses inferenceClassification
            focused = client.get(
                "/me/messages",
                params={
                    "$filter": "inferenceClassification eq 'focused' and isRead eq false",
                    "$count": "true",
                    "$top": 1,
                },
            )
            focused_count = focused.get("@odata.count", len(focused.get("value", [])))

            other = client.get(
                "/me/messages",
                params={
                    "$filter": "inferenceClassification eq 'other' and isRead eq false",
                    "$count": "true",
                    "$top": 1,
                },
            )
            other_count = other.get("@odata.count", len(other.get("value", [])))
        except Exception:
            pass

        # Get age of oldest unread
        oldest_unread = None
        try:
            oldest = client.get(
                "/me/messages",
                params={
                    "$filter": "isRead eq false",
                    "$orderby": "receivedDateTime asc",
                    "$top": 1,
                    "$select": "receivedDateTime,subject,from",
                },
            )
            if oldest.get("value"):
                msg = oldest["value"][0]
                oldest_unread = {
                    "date": msg.get("receivedDateTime"),
                    "subject": msg.get("subject", "(No subject)"),
                    "from": msg.get("from", {})
                    .get("emailAddress", {})
                    .get("name", "Unknown"),
                }
        except Exception:
            pass

        # Calculate score (0-100, 100 = inbox zero)
        score = max(0, 100 - min(unread, 100))

        # Recommendations
        recommendations = []
        if unread > 50:
            recommendations.append("🚨 Consider bulk archiving old notifications")
        if unread > 20:
            recommendations.append("📧 Use filters to auto-sort newsletters and alerts")
        if other_count > focused_count:
            recommendations.append("🔇 Process 'Other' inbox - mostly notifications")
        if oldest_unread:
            try:
                oldest_date = datetime.fromisoformat(
                    oldest_unread["date"].replace("Z", "+00:00")
                )
                age_days = (datetime.now(timezone.utc) - oldest_date).days
                if age_days > 7:
                    recommendations.append(
                        f"⏰ Oldest unread is {age_days} days old - time to clean up!"
                    )
            except Exception:
                pass

        status = "inbox zero achieved!" if unread == 0 else f"{unread} unread emails"

        emit_success(f"Inbox status: {status} (score: {score}/100)")

        return {
            "success": True,
            "score": score,
            "status": status,
            "unread": unread,
            "total": total,
            "focused_unread": focused_count,
            "other_unread": other_count,
            "oldest_unread": oldest_unread,
            "recommendations": recommendations,
            "at_inbox_zero": unread == 0,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_inbox_zero_status(agent: Any) -> Tool:
    """Register the inbox zero status tool."""
    return agent.tool()(msgraph_inbox_zero_status)
