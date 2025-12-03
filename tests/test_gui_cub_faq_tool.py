"""Tests for the GUI-Cub FAQ tool."""

from pathlib import Path

from code_puppy.tools.gui_cub.faq_tool import (
    get_faq_by_topic,
    list_faq_topics,
    parse_faq_sections,
    get_faq_path,
    FAQ_TOPICS,
)


class TestFAQTopicLookup:
    """Tests for explicit topic-based FAQ lookup."""

    def test_get_capabilities_topic(self):
        """Should return capabilities FAQ when explicitly requested."""
        result = get_faq_by_topic("capabilities")
        assert result["found"] is True
        assert result["topic"] == "What can you do?"
        assert len(result["response"]) > 100

    def test_get_how_it_works_topic(self):
        """Should return how_it_works FAQ."""
        result = get_faq_by_topic("how_it_works")
        assert result["found"] is True
        assert result["topic"] == "How does this agent work?"

    def test_get_workflows_topic(self):
        """Should return workflows FAQ."""
        result = get_faq_by_topic("workflows")
        assert result["found"] is True
        assert result["topic"] == "What are workflows?"

    def test_get_tier_system_topic(self):
        """Should return tier_system FAQ."""
        result = get_faq_by_topic("tier_system")
        assert result["found"] is True
        assert result["topic"] == "What is the tier system?"

    def test_get_calibration_topic(self):
        """Should return calibration FAQ."""
        result = get_faq_by_topic("calibration")
        assert result["found"] is True
        assert result["topic"] == "What is calibration?"

    def test_get_limitations_topic(self):
        """Should return limitations FAQ."""
        result = get_faq_by_topic("limitations")
        assert result["found"] is True
        assert result["topic"] == "What can you NOT do?"

    def test_get_platforms_topic(self):
        """Should return platforms FAQ."""
        result = get_faq_by_topic("platforms")
        assert result["found"] is True
        assert result["topic"] == "What platforms do you support?"

    def test_get_getting_started_topic(self):
        """Should return getting_started FAQ."""
        result = get_faq_by_topic("getting_started")
        assert result["found"] is True
        assert result["topic"] == "How do I get started?"

    def test_unknown_topic_returns_not_found(self):
        """Should return not found for unknown topics."""
        result = get_faq_by_topic("nonexistent_topic")
        assert result["found"] is False
        assert result["topic"] is None
        assert "Unknown topic" in result["response"]
        assert len(result["available_topics"]) > 0

    def test_topic_normalization_with_dashes(self):
        """Should normalize topic keys with dashes."""
        result = get_faq_by_topic("how-it-works")
        assert result["found"] is True

    def test_topic_normalization_with_spaces(self):
        """Should normalize topic keys with spaces."""
        result = get_faq_by_topic("how it works")
        assert result["found"] is True

    def test_topic_case_insensitive(self):
        """Should handle uppercase topic keys."""
        result = get_faq_by_topic("CAPABILITIES")
        assert result["found"] is True


class TestFAQResponseQuality:
    """Tests for FAQ response content quality."""

    def test_capabilities_mentions_gui_cub(self):
        """Capabilities response should mention GUI-Cub."""
        result = get_faq_by_topic("capabilities")
        assert result["found"] is True
        assert "GUI-Cub" in result["response"]

    def test_capabilities_mentions_automation(self):
        """Capabilities response should mention automation."""
        result = get_faq_by_topic("capabilities")
        response_lower = result["response"].lower()
        assert "automat" in response_lower or "desktop" in response_lower

    def test_tier_system_mentions_keyboard(self):
        """Tier system response should mention keyboard as first priority."""
        result = get_faq_by_topic("tier_system")
        assert result["found"] is True
        assert "keyboard" in result["response"].lower()

    def test_limitations_lists_things_that_cant_be_done(self):
        """Limitations should list what can't be done."""
        result = get_faq_by_topic("limitations")
        assert result["found"] is True
        response_lower = result["response"].lower()
        # Should mention at least one limitation
        assert any(
            word in response_lower
            for word in ["captcha", "cannot", "can't", "terminal", "drm"]
        )

    def test_workflows_explains_purpose(self):
        """Workflows response should explain what they are."""
        result = get_faq_by_topic("workflows")
        assert result["found"] is True
        response_lower = result["response"].lower()
        assert "save" in response_lower or "pattern" in response_lower


