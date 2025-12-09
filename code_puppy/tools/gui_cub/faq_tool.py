"""GUI-Cub FAQ Tool - Provides canned responses for common questions.

This tool provides well-crafted responses for questions about GUI-Cub itself.
The AGENT decides when to use this tool - it should only be called when the
user is asking about GUI-Cub's capabilities, not when asking about automating
a specific application.

Good use cases:
- "What can you do?" (asking about GUI-Cub)
- "How does this agent work?"
- "What platforms do you support?"

BAD use cases (don't use FAQ for these):
- "What are the capabilities of Calculator?" (asking about an app)
- "How does Excel work?" (asking about an app)
- "Which workflows support Notepad?" (asking about app-specific workflows)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

from pydantic_ai import RunContext
from rich.console import Console

console = Console()

# Available FAQ topics - agent explicitly chooses which to retrieve
# Keys are snake_case for programmatic use, values are the exact headers in FAQ.md
FAQ_TOPICS: dict[str, str] = {
    "capabilities": "What can you do?",
    "how_it_works": "How does this agent work?",
    "workflows": "What are workflows?",
    "tier_system": "What is the tier system?",
    "calibration": "What is calibration?",
    "why_workflows_first": "Why do you check workflows first?",
    "limitations": "What can you NOT do?",
    "getting_started": "How do I get started?",
    "platforms": "What platforms do you support?",
    "debugging": "How do I report bugs or issues?",
    "knowledge_base": "What's the knowledge base?",
}


class FAQResult(TypedDict):
    """Result from FAQ lookup."""

    found: bool
    topic: str | None
    response: str
    available_topics: list[str]


def get_faq_path() -> Path:
    """Get the path to the FAQ.md file."""
    # First try the installed package location
    package_dir = Path(__file__).parent.parent.parent.parent
    faq_path = package_dir / "docs" / "gui-cub" / "FAQ.md"

    if faq_path.exists():
        return faq_path

    # Fallback to current working directory
    cwd_path = Path.cwd() / "docs" / "gui-cub" / "FAQ.md"
    if cwd_path.exists():
        return cwd_path

    # Return the expected path even if it doesn't exist
    return faq_path


def parse_faq_sections(content: str) -> dict[str, str]:
    """Parse FAQ.md into sections by header.

    Args:
        content: The raw markdown content of FAQ.md

    Returns:
        Dict mapping section headers to their content (including **Response:**)
    """
    sections: dict[str, str] = {}

    # Split by ## headers
    pattern = r"^## (.+?)$"
    matches = list(re.finditer(pattern, content, re.MULTILINE))

    for i, match in enumerate(matches):
        header = match.group(1).strip()

        # Skip non-FAQ headers (like METADATA)
        if header in ("METADATA",):
            continue

        # Get content between this header and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_content = content[start:end].strip()

        # Extract just the response part (after **Response:**)
        response_match = re.search(
            r"\*\*Response:\*\*\s*(.+?)(?=^---$|\Z)",
            section_content,
            re.DOTALL | re.MULTILINE,
        )

        if response_match:
            sections[header] = response_match.group(1).strip()
        else:
            sections[header] = section_content

    return sections


def get_faq_by_topic(topic_key: str) -> FAQResult:
    """Get an FAQ response by explicit topic key.

    The agent explicitly chooses which topic to retrieve. This avoids
    false positives from greedy keyword matching.

    Args:
        topic_key: One of the FAQ_TOPICS keys (e.g., "capabilities", "workflows")

    Returns:
        FAQResult with the response and metadata
    """
    available_topics = list(FAQ_TOPICS.keys())

    # Normalize the topic key
    topic_key_lower = topic_key.lower().strip().replace(" ", "_").replace("-", "_")

    # Check if it's a valid topic
    if topic_key_lower not in FAQ_TOPICS:
        return FAQResult(
            found=False,
            topic=None,
            response=f"Unknown topic '{topic_key}'. Available topics: {', '.join(available_topics)}",
            available_topics=available_topics,
        )

    faq_path = get_faq_path()

    if not faq_path.exists():
        return FAQResult(
            found=False,
            topic=None,
            response=f"FAQ file not found at {faq_path}. "
            "I'll answer from my training instead.",
            available_topics=available_topics,
        )

    try:
        content = faq_path.read_text(encoding="utf-8")
        sections = parse_faq_sections(content)
    except Exception as e:
        return FAQResult(
            found=False,
            topic=None,
            response=f"Error reading FAQ: {e}",
            available_topics=available_topics,
        )

    # Get the header for this topic
    header = FAQ_TOPICS[topic_key_lower]

    if header in sections:
        return FAQResult(
            found=True,
            topic=header,
            response=sections[header],
            available_topics=available_topics,
        )

    # Header not found in FAQ file (shouldn't happen if FAQ.md is in sync)
    return FAQResult(
        found=False,
        topic=None,
        response=f"Topic '{header}' not found in FAQ. This may be a sync issue.",
        available_topics=available_topics,
    )


def list_faq_topics() -> dict[str, str]:
    """List all available FAQ topics.

    Returns:
        Dict mapping topic keys to their display names
    """
    return FAQ_TOPICS.copy()


def register_faq_tool(agent):
    """Register the FAQ tool with an agent."""

    @agent.tool
    async def gui_cub_faq(
        context: RunContext,
        topic: str,
    ) -> dict:
        """Get a canned response about GUI-Cub from the official FAQ.

        ⚠️  IMPORTANT: Only use this when the user is asking about GUI-Cub itself!

        ✅ USE FOR:
        - "What can you do?" → topic="capabilities"
        - "How does this agent work?" → topic="how_it_works"
        - "What are your limitations?" → topic="limitations"

        ❌ DO NOT USE FOR:
        - "What are the capabilities of Calculator?" (asking about an APP)
        - "How does Excel work?" (asking about an APP)
        - "Which workflows support Notepad?" (asking about APP workflows)

        Available topics:
        - capabilities: What GUI-Cub can do
        - how_it_works: Architecture and how the agent operates
        - workflows: What workflows are and how they're used
        - tier_system: The keyboard → accessibility → OCR → VQA priority
        - calibration: Screen coordinate calibration
        - why_workflows_first: Why workflows are checked before any task
        - limitations: What GUI-Cub cannot do
        - getting_started: Quick start guide
        - platforms: Supported operating systems
        - debugging: How to troubleshoot and report issues
        - knowledge_base: Persistent memory across sessions

        Args:
            topic: The FAQ topic key (e.g., "capabilities", "workflows")

        Returns:
            Dict with:
            - found (bool): Whether the topic was found
            - topic (str|None): The topic header
            - response (str): The canned response
            - available_topics (list): All available topic keys

        Example:
            # User asks "What can you do?"
            result = gui_cub_faq(topic="capabilities")
        """
        result = get_faq_by_topic(topic)

        console.print(
            f"[dim]📚 FAQ lookup: topic='{topic}' -> "
            f"{result['topic'] if result['found'] else 'not found'}[/dim]"
        )

        return dict(result)

    @agent.tool
    async def gui_cub_list_faq_topics(
        context: RunContext,
    ) -> dict:
        """List all available FAQ topics that GUI-Cub can answer.

        Use this to see what topics have canned responses about GUI-Cub.
        Only use these for questions about GUI-Cub itself, not about
        specific applications being automated.

        Returns:
            Dict with:
            - topics (dict): Mapping of topic keys to display names
            - count (int): Number of topics
        """
        topics = list_faq_topics()

        return {
            "topics": topics,
            "count": len(topics),
        }
