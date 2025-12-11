"""Pure text matching and scoring logic.

This module contains pure functions for fuzzy text matching,
separated from caching and I/O for easy testing.
"""

from typing import List, Tuple


def normalize_text_pure(text: str) -> str:
    """Normalize text for matching (pure function, no caching).

    Args:
        text: Text to normalize

    Returns:
        Normalized text (lowercase, trimmed whitespace)
    """
    if not text:
        return ""

    normalized = text.lower()
    normalized = " ".join(normalized.split())

    return normalized


def generate_identifier_variants(search_text: str) -> List[str]:
    """Generate identifier variants for fuzzy matching.

    Creates common programming identifier patterns:
    - "Submit" → ["submit", "submitbtn", "submit_btn", "btnsubmit", etc.]

    Args:
        search_text: Original search text

    Returns:
        List of likely identifier variants
    """
    normalized = normalize_text_pure(search_text)
    variants = [normalized]

    # Common suffixes (btn, button)
    common_suffixes = ["btn", "button"]
    for suffix in common_suffixes:
        variants.append(f"{normalized}{suffix}")  # submitbtn
        variants.append(f"{normalized}_{suffix}")  # submit_btn

    # Common prefix (btn)
    variants.append(f"btn{normalized}")  # btnsubmit
    variants.append(f"btn_{normalized}")  # btn_submit

    # Multi-word handling
    if " " in search_text:
        words = search_text.split()
        # camelCase
        camel_case = words[0].lower() + "".join(w.capitalize() for w in words[1:])
        variants.append(camel_case)  # submitButton
        # no spaces
        no_space = "".join(w.lower() for w in words)
        variants.append(no_space)  # submitbutton

    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique_variants.append(v)

    return unique_variants


def calculate_exact_match_score(search_norm: str, target_norm: str) -> float:
    """Calculate score for exact match.

    Args:
        search_norm: Normalized search text
        target_norm: Normalized target text

    Returns:
        1.0 if exact match, 0.0 otherwise
    """
    if search_norm == target_norm:
        return 1.0
    return 0.0


def calculate_substring_match_score(search_norm: str, target_norm: str) -> float:
    """Calculate score for substring match.

    Args:
        search_norm: Normalized search text
        target_norm: Normalized target text

    Returns:
        Score between 0.8-0.95 if substring match, 0.0 otherwise
    """
    if search_norm in target_norm:
        # Longer match = higher score
        ratio = len(search_norm) / len(target_norm)
        return 0.8 + (ratio * 0.15)  # Range: 0.8 to 0.95
    return 0.0


def calculate_reverse_substring_score(search_norm: str, target_norm: str) -> float:
    """Calculate score for reverse substring match (target in search).

    Args:
        search_norm: Normalized search text
        target_norm: Normalized target text

    Returns:
        Score between 0.75-0.9 if reverse match, 0.0 otherwise
    """
    if target_norm in search_norm:
        ratio = len(target_norm) / len(search_norm)
        return 0.75 + (ratio * 0.15)  # Range: 0.75 to 0.9
    return 0.0


# Maximum string length for Levenshtein calculation to prevent memory issues
MAX_LEVENSHTEIN_LENGTH = 1000


