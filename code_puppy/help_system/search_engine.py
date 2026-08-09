"""Search engine for help content with fuzzy matching."""

from difflib import SequenceMatcher
from typing import List, Tuple


def match_score(query: str, text: str, info: dict = None) -> float:
    """Calculate relevance score using fuzzy matching."""
    text_lower = text.lower()
    brief = (info.get("brief", "") if info else "").lower()
    desc = (info.get("description", "") if info else "").lower()

    if query in text_lower:
        return 1.0
    if brief and query in brief:
        return 0.9
    if desc and query in desc:
        return 0.7

    ratio = SequenceMatcher(None, query, text_lower).ratio()
    return ratio * 0.6


def search_help(query: str, help_categories: dict) -> List[Tuple[str, str, str]]:
    """Search help content by keyword.

    Returns list of (category, name, description) tuples.
    """
    results = []
    query_lower = query.lower()

    for cat_name, cat_info in help_categories.items():
        if not isinstance(cat_info, dict) or "items" not in cat_info:
            continue

        for item_name, item_info in cat_info["items"].items():
            if isinstance(item_info, dict):
                brief = item_info.get("brief", "")
                desc = item_info.get("description", "")
                score = match_score(query_lower, item_name, item_info)
                score = max(score, match_score(query_lower, brief))
                score = max(score, match_score(query_lower, desc))
            else:
                score = match_score(query_lower, item_name)

            if score > 0.3:
                brief_text = (
                    item_info.get("brief", item_info)
                    if isinstance(item_info, dict)
                    else str(item_info)
                )
                results.append((cat_name, item_name, brief_text))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def format_search_results(results: List[Tuple[str, str, str]], query: str) -> str:
    """Format search results for display."""
    if not results:
        return (
            f'No results found for "{query}"\n\nTry: /help search <different keyword>'
        )

    output = f'Search results for "{query}" ({len(results)} matches)\n'
    output += "=" * 40 + "\n\n"

    current_cat = None
    for cat, name, desc in results:
        if cat != current_cat:
            current_cat = cat
            output += f"{cat.title()}:\n"
        output += f"  {name:25} {desc}\n"

    output += "\nUsage: /help <command> for detailed help"
    return output
