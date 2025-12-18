"""Organizational Context and Relationship Intelligence.

This module provides tools for understanding:
- User's position in the org hierarchy
- Relationship context with specific people
- Relationship health and attention needed

Design Principles:
- Build comprehensive org context for relationship-aware responses
- Use multiple signals: org chart, People API, interaction history
- Enable different response styles for different relationships
- Proactively identify relationships needing attention
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# ORG CONTEXT
# =============================================================================


def msgraph_get_org_context(
    ctx: RunContext[Any],
) -> dict:
    """Get comprehensive org context for the current user.

    Gathers:
    - User's manager (and skip-level if available)
    - User's direct reports
    - Top collaborators with relevance scores
    - User's job title and department

    This context enables relationship-aware responses where the agent
    can adjust tone and urgency based on org relationships.

    Returns:
        Dict with complete org context including:
        - user: Current user's profile
        - manager: Direct manager info
        - skip_level: Manager's manager (if accessible)
        - direct_reports: List of direct reports
        - top_collaborators: Relevance-ranked collaborators
        - relationship_tiers: People grouped by priority tier
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\U0001f3e2 [bold cyan]Building org context...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    result = {
        "success": True,
        "user": None,
        "manager": None,
        "skip_level": None,
        "direct_reports": [],
        "top_collaborators": [],
        "relationship_tiers": {
            "critical": [],  # Manager, skip-level
            "high": [],  # Top 10 collaborators, direct reports
            "medium": [],  # 11-30 collaborators
            "normal": [],  # Others
        },
        "sources_status": {},
    }

    # === GET CURRENT USER ===
    try:
        me = client.get(
            "/me",
            params={
                "$select": "id,displayName,mail,jobTitle,department,officeLocation"
            },
        )
        result["user"] = {
            "id": me.get("id"),
            "name": me.get("displayName"),
            "email": me.get("mail"),
            "title": me.get("jobTitle"),
            "department": me.get("department"),
            "location": me.get("officeLocation"),
        }
        result["sources_status"]["user"] = "success"
    except Exception as e:
        result["sources_status"]["user"] = f"failed: {str(e)[:50]}"

    # === GET MANAGER ===
    try:
        manager = client.get(
            "/me/manager",
            params={"$select": "id,displayName,mail,jobTitle,department"},
        )
        manager_info = {
            "id": manager.get("id"),
            "name": manager.get("displayName"),
            "email": manager.get("mail"),
            "title": manager.get("jobTitle"),
            "department": manager.get("department"),
            "relationship": "manager",
        }
        result["manager"] = manager_info
        result["relationship_tiers"]["critical"].append(manager_info)
        result["sources_status"]["manager"] = "success"

        # === TRY TO GET SKIP-LEVEL (manager's manager) ===
        try:
            skip = client.get(
                f"/users/{manager.get('id')}/manager",
                params={"$select": "id,displayName,mail,jobTitle,department"},
            )
            skip_info = {
                "id": skip.get("id"),
                "name": skip.get("displayName"),
                "email": skip.get("mail"),
                "title": skip.get("jobTitle"),
                "department": skip.get("department"),
                "relationship": "skip_level",
            }
            result["skip_level"] = skip_info
            result["relationship_tiers"]["critical"].append(skip_info)
            result["sources_status"]["skip_level"] = "success"
        except Exception:
            result["sources_status"]["skip_level"] = "not_accessible"

    except Exception as e:
        error_str = str(e).lower()
        if "404" in error_str or "not found" in error_str:
            result["sources_status"]["manager"] = "no_manager_found"
        else:
            result["sources_status"]["manager"] = f"failed: {str(e)[:50]}"

    # === GET DIRECT REPORTS ===
    try:
        reports = client.get(
            "/me/directReports",
            params={
                "$select": "id,displayName,mail,jobTitle",
                "$top": 50,
            },
        )
        for report in reports.get("value", []):
            report_info = {
                "id": report.get("id"),
                "name": report.get("displayName"),
                "email": report.get("mail"),
                "title": report.get("jobTitle"),
                "relationship": "direct_report",
            }
            result["direct_reports"].append(report_info)
            result["relationship_tiers"]["high"].append(report_info)

        result["sources_status"]["direct_reports"] = "success"
    except Exception as e:
        result["sources_status"]["direct_reports"] = f"failed: {str(e)[:50]}"

    # === GET TOP COLLABORATORS (People API) ===
    try:
        people = client.get(
            "/me/people",
            params={
                "$top": 50,
                "$select": "id,displayName,emailAddresses,jobTitle,department,personType",
            },
        )

        critical_emails = set()
        if result["manager"]:
            critical_emails.add(result["manager"].get("email", "").lower())
        if result["skip_level"]:
            critical_emails.add(result["skip_level"].get("email", "").lower())

        direct_report_emails = {
            r.get("email", "").lower() for r in result["direct_reports"]
        }

        for idx, person in enumerate(people.get("value", [])):
            emails = person.get("emailAddresses", [])
            email = emails[0].get("address", "") if emails else ""
            email_lower = email.lower()

            # Skip if already categorized
            if email_lower in critical_emails or email_lower in direct_report_emails:
                continue

            person_info = {
                "id": person.get("id"),
                "name": person.get("displayName"),
                "email": email,
                "title": person.get("jobTitle"),
                "department": person.get("department"),
                "relevance_rank": idx + 1,
                "person_type": person.get("personType", {}).get("subclass"),
                "relationship": "collaborator",
            }

            result["top_collaborators"].append(person_info)

            # Tier based on relevance rank
            if idx < 10:
                result["relationship_tiers"]["high"].append(person_info)
            elif idx < 30:
                result["relationship_tiers"]["medium"].append(person_info)
            else:
                result["relationship_tiers"]["normal"].append(person_info)

        result["sources_status"]["collaborators"] = "success"
    except Exception as e:
        result["sources_status"]["collaborators"] = f"failed: {str(e)[:50]}"

    # === SUMMARY ===
    emit_success(
        f"Org context: manager={result['manager'] is not None}, "
        f"{len(result['direct_reports'])} reports, "
        f"{len(result['top_collaborators'])} collaborators"
    )

    return result


