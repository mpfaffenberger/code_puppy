"""Element relevance scoring logic.

This module provides pure functions for calculating relevance scores
for UI elements in accessibility tree.
"""

from .relevance import (
    ACTION_WORDS,
    ROLE_SCORES,
    calculate_action_word_boost,
    calculate_element_relevance,
    calculate_length_penalty,
    calculate_role_score,
    calculate_title_score,
    has_action_word,
    rank_elements,
)

__all__ = [
    "ROLE_SCORES",
    "ACTION_WORDS",
    "calculate_role_score",
    "calculate_title_score",
    "calculate_action_word_boost",
    "calculate_length_penalty",
    "calculate_element_relevance",
    "has_action_word",
    "rank_elements",
]