class TestListFAQTopics:
    """Tests for listing FAQ topics."""

    def test_list_topics_returns_dict(self):
        """Should return a dict of topic keys to display names."""
        topics = list_faq_topics()
        assert isinstance(topics, dict)
        assert len(topics) > 0

    def test_list_topics_includes_expected_keys(self):
        """Should include expected topic keys."""
        topics = list_faq_topics()
        expected_keys = [
            "capabilities",
            "how_it_works",
            "workflows",
            "tier_system",
            "limitations",
            "platforms",
        ]
        for key in expected_keys:
            assert key in topics, f"Missing expected topic: {key}"

    def test_list_topics_values_are_questions(self):
        """Topic display names should be question-like."""
        topics = list_faq_topics()
        for key, display_name in topics.items():
            # Most display names end with '?' or contain 'What'
            assert display_name.endswith("?") or "What" in display_name, (
                f"Unexpected display name format for {key}: {display_name}"
            )


class TestFAQParsing:
    """Tests for FAQ markdown parsing."""

    def test_parse_simple_faq(self):
        """Should parse a simple FAQ structure."""
        content = """
# FAQ

## Question One

**Response:**

This is the answer to question one.

---

## Question Two

**Response:**

This is the answer to question two.

---
"""
        sections = parse_faq_sections(content)
        assert "Question One" in sections
        assert "Question Two" in sections
        assert "answer to question one" in sections["Question One"]
        assert "answer to question two" in sections["Question Two"]

    def test_parse_skips_metadata(self):
        """Should skip METADATA section."""
        content = """
## Good Question

**Response:**

Good answer.

---

## METADATA

Some metadata here.
"""
        sections = parse_faq_sections(content)
        assert "Good Question" in sections
        assert "METADATA" not in sections


class TestFAQPath:
    """Tests for FAQ file path resolution."""

    def test_get_faq_path_returns_path(self):
        """Should return a Path object."""
        path = get_faq_path()
        assert isinstance(path, Path)

    def test_faq_path_ends_with_expected_filename(self):
        """Path should end with FAQ.md."""
        path = get_faq_path()
        assert path.name == "FAQ.md"
        assert "gui-cub" in str(path)


class TestFAQTopicCoverage:
    """Tests to ensure FAQ topics are complete."""

    def test_all_topics_have_display_names(self):
        """Every topic should have a display name."""
        for key, display_name in FAQ_TOPICS.items():
            assert display_name, f"Topic {key} has no display name"
            assert len(display_name) > 5, f"Topic {key} display name too short"

    def test_all_topics_resolvable(self):
        """Every topic in FAQ_TOPICS should be resolvable."""
        for topic_key in FAQ_TOPICS.keys():
            result = get_faq_by_topic(topic_key)
            assert result["found"] is True, f"Topic {topic_key} not found in FAQ"

    def test_minimum_topic_count(self):
        """Should have at least 10 FAQ topics."""
        assert len(FAQ_TOPICS) >= 10


class TestAgentJudgmentDesign:
    """Tests to verify the agent-judgment design is correct."""

    def test_no_greedy_matching(self):
        """Should NOT match arbitrary strings with topic keywords."""
        # These should all return not found because they're not valid topic keys
        app_questions = [
            "what are the capabilities of calculator",
            "how does excel work",
            "workflow for notepad",
            "limitations of chrome",
        ]
        for query in app_questions:
            result = get_faq_by_topic(query)
            # These are NOT valid topic keys, so they should not be found
            assert result["found"] is False, f"Should not match: {query}"

    def test_explicit_topic_keys_work(self):
        """Only explicit topic keys should work."""
        # Valid topic keys should work
        valid_keys = ["capabilities", "workflows", "limitations", "platforms"]
        for key in valid_keys:
            result = get_faq_by_topic(key)
            assert result["found"] is True, f"Valid key should work: {key}"

    def test_available_topics_always_returned(self):
        """Should always return available_topics list."""
        result = get_faq_by_topic("capabilities")
        assert "available_topics" in result
        assert len(result["available_topics"]) > 0

        result2 = get_faq_by_topic("invalid_topic")
        assert "available_topics" in result2
        assert len(result2["available_topics"]) > 0
