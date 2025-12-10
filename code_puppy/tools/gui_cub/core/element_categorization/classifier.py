"""Pure UI element classification functions.

Classifies UI elements based on text content using keyword patterns.
No I/O - just text processing and categorization logic.
"""

from __future__ import annotations

from enum import Enum


class ElementCategory(Enum):
    """UI element category based on text content."""

    BUTTON = "button"
    FIELD = "field"
    LINK = "link"
    MENU = "menu"
    GENERIC = "generic"


# Keyword patterns for element categorization
BUTTON_KEYWORDS = [
    "submit",
    "ok",
    "cancel",
    "button",
    "save",
    "close",
    "confirm",
    "apply",
    "delete",
    "remove",
    "add",
    "create",
    "send",
    "next",
    "previous",
    "finish",
    "done",
]

FIELD_KEYWORDS = [
    "username",
    "password",
    "email",
    "name",
    "field",
    "input",
    "search",
    "text",
    "enter",
    "type",
]

LINK_KEYWORDS = [
    "link",
    "more",
    "details",
    "learn more",
    "read more",
    "view",
    "open",
]

MENU_KEYWORDS = [
    "file",
    "edit",
    "view",
    "help",
    "tools",
    "window",
    "settings",
    "preferences",
    "options",
]


def classify_element_by_text(text: str) -> ElementCategory:
    """Classify UI element based on text content.

    Uses keyword matching to determine element type.
    This is a heuristic approach - not 100% accurate but useful
    for summarization and prioritization.

    Args:
        text: Element text content

    Returns:
        ElementCategory enum value

    Example:
        >>> classify_element_by_text("Submit")
        ElementCategory.BUTTON

        >>> classify_element_by_text("Username")
        ElementCategory.FIELD

        >>> classify_element_by_text("Learn More")
        ElementCategory.LINK
    """
    if not text:
        return ElementCategory.GENERIC

    text_lower = text.lower().strip()

    # Check button keywords (highest priority)
    if any(kw in text_lower for kw in BUTTON_KEYWORDS):
        return ElementCategory.BUTTON

    # Check field keywords
    if any(kw in text_lower for kw in FIELD_KEYWORDS):
        return ElementCategory.FIELD

    # Check link keywords
    if any(kw in text_lower for kw in LINK_KEYWORDS):
        return ElementCategory.LINK

    # Check menu keywords
    if any(kw in text_lower for kw in MENU_KEYWORDS):
        return ElementCategory.MENU

    # Default to generic
    return ElementCategory.GENERIC


def categorize_text_list(texts: list[str]) -> dict[ElementCategory, list[str]]:
    """Categorize a list of text elements.

    Args:
        texts: List of text strings from UI elements

    Returns:
        Dictionary mapping categories to lists of text

    Example:
        >>> texts = ["Submit", "Cancel", "Username", "Password"]
        >>> result = categorize_text_list(texts)
        >>> result[ElementCategory.BUTTON]
        ['Submit', 'Cancel']
        >>> result[ElementCategory.FIELD]
        ['Username', 'Password']
    """
    categorized: dict[ElementCategory, list[str]] = {
        ElementCategory.BUTTON: [],
        ElementCategory.FIELD: [],
        ElementCategory.LINK: [],
        ElementCategory.MENU: [],
        ElementCategory.GENERIC: [],
    }

    for text in texts:
        category = classify_element_by_text(text)
        categorized[category].append(text)

    return categorized


def generate_summary_from_categories(
    buttons: list[str],
    fields: list[str],
    links: list[str] | None = None,
    menus: list[str] | None = None,
    max_items: int = 3,
) -> str:
    """Generate human-readable summary from categorized elements.

    Args:
        buttons: List of button texts
        fields: List of field texts
        links: Optional list of link texts
        menus: Optional list of menu texts
        max_items: Maximum items to show per category (default: 3)

    Returns:
        Human-readable summary string

    Example:
        >>> summary = generate_summary_from_categories(
        ...     buttons=["Submit", "Cancel"],
        ...     fields=["Username", "Password"]
        ... )
        >>> print(summary)
        'Username, Password fields with Submit, Cancel buttons'
    """
    parts = []

    # Add fields first (usually labels)
    if fields:
        field_sample = ", ".join(fields[:max_items])
        plural = "field" if len(fields) == 1 else "fields"
        parts.append(f"{field_sample} {plural}")

    # Add buttons
    if buttons:
        button_sample = ", ".join(buttons[:max_items])
        plural = "button" if len(buttons) == 1 else "buttons"
        parts.append(f"{button_sample} {plural}")

    # Add links if provided
    if links:
        link_sample = ", ".join(links[:max_items])
        plural = "link" if len(links) == 1 else "links"
        parts.append(f"{link_sample} {plural}")

    # Add menus if provided
    if menus:
        menu_sample = ", ".join(menus[:max_items])
        plural = "menu" if len(menus) == 1 else "menus"
        parts.append(f"{menu_sample} {plural}")

    if not parts:
        return "No categorized elements"

    # Join with "with" connector
    if len(parts) == 1:
        return parts[0]
    else:
        return " with ".join(parts)


def generate_natural_summary(texts: list[str], max_items: int = 3) -> str:
    """Generate natural language summary from text list.

    Convenience function that categorizes and summarizes in one call.

    Args:
        texts: List of text strings from UI elements
        max_items: Maximum items to show per category

    Returns:
        Human-readable summary string

    Example:
        >>> texts = ["Submit", "Cancel", "Username", "Password", "Learn More"]
        >>> summary = generate_natural_summary(texts)
        >>> print(summary)
        'Username, Password fields with Submit, Cancel buttons with Learn More links'
    """
    if not texts:
        return "No text found"

    categorized = categorize_text_list(texts)

    return generate_summary_from_categories(
        buttons=categorized[ElementCategory.BUTTON],
        fields=categorized[ElementCategory.FIELD],
        links=categorized[ElementCategory.LINK],
        menus=categorized[ElementCategory.MENU],
        max_items=max_items,
    )
