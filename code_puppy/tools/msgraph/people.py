"""Microsoft Graph People API tools.

Provides access to the People API which surfaces:
- Relevance-ranked contacts (people you interact with most)
- People search with relevance scoring

This enables intelligent prioritization of emails/requests based on
sender importance and relationship strength.

API Reference:
https://learn.microsoft.com/en-us/graph/api/resources/person
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success
from code_puppy.tools.msgraph.common import _handle_msgraph_error, get_msgraph_client


# =============================================================================
# RELEVANT PEOPLE
# =============================================================================


def msgraph_get_relevant_people(
    ctx: RunContext[Any],
    *,
    top: int = 25,
) -> dict:
    """Get people most relevant to you.

    Returns a relevance-ranked list of people based on:
    - Communication patterns (email, meetings)
    - Working relationships
    - Organizational proximity

    Use this to prioritize emails/requests from important contacts.

    Args:
        top: Maximum number of people to return (default 25, max 100).

    Returns:
        Dict with success and list of relevant people with metadata.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            "👥 [bold cyan]Getting your most relevant contacts...[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get(
            "/me/people",
            params={
                "$top": min(top, 100),
                "$select": "id,displayName,givenName,surname,emailAddresses,jobTitle,department,officeLocation,companyName,personType",
            },
        )
        items = response.get("value", [])

        people = []
        for idx, person in enumerate(items):
            emails = person.get("emailAddresses", [])
            primary_email = emails[0].get("address") if emails else None
            people.append(
                {
                    "rank": idx + 1,  # Position indicates relevance
                    "id": person.get("id"),
                    "name": person.get("displayName"),
                    "email": primary_email,
                    "job_title": person.get("jobTitle"),
                    "department": person.get("department"),
                    "company": person.get("companyName"),
                    "person_type": person.get("personType", {}).get("subclass"),
                }
            )

        emit_success(f"Found {len(people)} relevant contacts")

        return {
            "success": True,
            "count": len(people),
            "people": people,
            "note": "People are ranked by relevance - position 1 is most relevant",
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_get_relevant_people(agent: Any) -> Tool:
    """Register the get relevant people tool."""
    return agent.tool()(msgraph_get_relevant_people)


# =============================================================================
# SEARCH PEOPLE WITH RELEVANCE
# =============================================================================


def msgraph_search_people_relevant(
    ctx: RunContext[Any],
    *,
    query: str,
    top: int = 10,
) -> dict:
    """Search for people with relevance ranking.

    Unlike basic user search, this uses the People API which:
    - Considers your relationship with each person
    - Ranks results by relevance to YOU
    - Includes people from your frequent contacts

    Args:
        query: Search query (name, email, etc.).
        top: Maximum number of results (default 10).

    Returns:
        Dict with success and relevance-ranked search results.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"🔍 [bold cyan]Searching people: {query}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        response = client.get(
            "/me/people",
            params={
                "$search": f'"{query}"',
                "$top": min(top, 50),
                "$select": "id,displayName,emailAddresses,jobTitle,department,companyName",
            },
        )
        items = response.get("value", [])

        results = []
        for idx, person in enumerate(items):
            emails = person.get("emailAddresses", [])
            primary_email = emails[0].get("address") if emails else None
            results.append(
                {
                    "relevance_rank": idx + 1,
                    "id": person.get("id"),
                    "name": person.get("displayName"),
                    "email": primary_email,
                    "job_title": person.get("jobTitle"),
                    "department": person.get("department"),
                }
            )

        emit_success(f"Found {len(results)} people matching '{query}'")

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "results": results,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_search_people_relevant(agent: Any) -> Tool:
    """Register the search people relevant tool."""
    return agent.tool()(msgraph_search_people_relevant)


# =============================================================================
# CHECK IF PERSON IS VIP
# =============================================================================


def msgraph_check_sender_importance(
    ctx: RunContext[Any],
    *,
    email_address: str,
) -> dict:
    """Check how important a sender is to you.

    Determines if a sender is in your top contacts and their
    relevance rank. Use this to prioritize inbox triage.

    Args:
        email_address: Email address to check.

    Returns:
        Dict with importance level and rank if found.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] MS GRAPH [/bold white on blue] "
            f"⭐ [bold cyan]Checking sender importance: {email_address}[/bold cyan]"
        )
    )

    try:
        client = get_msgraph_client()
        if not client:
            return _handle_msgraph_error(Exception("Not authenticated"))

        # Get top 100 relevant people
        response = client.get(
            "/me/people",
            params={
                "$top": 100,
                "$select": "id,displayName,emailAddresses",
            },
        )
        people = response.get("value", [])

        # Search for the email
        email_lower = email_address.lower()
        for idx, person in enumerate(people):
            emails = person.get("emailAddresses", [])
            for email_obj in emails:
                if email_obj.get("address", "").lower() == email_lower:
                    rank = idx + 1
                    importance = (
                        "critical"
                        if rank <= 5
                        else "high"
                        if rank <= 15
                        else "medium"
                        if rank <= 30
                        else "normal"
                    )
                    emit_success(
                        f"{person.get('displayName')} is rank #{rank} ({importance})"
                    )
                    return {
                        "success": True,
                        "found": True,
                        "name": person.get("displayName"),
                        "email": email_address,
                        "relevance_rank": rank,
                        "importance": importance,
                        "is_vip": rank <= 15,
                    }

        emit_success(f"{email_address} not in top 100 contacts")
        return {
            "success": True,
            "found": False,
            "email": email_address,
            "relevance_rank": None,
            "importance": "low",
            "is_vip": False,
        }

    except Exception as e:
        return _handle_msgraph_error(e)


def register_msgraph_check_sender_importance(agent: Any) -> Tool:
    """Register the check sender importance tool."""
    return agent.tool()(msgraph_check_sender_importance)
