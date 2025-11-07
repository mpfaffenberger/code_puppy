"""Tool metadata schema and definitions.

Provides structured metadata for all tools in the registry,
enabling programmatic tool discovery, filtering, and documentation generation.
"""

from typing import Callable, Literal, TypedDict


class ToolMetadata(TypedDict, total=False):
    """Metadata for a tool in the registry.

    All fields are optional to support gradual migration.
    Eventually, all tools should have complete metadata.
    """

    register: Callable  # Required: Function that registers the tool
    category: str  # Tool category (e.g., "Desktop Automation", "File Operations")
    description: str  # One-line description of what the tool does
    keywords: list[str]  # Keywords for search/discovery
    platform: Literal["all", "macos", "windows", "linux"]  # Platform availability
    requires_typing: bool  # Does this tool involve keyboard typing?
    use_cases: list[str]  # Common use cases for this tool


# Tool categories (standardized list)
CATEGORY_AGENT = "Agent Management"
CATEGORY_FILE_OPS = "File Operations"
CATEGORY_COMMAND = "Command Execution"
CATEGORY_BROWSER = "Browser Automation"
CATEGORY_DESKTOP = "Desktop Automation"
CATEGORY_COMMUNICATION = "Communication"
CATEGORY_KNOWLEDGE = "Knowledge Management"


def get_tool_register(tool_entry: Callable | ToolMetadata) -> Callable:
    """Extract register function from tool entry.

    Supports both old format (bare function) and new format (metadata dict).

    Args:
        tool_entry: Either a bare register function or a ToolMetadata dict

    Returns:
        The register function
    """
    if isinstance(tool_entry, dict):
        return tool_entry["register"]
    return tool_entry


def get_tool_metadata(tool_entry: Callable | ToolMetadata) -> ToolMetadata:
    """Get metadata for a tool entry.

    Args:
        tool_entry: Either a bare register function or a ToolMetadata dict

    Returns:
        ToolMetadata dict (minimal if old format)
    """
    if isinstance(tool_entry, dict):
        return tool_entry
    # Old format - return minimal metadata
    return {"register": tool_entry}
