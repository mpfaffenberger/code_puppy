"""Pure element relevance scoring logic.

This module calculates relevance scores for UI elements based on their
role, title, and characteristics. Higher scores indicate more relevant
interactive elements (buttons, fields, links).

Philosophy:
- Interactive elements (buttons, fields) score higher
- Elements with action words (submit, login, save) get boosted
- Very long titles are likely labels, not interactive elements
"""

from __future__ import annotations

from typing import Any

# ============================================================================
# Constants
# ============================================================================

# Role-based relevance scores (0.0 - 0.5)
ROLE_SCORES: dict[str, float] = {
    "AXButton": 0.5,
    "Button": 0.5,
    "AXTextField": 0.45,
    "Edit": 0.45,
    "AXMenuItem": 0.4,
    "MenuItem": 0.4,
    "AXLink": 0.35,
    "Hyperlink": 0.35,
    "AXCheckBox": 0.3,
    "CheckBox": 0.3,
}

DEFAULT_ROLE_SCORE = 0.2

# Common action words that indicate interactive elements
ACTION_WORDS: set[str] = {
    "submit",
    "login",
    "sign in",
    "search",
    "save",
    "send",
    "ok",
    "accept",
    "continue",
    "next",
    "cancel",
    "close",
    "delete",
    "remove",
    "add",
    "create",
    "edit",
    "update",
}

TITLE_BASE_SCORE = 0.1  # Base boost for having a title
ACTION_WORD_BOOST = 0.2  # Boost for containing action words
LONG_TITLE_THRESHOLD = 50  # Characters
LONG_TITLE_PENALTY = -0.1  # Penalty for very long titles


# ============================================================================
# Pure Scoring Functions
# ============================================================================


def calculate_role_score(role: str | None) -> float:
    """
    Calculate relevance score based on element role/type.

    Args:
        role: Element role (AXButton, Edit, MenuItem, etc.)

    Returns:
        Score between 0.0 and 0.5

    Examples:
        >>> calculate_role_score("AXButton")
        0.5
        >>> calculate_role_score("AXTextField")
        0.45
        >>> calculate_role_score("UnknownRole")
        0.2
        >>> calculate_role_score(None)
        0.2
    """
    if not role:
        return DEFAULT_ROLE_SCORE
    return ROLE_SCORES.get(role, DEFAULT_ROLE_SCORE)


def has_action_word(title: str) -> bool:
    """
    Check if title contains any common action words.

    Args:
        title: Element title (case-insensitive, will be lowercased)

    Returns:
        True if title contains action word, False otherwise

    Examples:
        >>> has_action_word("Submit Form")
        True
        >>> has_action_word("Click to Login")
        True
        >>> has_action_word("Hello World")
        False
    """
    title_lower = title.lower()
    return any(action in title_lower for action in ACTION_WORDS)


def calculate_title_score(title: str | None) -> float:
    """
    Calculate base score for having a title.

    Args:
        title: Element title (stripped and lowercased)

    Returns:
        0.1 if title exists and is non-empty, 0.0 otherwise

    Examples:
        >>> calculate_title_score("Submit")
        0.1
        >>> calculate_title_score("")
        0.0
        >>> calculate_title_score(None)
        0.0
    """
    if not title or not title.strip():
        return 0.0
    return TITLE_BASE_SCORE


def calculate_action_word_boost(title: str) -> float:
    """
    Calculate boost for title containing action words.

    Args:
        title: Element title (will be checked for action words)

    Returns:
        0.2 if action word found, 0.0 otherwise

    Examples:
        >>> calculate_action_word_boost("Submit Form")
        0.2
        >>> calculate_action_word_boost("Random Text")
        0.0
    """
    if has_action_word(title):
        return ACTION_WORD_BOOST
    return 0.0


def calculate_length_penalty(title: str) -> float:
    """
    Calculate penalty for very long titles.

    Very long titles are likely labels or descriptions, not
    interactive elements like buttons.

    Args:
        title: Element title

    Returns:
        -0.1 if title longer than 50 chars, 0.0 otherwise

    Examples:
        >>> calculate_length_penalty("Submit")
        0.0
        >>> calculate_length_penalty("This is a very long label that describes something in detail")
        -0.1
    """
    if len(title) > LONG_TITLE_THRESHOLD:
        return LONG_TITLE_PENALTY
    return 0.0


def calculate_element_relevance(
    role: str | None = None,
    title: str | None = None,
) -> float:
    """
    Calculate overall relevance score for UI element.

    Combines role score, title score, action word boost, and length penalty.
    Result is clamped to [0.0, 1.0] range.

    Args:
        role: Element role/type (AXButton, Edit, etc.)
        title: Element title/label

    Returns:
        Relevance score between 0.0 (not relevant) and 1.0 (highly relevant)

    Examples:
        >>> calculate_element_relevance("AXButton", "Submit")
        0.8
        >>> calculate_element_relevance("AXTextField", "Email Address")
        0.55
        >>> calculate_element_relevance(None, None)
        0.2
    """
    score = 0.0

    # Base score from role
    score += calculate_role_score(role)

    # Process title if provided
    if title:
        title_stripped = title.strip()
        if title_stripped:
            # Base score for having title
            score += calculate_title_score(title_stripped)

            # Boost for action words (case-insensitive)
            score += calculate_action_word_boost(title_stripped)

            # Penalty for long titles (use original length)
            score += calculate_length_penalty(title_stripped)

    # Clamp to [0.0, 1.0]
    return min(1.0, max(0.0, score))


def rank_elements(
    elements: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], float]]:
    """
    Rank elements by relevance score (highest first).

    Args:
        elements: List of element dictionaries with 'role', 'title', etc.

    Returns:
        List of (element, score) tuples sorted by score (descending)

    Examples:
        >>> elements = [
        ...     {"role": "AXButton", "title": "Submit"},
        ...     {"role": "AXTextField", "title": "Email"},
        ...     {"role": "AXStaticText", "title": "Description"},
        ... ]
        >>> ranked = rank_elements(elements)
        >>> ranked[0][1] > ranked[1][1] > ranked[2][1]
        True
    """
    scored = []
    for elem in elements:
        role = elem.get("role") or elem.get("type") or elem.get("control_type")
        title = elem.get("title") or ""
        score = calculate_element_relevance(role, title)
        scored.append((elem, score))

    # Sort by score (descending)
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
