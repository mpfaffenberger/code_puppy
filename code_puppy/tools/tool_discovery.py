"""Tool discovery and filtering utilities.

Provides functions to query and filter tools based on metadata.
"""

from typing import Callable

from .tool_metadata import ToolMetadata, get_tool_metadata


def get_tools_by_category(
    registry: dict[str, Callable | ToolMetadata], category: str
) -> list[str]:
    """Get all tool names in a specific category.

    Args:
        registry: Tool registry dict
        category: Category to filter by

    Returns:
        List of tool names in the category
    """
    return [
        name
        for name, entry in registry.items()
        if get_tool_metadata(entry).get("category") == category
    ]


def get_tools_by_keyword(
    registry: dict[str, Callable | ToolMetadata], keyword: str
) -> list[str]:
    """Get all tool names matching a keyword.

    Args:
        registry: Tool registry dict
        keyword: Keyword to search for

    Returns:
        List of tool names with matching keyword
    """
    keyword_lower = keyword.lower()
    return [
        name
        for name, entry in registry.items()
        if keyword_lower
        in [k.lower() for k in get_tool_metadata(entry).get("keywords", [])]
    ]


def get_tools_by_platform(
    registry: dict[str, Callable | ToolMetadata], platform: str
) -> list[str]:
    """Get all tools available on a specific platform.

    Args:
        registry: Tool registry dict
        platform: Platform to filter by ("macos", "windows", "linux", "all")

    Returns:
        List of tool names available on the platform
    """
    return [
        name
        for name, entry in registry.items()
        if get_tool_metadata(entry).get("platform") in [platform, "all"]
    ]


def get_tools_without_typing(registry: dict[str, Callable | ToolMetadata]) -> list[str]:
    """Get all tools that don't require keyboard typing.

    Useful for "click but don't type" use case.

    Args:
        registry: Tool registry dict

    Returns:
        List of tool names that don't require typing
    """
    return [
        name
        for name, entry in registry.items()
        if not get_tool_metadata(entry).get("requires_typing", False)
    ]


def suggest_tools(
    registry: dict[str, Callable | ToolMetadata], user_intent: str
) -> list[str]:
    """Suggest tools based on user intent.

    Args:
        registry: Tool registry dict
        user_intent: User's description of what they want to do

    Returns:
        List of suggested tool names
    """
    intent_lower = user_intent.lower()
    suggestions = set()

    # Keyword matching
    for name, entry in registry.items():
        metadata = get_tool_metadata(entry)
        keywords = metadata.get("keywords", [])

        if any(keyword.lower() in intent_lower for keyword in keywords):
            suggestions.add(name)

        # Check use cases
        use_cases = metadata.get("use_cases", [])
        if any(use_case.lower() in intent_lower for use_case in use_cases):
            suggestions.add(name)

    # Special case: "click but not type"
    if "click" in intent_lower and (
        "not type" in intent_lower or "no typ" in intent_lower
    ):
        suggestions.update(get_tools_without_typing(registry))
        # Remove typing tools
        typing_tools = [
            name
            for name, entry in registry.items()
            if get_tool_metadata(entry).get("requires_typing", False)
        ]
        suggestions.difference_update(typing_tools)

    return sorted(list(suggestions))


def generate_tool_docs(registry: dict[str, Callable | ToolMetadata]) -> str:
    """Generate formatted tool documentation from registry.

    Args:
        registry: Tool registry dict

    Returns:
        Formatted markdown documentation
    """
    # Group tools by category
    categories: dict[str, list[tuple[str, ToolMetadata]]] = {}

    for name, entry in registry.items():
        metadata = get_tool_metadata(entry)
        category = metadata.get("category", "Other")

        if category not in categories:
            categories[category] = []
        categories[category].append((name, metadata))

    # Generate documentation
    lines = []
    for category in sorted(categories.keys()):
        lines.append(f"\n### {category}\n")

        for name, metadata in sorted(categories[category], key=lambda x: x[0]):
            desc = metadata.get("description", "No description")
            platform = metadata.get("platform", "all")

            line = f"- **{name}**: {desc}"
            if platform != "all":
                line += f" ⚠️ *{platform.upper()} ONLY*"

            lines.append(line)

    return "\n".join(lines)
