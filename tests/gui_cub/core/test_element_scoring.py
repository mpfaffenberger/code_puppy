"""Unit tests for element scoring utilities."""

import pytest

from code_puppy.tools.gui_cub.core.element_scoring import (
    calculate_element_relevance_score,
    generate_score_explanation,
)


class TestCalculateElementRelevanceScore:
    """Test element relevance scoring."""

    def test_button_high_relevance(self):
        """Buttons should have high base relevance."""
        score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        assert score > 0.8  # Buttons prioritized

    def test_disabled_element_penalty(self):
        """Disabled elements should score lower."""
        enabled_score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        disabled_score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=False,
        )
        assert disabled_score < enabled_score

    def test_deep_element_penalty(self):
        """Deeper elements should score lower."""
        shallow_score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=2,
            has_value=False,
            is_enabled=True,
        )
        deep_score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=10,
            has_value=False,
            is_enabled=True,
        )
        assert deep_score < shallow_score

    def test_fuzzy_score_impact(self):
        """Higher fuzzy match should increase score."""
        low_fuzzy = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.5,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        high_fuzzy = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.95,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        assert high_fuzzy > low_fuzzy

    def test_text_vs_button(self):
        """Buttons should score higher than text."""
        button_score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        text_score = calculate_element_relevance_score(
            element_type="text",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
        )
        assert button_score > text_score

    def test_score_bounded(self):
        """Scores should be between 0 and 1."""
        score = calculate_element_relevance_score(
            element_type="button",
            fuzzy_score=1.0,
            depth=1,
            has_value=True,
            is_enabled=True,
        )
        assert 0.0 <= score <= 1.0


class TestGenerateScoreExplanation:
    """Test score explanation generation."""

    def test_explanation_contains_score(self):
        """Explanation should include the score."""
        explanation = generate_score_explanation(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
            final_score=0.85,
        )
        assert "0.85" in explanation or "85" in explanation

    def test_explanation_contains_element_type(self):
        """Explanation should mention element type."""
        explanation = generate_score_explanation(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=True,
            final_score=0.85,
        )
        assert "button" in explanation.lower()

    def test_explanation_mentions_disabled(self):
        """Explanation should mention if element is disabled."""
        explanation = generate_score_explanation(
            element_type="button",
            fuzzy_score=0.9,
            depth=3,
            has_value=False,
            is_enabled=False,
            final_score=0.5,
        )
        assert "disabled" in explanation.lower()

    def test_explanation_non_empty(self):
        """Explanation should not be empty."""
        explanation = generate_score_explanation(
            element_type="link",
            fuzzy_score=0.75,
            depth=5,
            has_value=True,
            is_enabled=True,
            final_score=0.7,
        )
        assert len(explanation) > 0
