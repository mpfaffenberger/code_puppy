"""Unit tests for element scoring utilities."""

from code_puppy.tools.gui_cub.core.element_scoring import (
    calculate_element_relevance,
    calculate_role_score,
    calculate_title_score,
    has_action_word,
)


class TestCalculateElementRelevance:
    """Test element relevance scoring."""

    def test_button_high_relevance(self):
        """Buttons should have high base relevance."""
        score = calculate_element_relevance(
            role="AXButton",
            title="Submit",
        )
        # Button role is 0.5, title base is 0.1, action word "submit" adds 0.2
        # Total should be around 0.8
        assert score > 0.7  # Buttons prioritized

    def test_button_with_action_word(self):
        """Buttons with action words should score higher."""
        action_score = calculate_element_relevance(
            role="AXButton",
            title="Submit Form",  # Has action word "submit"
        )
        no_action_score = calculate_element_relevance(
            role="AXButton",
            title="Button Text",  # No action word
        )
        assert action_score > no_action_score

    def test_long_title_penalty(self):
        """Very long titles should get penalized."""
        short_score = calculate_element_relevance(
            role="AXButton",
            title="Submit",
        )
        long_score = calculate_element_relevance(
            role="AXButton",
            title="This is a very long title that describes something in great detail and is probably a label not a button",
        )
        assert short_score > long_score

    def test_no_title(self):
        """Elements without title should still get role score."""
        score = calculate_element_relevance(
            role="AXButton",
            title=None,
        )
        # Should get role score (0.5) but no title bonuses
        assert score == 0.5

    def test_text_vs_button(self):
        """Buttons should score higher than text."""
        button_score = calculate_role_score("AXButton")
        text_score = calculate_role_score("AXStaticText")
        assert button_score > text_score

    def test_score_bounded(self):
        """Scores should be between 0 and 1."""
        score = calculate_element_relevance(
            role="AXButton",
            title="Submit",
        )
        assert 0.0 <= score <= 1.0


class TestActionWordDetection:
    """Test action word detection."""

    def test_has_action_word_submit(self):
        """Should detect 'submit' action word."""
        assert has_action_word("Submit Form") is True
        assert has_action_word("SUBMIT") is True

    def test_has_action_word_login(self):
        """Should detect 'login' action word."""
        assert has_action_word("Login") is True
        assert has_action_word("Sign In") is True

    def test_no_action_word(self):
        """Should return False for no action words."""
        assert has_action_word("Click me") is False
        assert has_action_word("Button") is False


class TestTitleScoring:
    """Test title-based scoring."""

    def test_calculate_title_score_with_action(self):
        """Title with action word should score higher."""
        score = calculate_title_score("Submit")
        assert score > 0

    def test_calculate_title_score_empty(self):
        """Empty title should have minimal score."""
        score = calculate_title_score("")
        assert score >= 0

    def test_calculate_title_score_none(self):
        """None title should have minimal score."""
        score = calculate_title_score(None)
        assert score >= 0