def simple_levenshtein_ratio(s1: str, s2: str) -> float:
    """Calculate simple Levenshtein distance ratio.

    Simple O(n*m) implementation for testing. Production code should use rapidfuzz.

    NOTE: Strings longer than 1000 chars are truncated to prevent memory issues.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    if not s1 or not s2:
        return 0.0

    # Truncate very long strings to prevent memory issues
    # (O(n*m) space complexity can cause OOM on pathological inputs)
    truncated = False
    if len(s1) > MAX_LEVENSHTEIN_LENGTH:
        s1 = s1[:MAX_LEVENSHTEIN_LENGTH]
        truncated = True
    if len(s2) > MAX_LEVENSHTEIN_LENGTH:
        s2 = s2[:MAX_LEVENSHTEIN_LENGTH]
        truncated = True

    if truncated:
        import warnings

        warnings.warn(
            f"Truncating strings for Levenshtein calculation (>{MAX_LEVENSHTEIN_LENGTH} chars). "
            "Results may be inaccurate. Consider using fuzzy_matching.similarity_score() instead.",
            UserWarning,
            stacklevel=2,
        )

    # Calculate Levenshtein distance
    len1, len2 = len(s1), len(s2)

    # Initialize matrix
    d = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    for i in range(len1 + 1):
        d[i][0] = i
    for j in range(len2 + 1):
        d[0][j] = j

    # Fill matrix
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,  # deletion
                d[i][j - 1] + 1,  # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )

    # Calculate ratio
    distance = d[len1][len2]
    max_len = max(len1, len2)
    return 1.0 - (distance / max_len)


def calculate_similarity_score_pure(
    search_text: str,
    target_text: str,
    use_fuzzy: bool = True,
) -> float:
    """Calculate similarity score between two texts (pure logic).

    Scoring hierarchy:
    1. Exact match: 1.0
    2. Substring match: 0.8-0.95
    3. Reverse substring: 0.75-0.9
    4. Fuzzy match: 0.0-1.0 (if enabled)

    PERFORMANCE WARNING:
        This pure implementation uses simple_levenshtein_ratio() which has
        O(n*m) time and space complexity. For production use, prefer
        fuzzy_matching.similarity_score() which uses optimized rapidfuzz.

        This pure version is primarily for testing and offline scenarios.

    Args:
        search_text: Text being searched for
        target_text: Target text to compare against
        use_fuzzy: Whether to use fuzzy matching as fallback

    Returns:
        Similarity score from 0.0 to 1.0
    """
    if not search_text or not target_text:
        return 0.0

    search_norm = normalize_text_pure(search_text)
    target_norm = normalize_text_pure(target_text)

    # 1. Try exact match
    score = calculate_exact_match_score(search_norm, target_norm)
    if score > 0:
        return score

    # 2. Try substring match
    score = calculate_substring_match_score(search_norm, target_norm)
    if score > 0:
        return score

    # 3. Try reverse substring
    score = calculate_reverse_substring_score(search_norm, target_norm)
    if score > 0:
        return score

    # 4. Fuzzy matching (simple implementation)
    if use_fuzzy:
        return simple_levenshtein_ratio(search_norm, target_norm)

    return 0.0


def apply_attribute_weight(score: float, weight: float) -> float:
    """Apply attribute weight to a score.

    Args:
        score: Base similarity score (0.0-1.0)
        weight: Attribute weight (0.0-1.0)

    Returns:
        Weighted score
    """
    return score * weight


def is_above_threshold(score: float, threshold: float) -> bool:
    """Check if score meets threshold.

    Args:
        score: Similarity score
        threshold: Minimum acceptable score

    Returns:
        True if score >= threshold
    """
    return score >= threshold


def rank_matches(matches: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """Rank matches by score (highest first).

    Args:
        matches: List of (candidate, score) tuples

    Returns:
        Sorted list of matches (highest score first)
    """
    return sorted(matches, key=lambda x: x[1], reverse=True)


def explain_match_reason(
    search_text: str,
    target_text: str,
    score: float,
) -> str:
    """Generate explanation for why texts match.

    Args:
        search_text: Search text
        target_text: Target text
        score: Similarity score

    Returns:
        Human-readable explanation
    """
    search_norm = normalize_text_pure(search_text)
    target_norm = normalize_text_pure(target_text)

    if search_norm == target_norm:
        return f"Exact match: '{search_text}' == '{target_text}'"

    if search_norm in target_norm:
        return f"Substring match: '{search_text}' in '{target_text}'"

    if target_norm in search_norm:
        return f"Partial match: '{target_text}' in '{search_text}'"

    if score >= 0.8:
        return f"Strong fuzzy match (score: {score:.2f})"

    if score >= 0.6:
        return f"Moderate fuzzy match (score: {score:.2f})"

    return f"Weak fuzzy match (score: {score:.2f})"