def register_msgraph_get_org_context(agent: Any) -> Tool:
    """Register the get org context tool."""
    return agent.tool()(msgraph_get_org_context)


# =============================================================================
# RELATIONSHIP CONTEXT
# =============================================================================


def msgraph_get_relationship_context(
    ctx: RunContext[Any],
    *,
    email_address: str,
) -> dict:
    """Get comprehensive relationship context with a specific person.

    This helps the agent understand:
    - Org relationship (above, below, peer, external)
    - Interaction history (emails, meetings)
    - Relevance/importance score
    - Suggested response style

    Args:
        email_address: Email of the person to analyze.

    Returns:
        Dict with relationship context including:
        - person: Their profile info
        - relationship_type: manager, skip_level, direct_report, peer, external
        - relevance_rank: Position in user's People API results
        - recent_interactions: Recent emails and meetings
        - suggested_response_style: How to communicate with them
    """
    if not email_address or not email_address.strip():
        return {
            "success": False,
            "error": "email_address cannot be empty",
        }

    email_address = email_address.strip().lower()

    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"\U0001f465 [bold cyan]Analyzing relationship: {email_address}[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    result = {
        "success": True,
        "email": email_address,
        "person": None,
        "relationship_type": "unknown",
        "relevance_rank": None,
        "is_internal": False,
        "recent_emails": [],
        "recent_meetings": [],
        "interaction_frequency": "unknown",
        "suggested_response_style": {},
    }

    # === CHECK ORG RELATIONSHIP ===
    # Check if manager
    try:
        manager = client.get(
            "/me/manager",
            params={"$select": "mail,displayName,jobTitle"},
        )
        if manager.get("mail", "").lower() == email_address:
            result["relationship_type"] = "manager"
            result["person"] = {
                "name": manager.get("displayName"),
                "email": manager.get("mail"),
                "title": manager.get("jobTitle"),
            }
    except Exception:
        pass

    # Check if direct report
    if result["relationship_type"] == "unknown":
        try:
            reports = client.get(
                "/me/directReports",
                params={"$select": "mail,displayName,jobTitle"},
            )
            for report in reports.get("value", []):
                if report.get("mail", "").lower() == email_address:
                    result["relationship_type"] = "direct_report"
                    result["person"] = {
                        "name": report.get("displayName"),
                        "email": report.get("mail"),
                        "title": report.get("jobTitle"),
                    }
                    break
        except Exception:
            pass

    # === CHECK PEOPLE API FOR RELEVANCE ===
    try:
        people = client.get(
            "/me/people",
            params={
                "$top": 100,
                "$select": "displayName,emailAddresses,jobTitle,department,personType",
            },
        )

        for idx, person in enumerate(people.get("value", [])):
            emails = [
                e.get("address", "").lower() for e in person.get("emailAddresses", [])
            ]
            if email_address in emails:
                result["relevance_rank"] = idx + 1
                result["is_internal"] = (
                    person.get("personType", {}).get("subclass") == "OrganizationUser"
                )

                if not result["person"]:
                    result["person"] = {
                        "name": person.get("displayName"),
                        "email": email_address,
                        "title": person.get("jobTitle"),
                        "department": person.get("department"),
                    }

                if result["relationship_type"] == "unknown":
                    result["relationship_type"] = (
                        "peer" if result["is_internal"] else "external"
                    )

                break

        if result["relevance_rank"] is None and result["relationship_type"] == "unknown":
            # Not in top 100 and no org relationship found - external or rarely interacted
            result["relationship_type"] = (
                "external" if not result["is_internal"] else "infrequent"
            )

    except Exception:
        pass

    # === GET RECENT EMAILS ===
    try:
        emails = client.get(
            "/me/messages",
            params={
                "$filter": f"from/emailAddress/address eq '{email_address}' or "
                f"toRecipients/any(r:r/emailAddress/address eq '{email_address}')",
                "$top": 10,
                "$select": "subject,receivedDateTime,from,toRecipients",
                "$orderby": "receivedDateTime desc",
            },
        )
        result["recent_emails"] = [
            {
                "subject": e.get("subject"),
                "date": e.get("receivedDateTime"),
                "direction": "from_them"
                if e.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                == email_address
                else "to_them",
            }
            for e in emails.get("value", [])
        ]
    except Exception:
        pass

    # === GET RECENT MEETINGS ===
    try:
        now = datetime.now(timezone.utc)
        past = now - timedelta(days=30)
        future = now + timedelta(days=30)

        events = client.get(
            "/me/calendarView",
            params={
                "startDateTime": past.isoformat(),
                "endDateTime": future.isoformat(),
                "$top": 20,
                "$select": "subject,start,attendees",
            },
        )

        for event in events.get("value", []):
            attendees = event.get("attendees", [])
            for attendee in attendees:
                if (
                    attendee.get("emailAddress", {}).get("address", "").lower()
                    == email_address
                ):
                    result["recent_meetings"].append(
                        {
                            "subject": event.get("subject"),
                            "date": event.get("start", {}).get("dateTime"),
                        }
                    )
                    break

        result["recent_meetings"] = result["recent_meetings"][:5]  # Limit
    except Exception:
        pass

    # === DETERMINE INTERACTION FREQUENCY ===
    total_interactions = len(result["recent_emails"]) + len(result["recent_meetings"])
    if total_interactions >= 15:
        result["interaction_frequency"] = "very_high"
    elif total_interactions >= 8:
        result["interaction_frequency"] = "high"
    elif total_interactions >= 3:
        result["interaction_frequency"] = "medium"
    elif total_interactions >= 1:
        result["interaction_frequency"] = "low"
    else:
        result["interaction_frequency"] = "none"

    # === SUGGEST RESPONSE STYLE ===
    rel_type = result["relationship_type"]

    if rel_type == "manager":
        result["suggested_response_style"] = {
            "urgency": "high",
            "tone": "professional_warm",
            "format": "concise_with_context",
            "tips": [
                "Respond promptly - this is your manager",
                "Be clear and action-oriented",
                "Proactively address questions they might have",
                "Include relevant updates without being asked",
            ],
        }
    elif rel_type == "skip_level":
        result["suggested_response_style"] = {
            "urgency": "critical",
            "tone": "professional_formal",
            "format": "executive_summary",
            "tips": [
                "This is your skip-level - treat as executive communication",
                "Lead with the bottom line",
                "Keep it brief and impactful",
                "Highlight wins and flag risks clearly",
            ],
        }
    elif rel_type == "direct_report":
        result["suggested_response_style"] = {
            "urgency": "medium",
            "tone": "supportive_coaching",
            "format": "clear_expectations",
            "tips": [
                "Be supportive and clear",
                "Provide context and reasoning",
                "Offer help and resources",
                "Empower them to take action",
            ],
        }
    elif rel_type == "peer" and result.get("relevance_rank", 999) <= 15:
        result["suggested_response_style"] = {
            "urgency": "medium",
            "tone": "collaborative_friendly",
            "format": "conversational",
            "tips": [
                "This is a close collaborator",
                "Be collaborative and open",
                "Share information freely",
                "Maintain the working relationship",
            ],
        }
    elif rel_type == "external":
        result["suggested_response_style"] = {
            "urgency": "normal",
            "tone": "professional_formal",
            "format": "business_communication",
            "tips": [
                "External contact - represent the organization well",
                "Be professional and courteous",
                "Clear next steps and expectations",
                "Consider CC'ing relevant internal stakeholders",
            ],
        }
    else:
        result["suggested_response_style"] = {
            "urgency": "normal",
            "tone": "professional",
            "format": "standard",
            "tips": [
                "Standard professional communication",
                "Be clear and courteous",
            ],
        }

    emit_success(
        f"Relationship: {result['relationship_type']}, "
        f"rank #{result['relevance_rank'] or 'unknown'}, "
        f"{result['interaction_frequency']} interaction"
    )

    return result


