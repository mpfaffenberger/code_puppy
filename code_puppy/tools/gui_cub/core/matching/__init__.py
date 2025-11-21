"""Text matching and scoring logic."""

from .scorer import (
    normalize_text_pure,
    generate_identifier_variants,
    calculate_exact_match_score,
    calculate_substring_match_score,
    calculate_reverse_substring_score,
    simple_levenshtein_ratio,
    calculate_similarity_score_pure,
    apply_attribute_weight,
    is_above_threshold,
    rank_matches,
    explain_match_reason,
)

__all__ = [
    "normalize_text_pure",
    "generate_identifier_variants",
    "calculate_exact_match_score",
    "calculate_substring_match_score",
    "calculate_reverse_substring_score",
    "simple_levenshtein_ratio",
    "calculate_similarity_score_pure",
    "apply_attribute_weight",
    "is_above_threshold",
    "rank_matches",
    "explain_match_reason",
]
