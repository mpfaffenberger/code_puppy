"""Confluence Search Agent."""

from code_puppy.agents.base_agent import BaseAgent


class ConfluenceSearchAgent(BaseAgent):
    """Agent for searching Confluence documentation."""

    @property
    def name(self) -> str:
        return "confluence_search"

    @property
    def display_name(self) -> str:
        return "Confluence Search 📚"

    @property
    def description(self) -> str:
        return "Search and retrieve documentation from Walmart Confluence"

    def get_available_tools(self) -> list[str]:
        """Confluence search tools plus reasoning capability."""
        return [
            "confluence_search",
            "confluence_read_page",
            "confluence_search_by_space",
            "agent_share_your_reasoning",
        ]

    def get_system_prompt(self) -> str:
        return """
You are the Confluence search puppy. Your mission is to help users find and retrieve documentation from Walmart's Confluence.

Capabilities:
- Search Confluence for documentation pages
- Retrieve full content from specific pages
- List available Confluence spaces

Usage:
- When a user asks about documentation, search Confluence using relevant keywords
- Provide clear summaries of search results with links
- Retrieve full page content when users need detailed information
- Help users discover available spaces for focused searches

Be helpful, concise, and always provide links to the original Confluence pages.
"""
