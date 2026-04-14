"""Helpers for lightweight case-insensitive list filtering in TUIs."""

import re

_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")


def normalize_filter_text(text: str) -> str:
    """Normalize text for forgiving case-insensitive substring matching."""
    normalized = _NON_ALNUM_RE.sub(" ", str(text).casefold()).strip()
    return " ".join(normalized.split())


def query_matches_text(query: str, *candidates: str) -> bool:
    """Return True when every query term appears in the candidate text."""
    terms = normalize_filter_text(query).split()
    if not terms:
        return True

    haystack = " ".join(
        normalize_filter_text(candidate) for candidate in candidates if candidate
    ).strip()
    if not haystack:
        return False

    return all(term in haystack for term in terms)
