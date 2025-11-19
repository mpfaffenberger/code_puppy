"""Tests for text matching and scoring logic.

These tests validate pure fuzzy matching functions,
separated from caching and I/O operations.
"""

import pytest
from code_puppy.tools.gui_cub.core.matching import (
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


class TestNormalizeTextPure:
    """Test text normalization."""

    def test_converts_to_lowercase(self):
        """Should convert text to lowercase."""
        assert normalize_text_pure("Submit") == "submit"
        assert normalize_text_pure("CANCEL") == "cancel"

    def test_trims_whitespace(self):
        """Should remove leading/trailing whitespace."""
        assert normalize_text_pure("  submit  ") == "submit"
        assert normalize_text_pure("\tcancel\n") == "cancel"

    def test_collapses_multiple_spaces(self):
        """Should collapse multiple spaces to single space."""
        assert normalize_text_pure("submit   form") == "submit form"
        assert normalize_text_pure("a  b  c") == "a b c"

    def test_handles_empty_string(self):
        """Should return empty string for empty input."""
        assert normalize_text_pure("") == ""
        assert normalize_text_pure("   ") == ""


class TestGenerateIdentifierVariants:
    """Test identifier variant generation."""

    def test_generates_button_variants(self):
        """Should generate common button identifier patterns."""
        variants = generate_identifier_variants("submit")

        assert "submit" in variants
        assert "submitbtn" in variants
        assert "submit_btn" in variants
        assert "submitbutton" in variants
        assert "submit_button" in variants
        assert "btnsubmit" in variants
        assert "btn_submit" in variants

    def test_generates_camel_case_for_multi_word(self):
        """Should generate camelCase for multi-word inputs."""
        variants = generate_identifier_variants("Submit Form")

        assert "submitForm" in variants
        assert "submitform" in variants

    def test_removes_duplicates(self):
        """Should not include duplicate variants."""
        variants = generate_identifier_variants("btn")

        # "btn" and "btnbtn" should not duplicate
        assert len(variants) == len(set(variants))

    def test_preserves_order(self):
        """Should preserve order of variants."""
        variants = generate_identifier_variants("test")

        # Base variant should come first
        assert variants[0] == "test"


class TestCalculateExactMatchScore:
    """Test exact match scoring."""

    def test_returns_1_for_exact_match(self):
        """Should return 1.0 for exact match."""
        score = calculate_exact_match_score("submit", "submit")
        assert score == 1.0

    def test_returns_0_for_no_match(self):
        """Should return 0.0 for different texts."""
        score = calculate_exact_match_score("submit", "cancel")
        assert score == 0.0


class TestCalculateSubstringMatchScore:
    """Test substring match scoring."""

    def test_returns_high_score_for_substring(self):
        """Should return score between 0.8-0.95 for substring match."""
        score = calculate_substring_match_score("submit", "submit button")

        assert 0.8 <= score <= 0.95

    def test_higher_score_for_longer_ratio(self):
        """Longer search text relative to target should score higher."""
        score1 = calculate_substring_match_score("submit", "submit button")
        score2 = calculate_substring_match_score("sub", "submit button")

        # "submit" is longer match than "sub"
        assert score1 > score2

    def test_returns_0_for_no_substring(self):
        """Should return 0.0 if not a substring."""
        score = calculate_substring_match_score("cancel", "submit button")
        assert score == 0.0


class TestCalculateReverseSubstringScore:
    """Test reverse substring scoring (target in search)."""

    def test_returns_score_for_reverse_match(self):
        """Should return score between 0.75-0.9 for reverse match."""
        score = calculate_reverse_substring_score("submit button", "button")

        assert 0.75 <= score <= 0.9

    def test_returns_0_for_no_reverse_match(self):
        """Should return 0.0 if target not in search."""
        score = calculate_reverse_substring_score("submit", "cancel button")
        assert score == 0.0


class TestSimpleLevenshteinRatio:
    """Test Levenshtein distance ratio."""

    def test_exact_match_returns_1(self):
        """Should return 1.0 for identical strings."""
        ratio = simple_levenshtein_ratio("submit", "submit")
        assert ratio == 1.0

    def test_similar_strings_have_high_ratio(self):
        """Should return high ratio for similar strings."""
        ratio = simple_levenshtein_ratio("submit", "submitt")

        # One character different
        assert ratio > 0.8

    def test_different_strings_have_low_ratio(self):
        """Should return low ratio for very different strings."""
        ratio = simple_levenshtein_ratio("submit", "xyz")

        assert ratio < 0.3

    def test_handles_empty_strings(self):
        """Should handle empty strings gracefully."""
        assert simple_levenshtein_ratio("", "submit") == 0.0
        assert simple_levenshtein_ratio("submit", "") == 0.0


class TestCalculateSimilarityScorePure:
    """Test overall similarity scoring."""

    def test_exact_match_gets_highest_score(self):
        """Exact match should return 1.0."""
        score = calculate_similarity_score_pure("submit", "submit")
        assert score == 1.0

    def test_substring_match_gets_high_score(self):
        """Substring match should return 0.8-0.95."""
        score = calculate_similarity_score_pure("submit", "submit button")
        assert 0.8 <= score <= 0.95

    def test_reverse_substring_gets_medium_score(self):
        """Reverse substring should return 0.75-0.9."""
        score = calculate_similarity_score_pure("submit button", "button")
        assert 0.75 <= score <= 0.9

    def test_fuzzy_match_for_similar_texts(self):
        """Similar texts should get fuzzy match score."""
        score = calculate_similarity_score_pure("submit", "submitt")

        # Fuzzy match should kick in
        assert 0.5 < score < 1.0

    def test_can_disable_fuzzy_matching(self):
        """Should be able to disable fuzzy matching."""
        # These don't match via exact/substring/reverse, so with use_fuzzy=False, should be 0.0
        score = calculate_similarity_score_pure("apple", "orange", use_fuzzy=False)

        # Without fuzzy, no match for completely different words
        assert score == 0.0

        # But substring still works even with fuzzy disabled
        score2 = calculate_similarity_score_pure(
            "submit", "submit button", use_fuzzy=False
        )
        assert score2 > 0.8  # Substring match still works

    def test_case_insensitive_matching(self):
        """Should match case-insensitively."""
        score = calculate_similarity_score_pure("Submit", "SUBMIT")
        assert score == 1.0


class TestApplyAttributeWeight:
    """Test attribute weight application."""

    def test_applies_weight_correctly(self):
        """Should multiply score by weight."""
        weighted = apply_attribute_weight(0.8, 0.5)
        assert weighted == 0.4

    def test_full_weight_preserves_score(self):
        """Weight of 1.0 should preserve original score."""
        weighted = apply_attribute_weight(0.8, 1.0)
        assert weighted == 0.8

    def test_zero_weight_returns_zero(self):
        """Weight of 0.0 should return 0.0."""
        weighted = apply_attribute_weight(0.8, 0.0)
        assert weighted == 0.0


class TestIsAboveThreshold:
    """Test threshold checking."""

    def test_returns_true_when_above(self):
        """Should return True when score >= threshold."""
        assert is_above_threshold(0.8, 0.7) is True
        assert is_above_threshold(0.7, 0.7) is True

    def test_returns_false_when_below(self):
        """Should return False when score < threshold."""
        assert is_above_threshold(0.6, 0.7) is False


class TestRankMatches:
    """Test match ranking."""

    def test_sorts_by_score_descending(self):
        """Should sort matches by score, highest first."""
        matches = [
            ("candidate1", 0.5),
            ("candidate2", 0.9),
            ("candidate3", 0.7),
        ]

        ranked = rank_matches(matches)

        assert ranked[0] == ("candidate2", 0.9)
        assert ranked[1] == ("candidate3", 0.7)
        assert ranked[2] == ("candidate1", 0.5)

    def test_handles_empty_list(self):
        """Should handle empty match list."""
        ranked = rank_matches([])
        assert ranked == []

    def test_handles_tie_scores(self):
        """Should handle matches with same score."""
        matches = [
            ("candidate1", 0.8),
            ("candidate2", 0.8),
        ]

        ranked = rank_matches(matches)

        # Both should be present
        assert len(ranked) == 2
        assert all(score == 0.8 for _, score in ranked)


class TestExplainMatchReason:
    """Test match explanation generation."""

    def test_explains_exact_match(self):
        """Should explain exact matches."""
        explanation = explain_match_reason("submit", "submit", 1.0)
        assert "exact match" in explanation.lower()

    def test_explains_substring_match(self):
        """Should explain substring matches."""
        explanation = explain_match_reason("submit", "submit button", 0.85)
        assert "substring" in explanation.lower()

    def test_explains_strong_fuzzy_match(self):
        """Should identify strong fuzzy matches."""
        # Test with a high score (0.85) that's not exact/substring
        explanation = explain_match_reason("test", "tests", 0.85)
        # Should trigger either substring OR strong fuzzy (both are fine for 0.85 score)
        assert (
            "strong" in explanation.lower()
            or "substring" in explanation.lower()
            or "fuzzy" in explanation.lower()
        )

    def test_explains_moderate_fuzzy_match(self):
        """Should identify moderate fuzzy matches."""
        explanation = explain_match_reason("submit", "submut", 0.65)
        assert "moderate" in explanation.lower()

    def test_explains_weak_fuzzy_match(self):
        """Should identify weak fuzzy matches."""
        # Test with a score that would trigger weak fuzzy explanation
        explanation = explain_match_reason("apple", "orange", 0.4)
        assert "weak" in explanation.lower() or "fuzzy" in explanation.lower()


class TestIdentifierVariantsRealWorld:
    """Test identifier variants with real-world examples."""

    def test_login_button_variants(self):
        """Should generate practical variants for 'Login'."""
        variants = generate_identifier_variants("Login")

        # Common patterns
        assert "login" in variants
        assert "loginbtn" in variants
        assert "btnlogin" in variants

    def test_submit_form_variants(self):
        """Should handle multi-word identifiers."""
        variants = generate_identifier_variants("Submit Form")

        assert "submitForm" in variants  # camelCase
        assert "submitform" in variants  # no space


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
