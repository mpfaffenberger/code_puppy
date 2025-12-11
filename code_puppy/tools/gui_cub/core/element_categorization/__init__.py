"""UI element categorization utilities.

Pure functions for classifying UI elements based on text content.
No I/O operations, just text pattern matching and categorization.
"""

from .classifier import (
    ElementCategory,
    classify_element_by_text,
    categorize_text_list,
    generate_summary_from_categories,
    generate_natural_summary,
    BUTTON_KEYWORDS,
    FIELD_KEYWORDS,
    LINK_KEYWORDS,
    MENU_KEYWORDS,
)

__all__ = [
    "ElementCategory",
    "classify_element_by_text",
    "categorize_text_list",
    "generate_summary_from_categories",
    "generate_natural_summary",
    "BUTTON_KEYWORDS",
    "FIELD_KEYWORDS",
    "LINK_KEYWORDS",
    "MENU_KEYWORDS",
]
