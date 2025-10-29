"""Comprehensive tests for fuzzy text matching utilities."""

from __future__ import annotations

import pytest
from code_puppy.tools.rpa.fuzzy_matching import (
    normalize_text,
    extract_identifier_variants,
    levenshtein_distance,
    similarity_score,
    fuzzy_match,
    explain_match,
)


class TestNormalizeText:
    """Test text normalization."""

    def test_lowercase_conversion(self):
        assert normalize_text("HELLO") == "hello"
        assert normalize_text("Hello World") == "hello world"

    def test_whitespace_normalization(self):
        assert normalize_text("hello  world") == "hello world"
        assert normalize_text("  hello   world  ") == "hello world"
        assert normalize_text("hello\n\tworld") == "hello world"

    def test_empty_string(self):
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""

    def test_combined_normalization(self):
        assert normalize_text("  HELLO   World  ") == "hello world"


class TestExtractIdentifierVariants:
    """Test identifier variant generation."""

    def test_basic_variants(self):
        variants = extract_identifier_variants("submit")
        assert "submit" in variants
        assert "submitbtn" in variants
        assert "submit_btn" in variants
        assert "submit-btn" in variants
        assert "btnsubmit" in variants
        assert "btn_submit" in variants

    def test_camel_case_generation(self):
        variants = extract_identifier_variants("submit button")
        assert "submitButton" in variants

    def test_no_duplicates(self):
        variants = extract_identifier_variants("test")
        assert len(variants) == len(set(variants))

    def test_empty_string(self):
        variants = extract_identifier_variants("")
        assert len(variants) > 0


class TestLevenshteinDistance:
    """Test edit distance calculation."""

    def test_identical_strings(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_single_insertion(self):
        assert levenshtein_distance("cat", "cats") == 1

    def test_single_deletion(self):
        assert levenshtein_distance("cats", "cat") == 1

    def test_single_substitution(self):
        assert levenshtein_distance("cat", "bat") == 1

    def test_multiple_edits(self):
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("hello", "") == 5
        assert levenshtein_distance("", "world") == 5

    def test_symmetric(self):
        assert levenshtein_distance("abc", "def") == levenshtein_distance("def", "abc")


class TestSimilarityScore:
    """Test similarity scoring."""

    def test_exact_match(self):
        assert similarity_score("hello", "hello") == 1.0
        assert similarity_score("HELLO", "hello") == 1.0

    def test_substring_match(self):
        score = similarity_score("submit", "submit button")
        assert 0.8 <= score <= 0.95

    def test_reverse_substring_match(self):
        score = similarity_score("submit button", "submit")
        assert 0.75 <= score <= 0.9

    def test_no_match(self):
        score = similarity_score("abc", "xyz")
        assert score < 0.5

    def test_empty_strings(self):
        assert similarity_score("", "hello") == 0.0
        assert similarity_score("hello", "") == 0.0
        assert similarity_score("", "") == 0.0

    def test_fuzzy_match(self):
        score = similarity_score("color", "colour")
        assert 0.5 < score < 1.0


class TestFuzzyMatch:
    """Test fuzzy matching on candidates."""

    def test_dict_candidates_with_title(self):
        candidates = [
            {"title": "Submit Button", "description": "Submits the form"},
            {"title": "Cancel", "description": "Cancels the operation"},
        ]
        matches = fuzzy_match("submit", candidates, ["title", "description"], threshold=0.6)
        
        assert len(matches) >= 1
        assert matches[0][0]["title"] == "Submit Button"
        assert matches[0][1] >= 0.6

    def test_dict_candidates_multiple_attributes(self):
        candidates = [
            {"title": "OK", "description": "Submit the form"},
            {"title": "Cancel", "description": "Cancel"},
        ]
        matches = fuzzy_match("submit", candidates, ["title", "description"], threshold=0.6)
        
        assert len(matches) >= 1
        assert matches[0][0]["description"] == "Submit the form"

    def test_object_candidates(self):
        class Element:
            def __init__(self, title, name):
                self.title = title
                self.name = name

        candidates = [
            Element("Submit", "btn_submit"),
            Element("Cancel", "btn_cancel"),
        ]
        matches = fuzzy_match("submit", candidates, ["title", "name"], threshold=0.6)
        
        assert len(matches) >= 1
        assert matches[0][0].title == "Submit"

    def test_threshold_filtering(self):
        candidates = [
            {"title": "Submit Button"},
            {"title": "Completely Different"},
        ]
        matches = fuzzy_match("submit", candidates, ["title"], threshold=0.8)
        
        assert len(matches) == 1
        assert matches[0][0]["title"] == "Submit Button"

    def test_sorted_by_score(self):
        candidates = [
            {"title": "Submit Button"},
            {"title": "Submit"},
            {"title": "Submittal Form"},
        ]
        matches = fuzzy_match("submit", candidates, ["title"], threshold=0.5)
        
        assert len(matches) >= 2
        assert matches[0][1] >= matches[1][1]

    def test_default_attributes(self):
        candidates = [
            {"title": "Submit"},
            {"name": "Cancel"},
        ]
        matches = fuzzy_match("submit", candidates)
        assert len(matches) >= 1

    def test_empty_candidates(self):
        matches = fuzzy_match("submit", [], ["title"])
        assert len(matches) == 0

    def test_missing_attributes(self):
        candidates = [
            {"foo": "bar"},
        ]
        matches = fuzzy_match("submit", candidates, ["title", "description"])
        assert len(matches) == 0

    def test_none_attribute_values(self):
        candidates = [
            {"title": None, "description": "Submit"},
        ]
        matches = fuzzy_match("submit", candidates, ["title", "description"])
        assert len(matches) >= 1


class TestExplainMatch:
    """Test match explanation generation."""

    def test_exact_match_explanation(self):
        explanation = explain_match("submit", "SUBMIT", 1.0)
        assert "Exact match" in explanation
        assert "case-insensitive" in explanation.lower()

    def test_substring_match_explanation(self):
        explanation = explain_match("submit", "submit button", 0.85)
        assert "match" in explanation.lower() and "submit" in explanation.lower()

    def test_reverse_substring_explanation(self):
        explanation = explain_match("submit button", "submit", 0.80)
        assert "found in" in explanation.lower() or "partial" in explanation.lower()

    def test_strong_fuzzy_explanation(self):
        explanation = explain_match("color", "colour", 0.85)
        assert "match" in explanation.lower() and "score" in explanation.lower()

    def test_moderate_fuzzy_explanation(self):
        explanation = explain_match("abc", "abd", 0.65)
        assert "match" in explanation.lower()

    def test_weak_fuzzy_explanation(self):
        explanation = explain_match("abc", "xyz", 0.2)
        assert "match" in explanation.lower()


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_workflow(self):
        ui_elements = [
            {"title": "Submit Form", "id": "btn_submit", "type": "button"},
            {"title": "Cancel", "id": "btn_cancel", "type": "button"},
            {"title": "Submit Order", "id": "order_submit", "type": "button"},
        ]
        
        matches = fuzzy_match(
            "submit",
            ui_elements,
            ["title", "id"],
            threshold=0.6
        )
        
        assert len(matches) >= 2
        
        for element, score in matches:
            assert score >= 0.6
            assert "submit" in element["title"].lower() or "submit" in element["id"].lower()

    def test_identifier_variant_matching(self):
        elements = [
            {"id": "btnSubmit"},
            {"id": "btn_submit"},
            {"id": "submit-button"},
        ]
        
        matches = fuzzy_match("submit", elements, ["id"], threshold=0.6)
        
        assert len(matches) == 3
