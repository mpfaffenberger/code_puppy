"""Fuzzy text matching utilities for element searching."""

from __future__ import annotations

import difflib
from typing import Any


def normalize_text(text: str) -> str:
    """
    Normalize text for fuzzy matching.

    Converts to lowercase, removes extra whitespace, and strips special characters.

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    if not text:
        return ""
    # Convert to lowercase
    text = text.lower()
    # Remove extra whitespace
    text = " ".join(text.split())
    return text


def extract_identifier_variants(search_text: str) -> list[str]:
    """
    Generate likely identifier variants for fuzzy matching.

    For "Submit" generates: ["submit", "submitbtn", "submit_btn", "submit-btn",
                             "btn_submit", "btnsubmit", etc.]

    Args:
        search_text: Original search text

    Returns:
        List of likely identifier variants
    """
    normalized = normalize_text(search_text)
    variants = [normalized]

    # Add common suffixes
    common_suffixes = ["btn", "button", "lbl", "label", "txt", "text", "field"]
    for suffix in common_suffixes:
        variants.append(f"{normalized}{suffix}")  # submitbtn
        variants.append(f"{normalized}_{suffix}")  # submit_btn
        variants.append(f"{normalized}-{suffix}")  # submit-btn
        variants.append(f"{suffix}{normalized}")  # btnsubmit
        variants.append(f"{suffix}_{normalized}")  # btn_submit
        variants.append(f"{suffix}-{normalized}")  # btn-submit

    # Add common prefixes
    common_prefixes = ["btn", "lbl", "txt", "fld"]
    for prefix in common_prefixes:
        variants.append(f"{prefix}{normalized}")  # btnsubmit
        variants.append(f"{prefix}_{normalized}")  # btn_submit
        variants.append(f"{prefix}-{normalized}")  # btn-submit

    # Add camelCase variants
    if " " in search_text:
        words = search_text.split()
        camel_case = words[0].lower() + "".join(w.capitalize() for w in words[1:])
        variants.append(camel_case)  # submitButton

    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)

    return unique_variants


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance (edit distance) between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Edit distance (number of single-character edits needed)
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def similarity_score(search_text: str, target_text: str) -> float:
    """
    Calculate similarity score between search text and target text.

    Combines multiple matching strategies:
    - Exact match: 1.0
    - Substring match: 0.8-0.95
    - Fuzzy match (SequenceMatcher): 0.6-0.95
    - Levenshtein distance: 0.4-0.8

    Args:
        search_text: Text being searched for
        target_text: Target text to compare against

    Returns:
        Similarity score from 0.0 (no match) to 1.0 (exact match)
    """
    if not search_text or not target_text:
        return 0.0

    search_norm = normalize_text(search_text)
    target_norm = normalize_text(target_text)

    # Exact match (case-insensitive)
    if search_norm == target_norm:
        return 1.0

    # Substring match
    if search_norm in target_norm:
        # Longer match = higher score
        ratio = len(search_norm) / len(target_norm)
        return 0.8 + (ratio * 0.15)  # 0.8 to 0.95

    # Reverse substring match (target in search)
    if target_norm in search_norm:
        ratio = len(target_norm) / len(search_norm)
        return 0.75 + (ratio * 0.15)  # 0.75 to 0.9

    # SequenceMatcher ratio (built-in fuzzy matching)
    seq_ratio = difflib.SequenceMatcher(None, search_norm, target_norm).ratio()

    # Levenshtein-based similarity
    max_len = max(len(search_norm), len(target_norm))
    if max_len > 0:
        edit_distance = levenshtein_distance(search_norm, target_norm)
        lev_similarity = 1.0 - (edit_distance / max_len)
    else:
        lev_similarity = 0.0

    # Use the higher of the two fuzzy scores
    fuzzy_score = max(seq_ratio, lev_similarity)

    return fuzzy_score


def fuzzy_match(
    search_text: str,
    candidates: list[dict[str, Any]],
    attribute_names: list[str] = None,
    threshold: float = 0.5,
) -> list[tuple[dict[str, Any], float]]:
    """
    Perform fuzzy matching on a list of candidates.

    Searches multiple attributes and returns ranked matches.

    Args:
        search_text: Text to search for
        candidates: List of candidate dictionaries/objects to search through
        attribute_names: List of attribute names to search (e.g., ["title", "description", "name"])
        threshold: Minimum similarity score to include (0.0 to 1.0)

    Returns:
        List of (candidate, score) tuples sorted by score (highest first)

    Example:
        candidates = [
            {"title": "Submit Button", "description": "Submits the form"},
            {"title": "Cancel", "description": "Cancels the operation"},
        ]
        matches = fuzzy_match("submit", candidates, ["title", "description"], threshold=0.6)
        # Returns [(first_candidate, 0.95), ...]
    """
    if not attribute_names:
        attribute_names = ["title", "description", "name", "value", "text"]

    # Generate search variants
    search_variants = extract_identifier_variants(search_text)

    # Score each candidate
    scored_candidates = []
    for candidate in candidates:
        max_score = 0.0
        best_attribute = None

        # Try each attribute
        for attr_name in attribute_names:
            # Get attribute value (works for dicts and objects)
            if isinstance(candidate, dict):
                attr_value = candidate.get(attr_name)
            else:
                attr_value = getattr(candidate, attr_name, None)

            if not attr_value:
                continue

            # Convert to string
            attr_str = str(attr_value)

            # Try exact search text first
            score = similarity_score(search_text, attr_str)

            # Try search variants
            for variant in search_variants:
                variant_score = similarity_score(variant, attr_str)
                if variant_score > score:
                    score = variant_score

            # Track best score across all attributes
            if score > max_score:
                max_score = score
                best_attribute = attr_name

        # Include if above threshold
        if max_score >= threshold:
            scored_candidates.append((candidate, max_score, best_attribute))

    # Sort by score (highest first)
    scored_candidates.sort(key=lambda x: x[1], reverse=True)

    # Return (candidate, score) tuples
    return [(candidate, score) for candidate, score, _ in scored_candidates]


def explain_match(
    search_text: str,
    target_text: str,
    score: float,
) -> str:
    """
    Generate human-readable explanation of why a match was made.

    Args:
        search_text: Original search text
        target_text: Matched target text
        score: Similarity score

    Returns:
        Explanation string
    """
    search_norm = normalize_text(search_text)
    target_norm = normalize_text(target_text)

    if search_norm == target_norm:
        return f"Exact match (case-insensitive): '{search_text}' == '{target_text}'"

    if search_norm in target_norm:
        return f"Substring match: '{search_text}' found in '{target_text}'"

    if target_norm in search_norm:
        return f"Partial match: '{target_text}' found in '{search_text}'"

    if score >= 0.8:
        return f"Strong fuzzy match (score: {score:.2f}): '{search_text}' ≈ '{target_text}'"

    if score >= 0.6:
        return f"Moderate fuzzy match (score: {score:.2f}): '{search_text}' ≈ '{target_text}'"

    return f"Weak fuzzy match (score: {score:.2f}): '{search_text}' ≈ '{target_text}'"
