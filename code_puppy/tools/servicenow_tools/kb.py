"""ServiceNow Knowledge Base tools.

Tools for searching and reading Knowledge Base articles.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success

from ._common import (
    SERVICENOW_BASE_URL,
    MAX_CHARACTER_LIMIT,
    get_servicenow_client,
    handle_servicenow_error,
    convert_html_to_markdown,
    clean_text,
)


# ============================================================================
# Knowledge Base Search
# ============================================================================


def servicenow_kb_search(
    ctx: RunContext,
    query: str,
    limit: int = 10,
) -> dict:
    """Search for Knowledge Base articles by keyword.

    Args:
        ctx: PydanticAI run context
        query: Search query (keywords to find in article titles and content)
        limit: Maximum number of results to return (default: 10, max: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the search was successful
            - articles (list): List of matching articles with:
                - sys_id (str): Article system ID (use for reading full article)
                - number (str): Article number (e.g., KB0012345)
                - title (str): Article title
                - snippet (str): Text excerpt from the article
                - category (str): Article category
                - url (str): Direct link to view the article
            - total_count (int): Number of results found
            - error (str, optional): Error message if search failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW KB SEARCH [/bold white on blue] "
            f"\U0001f50d [bold cyan]{query}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_kb_articles(query=query, limit=min(limit, 50))

        articles = []
        for article in result.get("result", []):
            sys_id = article.get("sys_id", "")
            number = article.get("number", "")

            articles.append(
                {
                    "sys_id": sys_id,
                    "number": number,
                    "title": article.get("short_description", ""),
                    "snippet": clean_text(article.get("text", ""))[:300] + "..."
                    if article.get("text")
                    else "",
                    "category": article.get("kb_category", ""),
                    "url": f"{SERVICENOW_BASE_URL}/kb_view.do?sysparm_article={number}",
                }
            )

        emit_success(f"Found {len(articles)} article(s)")

        return {
            "success": True,
            "articles": articles,
            "total_count": len(articles),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_kb_search(agent: Any) -> Tool:
    """Register the servicenow_kb_search tool with a PydanticAI agent."""
    return agent.tool(servicenow_kb_search)


# ============================================================================
# Knowledge Base Read Article
# ============================================================================


def servicenow_kb_read_article(
    ctx: RunContext,
    article_id: str,
    character_limit: int = MAX_CHARACTER_LIMIT,
    character_offset: int = 0,
) -> dict:
    """Read the full content of a Knowledge Base article.

    Args:
        ctx: PydanticAI run context
        article_id: Article sys_id, KB number (e.g., KB0012345), or article number
        character_limit: Maximum characters to return (default: 30000, for large articles)
        character_offset: Starting character position for pagination (default: 0)

    Returns:
        Dict containing:
            - success (bool): Whether the article was found
            - number (str): Article number (e.g., KB0012345)
            - title (str): Article title
            - content (str): Full article content in markdown format
            - category (str): Article category
            - knowledge_base (str): Which KB this belongs to
            - author (str): Article author
            - updated (str): Last updated date
            - url (str): Direct link to view the article
            - content_truncated (bool): Whether content was truncated
            - total_content_length (int): Total length of the full content
            - remaining_content_length (int): Remaining characters if truncated
            - error (str, optional): Error message if lookup failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW KB READ [/bold white on blue] "
            f"\U0001f4d6 [bold cyan]{article_id}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()

        # Determine if it's a KB number or sys_id
        if article_id.upper().startswith("KB"):
            result = client.get_kb_article_by_number(article_id)
        else:
            result = client.get_kb_article_by_id(article_id)

        article_data = result.get("result", {})

        # Handle list response (from number lookup)
        if isinstance(article_data, list):
            if not article_data:
                return {
                    "success": False,
                    "error": f"Article not found: {article_id}",
                    "error_type": "not_found",
                }
            article_data = article_data[0]

        if not article_data:
            return {
                "success": False,
                "error": f"Article not found: {article_id}",
                "error_type": "not_found",
            }

        # Convert HTML content to markdown
        raw_content = article_data.get("text", "")
        content = convert_html_to_markdown(raw_content)

        # Apply pagination
        total_length = len(content)
        if character_offset > 0:
            content = content[character_offset:]

        truncated = len(content) > character_limit
        if truncated:
            content = content[:character_limit]
            remaining = total_length - character_offset - character_limit
        else:
            remaining = 0

        number = article_data.get("number", "")
        url = f"{SERVICENOW_BASE_URL}/kb_view.do?sysparm_article={number}"

        emit_success(f"Retrieved article: {number}")

        return {
            "success": True,
            "sys_id": article_data.get("sys_id", ""),
            "number": number,
            "title": article_data.get("short_description", ""),
            "content": content,
            "category": article_data.get("kb_category", ""),
            "knowledge_base": article_data.get("kb_knowledge_base", ""),
            "author": article_data.get("author", ""),
            "updated": article_data.get("sys_updated_on", ""),
            "url": url,
            "content_truncated": truncated,
            "total_content_length": total_length,
            "remaining_content_length": remaining,
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_kb_read_article(agent: Any) -> Tool:
    """Register the servicenow_kb_read_article tool with a PydanticAI agent."""
    return agent.tool(servicenow_kb_read_article)


# ============================================================================
# Knowledge Base Search by Category
# ============================================================================


def servicenow_kb_search_by_category(
    ctx: RunContext,
    category: str,
    query: str = "",
    limit: int = 10,
) -> dict:
    """Search for Knowledge Base articles within a specific category.

    Args:
        ctx: PydanticAI run context
        category: Category name to search within
        query: Optional search query to filter within the category
        limit: Maximum number of results to return (default: 10)

    Returns:
        Dict containing:
            - success (bool): Whether the search was successful
            - articles (list): List of matching articles
            - category (str): The category searched
            - total_count (int): Number of results found
            - error (str, optional): Error message if search failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] SERVICENOW KB CATEGORY SEARCH [/bold white on blue] "
            f"\U0001f4c1 [bold cyan]{category}[/bold cyan]"
        )
    )

    try:
        client = get_servicenow_client()
        result = client.search_kb_by_category(
            category=category,
            query=query,
            limit=min(limit, 50),
        )

        articles = []
        for article in result.get("result", []):
            sys_id = article.get("sys_id", "")
            number = article.get("number", "")

            articles.append(
                {
                    "sys_id": sys_id,
                    "number": number,
                    "title": article.get("short_description", ""),
                    "snippet": clean_text(article.get("text", ""))[:300] + "..."
                    if article.get("text")
                    else "",
                    "url": f"{SERVICENOW_BASE_URL}/kb_view.do?sysparm_article={number}",
                }
            )

        emit_success(f"Found {len(articles)} article(s) in category '{category}'")

        return {
            "success": True,
            "articles": articles,
            "category": category,
            "total_count": len(articles),
        }

    except Exception as e:
        return handle_servicenow_error(e)


def register_servicenow_kb_search_by_category(agent: Any) -> Tool:
    """Register the servicenow_kb_search_by_category tool with a PydanticAI agent."""
    return agent.tool(servicenow_kb_search_by_category)