def register_msgraph_get_relationship_context(agent: Any) -> Tool:
    """Register the get relationship context tool."""
    return agent.tool()(msgraph_get_relationship_context)


# =============================================================================
# RELATIONSHIP HEALTH
# =============================================================================


def msgraph_relationship_health(
    ctx: RunContext[Any],
    *,
    days_threshold: int = 14,
    top_contacts: int = 25,
) -> dict:
    """Identify relationships that may need attention.

    Finds top contacts you haven't interacted with recently,
    suggesting proactive outreach to maintain relationships.

    Args:
        days_threshold: Days without interaction to flag (default 14).
        top_contacts: Number of top contacts to check (default 25).

    Returns:
        Dict with:
        - healthy: Recently active relationships
        - needs_attention: Contacts without recent interaction
        - suggestions: Proactive outreach suggestions
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "\u2764\ufe0f [bold cyan]Checking relationship health...[/bold cyan]"
        )
    )

    client = get_msgraph_client()
    if not client:
        return _handle_msgraph_error(Exception("Not authenticated"))

    now = datetime.now(timezone.utc)
    threshold_date = now - timedelta(days=days_threshold)

    result = {
        "success": True,
        "checked_at": now.isoformat(),
        "threshold_days": days_threshold,
        "healthy": [],
        "needs_attention": [],
        "suggestions": [],
    }

    try:
        # Get top contacts
        people = client.get(
            "/me/people",
            params={
                "$top": top_contacts,
                "$select": "displayName,emailAddresses,jobTitle",
            },
        )

        for idx, person in enumerate(people.get("value", [])):
            name = person.get("displayName", "Unknown")
            emails = person.get("emailAddresses", [])
            email = emails[0].get("address", "") if emails else ""
            title = person.get("jobTitle", "")

            if not email:
                continue

            # Check for recent emails
            last_interaction = None
            try:
                recent_emails = client.get(
                    "/me/messages",
                    params={
                        "$filter": f"(from/emailAddress/address eq '{email.lower()}') or "
                        f"(toRecipients/any(r:r/emailAddress/address eq '{email.lower()}'))",
                        "$top": 1,
                        "$select": "receivedDateTime",
                        "$orderby": "receivedDateTime desc",
                    },
                )
                if recent_emails.get("value"):
                    last_date_str = recent_emails["value"][0].get(
                        "receivedDateTime", ""
                    )
                    if last_date_str:
                        last_interaction = datetime.fromisoformat(
                            last_date_str.replace("Z", "+00:00")
                        )
            except Exception:
                pass

            contact_info = {
                "rank": idx + 1,
                "name": name,
                "email": email,
                "title": title,
                "last_interaction": last_interaction.isoformat()
                if last_interaction
                else None,
                "days_since_interaction": (now - last_interaction).days
                if last_interaction
                else None,
            }

            if last_interaction and last_interaction >= threshold_date:
                result["healthy"].append(contact_info)
            else:
                result["needs_attention"].append(contact_info)

                # Generate suggestion
                days_ago = contact_info["days_since_interaction"]
                if days_ago is None:
                    suggestion = (
                        f"Reach out to {name} ({title}) - no recent interaction found"
                    )
                elif days_ago > 30:
                    suggestion = f"Reconnect with {name} ({title}) - last contact was {days_ago} days ago"
                else:
                    suggestion = (
                        f"Check in with {name} ({title}) - it's been {days_ago} days"
                    )

                result["suggestions"].append(
                    {
                        "contact": name,
                        "email": email,
                        "action": suggestion,
                        "priority": "high" if idx < 5 else "medium",
                    }
                )

        emit_success(
            f"Relationship health: {len(result['healthy'])} healthy, "
            f"{len(result['needs_attention'])} need attention"
        )

        return result

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_relationship_health(agent: Any) -> Tool:
    """Register the relationship health tool."""
    return agent.tool()(msgraph_relationship_health)
