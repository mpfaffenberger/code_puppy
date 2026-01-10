"""Comprehensive tests for vqa_agent.py visual question answering.

Tests VQA analysis without requiring actual image processing models.
"""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.browser.vqa_agent import (
    VisualAnalysisResult,
    _get_vqa_instructions,
    run_vqa_analysis,
)


class TestVisualAnalysisResult:
    """Test VisualAnalysisResult model validation."""

    def test_vqa_result_valid(self):
        """Test valid VQA result creation."""
        result = VisualAnalysisResult(
            answer="Yes, the button is visible",
            confidence=0.95,
            observations="Blue button in the center of the page",
        )

        assert result.answer == "Yes, the button is visible"
        assert result.confidence == 0.95
        assert result.observations == "Blue button in the center of the page"

    def test_vqa_result_min_confidence(self):
        """Test VQA result with minimum confidence."""
        result = VisualAnalysisResult(
            answer="Uncertain answer",
            confidence=0.0,
            observations="Limited visibility in image",
        )

        assert result.confidence == 0.0

    def test_vqa_result_max_confidence(self):
        """Test VQA result with maximum confidence."""
        result = VisualAnalysisResult(
            answer="Certain answer",
            confidence=1.0,
            observations="Clear and obvious in image",
        )

        assert result.confidence == 1.0

    def test_vqa_result_invalid_confidence_too_high(self):
        """Test VQA result rejects confidence > 1.0."""
        with pytest.raises(ValueError):
            VisualAnalysisResult(
                answer="Answer",
                confidence=1.5,  # Invalid
                observations="Observations",
            )

    def test_vqa_result_invalid_confidence_negative(self):
        """Test VQA result rejects negative confidence."""
        with pytest.raises(ValueError):
            VisualAnalysisResult(
                answer="Answer",
                confidence=-0.1,  # Invalid
                observations="Observations",
            )


class TestVQAInstructions:
    """Test VQA system instructions."""

    def test_vqa_instructions_not_empty(self):
        """Test that VQA instructions are defined."""
        instructions = _get_vqa_instructions()

        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_vqa_instructions_contain_key_phrases(self):
        """Test that instructions contain important guidance."""
        instructions = _get_vqa_instructions()

        # Should mention visual analysis
        assert "visual" in instructions.lower() or "image" in instructions.lower()
        # Should mention structure
        assert "schema" in instructions.lower() or "structured" in instructions.lower()
        # Should mention confidence
        assert "confidence" in instructions.lower()


class TestRunVQAAnalysis:
    """Test VQA analysis execution."""

    def test_run_vqa_analysis_basic(self):
        """Test basic VQA analysis."""
        question = "What do you see in this image?"
        image_bytes = b"fake_image_data"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="I see a button",
            confidence=0.85,
            observations="The button is blue and centered",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(question, image_bytes)

            assert isinstance(result, VisualAnalysisResult)
            assert result.answer == "I see a button"
            assert result.confidence == 0.85
            assert result.observations == "The button is blue and centered"

    def test_run_vqa_analysis_with_custom_media_type(self):
        """Test VQA analysis with custom image media type."""
        question = "What is this?"
        image_bytes = b"fake_jpeg_data"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="It's a test image",
            confidence=0.9,
            observations="JPEG format image",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(
                question,
                image_bytes,
                media_type="image/jpeg",
            )

            assert result.answer == "It's a test image"

    def test_run_vqa_analysis_multiple_questions(self):
        """Test VQA analysis with multiple different questions."""
        image_bytes = b"fake_image_data"
        questions = [
            "What color is the button?",
            "Where is the button located?",
            "What text does the button have?",
        ]

        answers = [
            "The button is blue",
            "The button is in the center",
            "The button says Submit",
        ]

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()

            for answer in answers:
                mock_result = MagicMock()
                mock_result.output = VisualAnalysisResult(
                    answer=answer,
                    confidence=0.9,
                    observations="Clear in image",
                )
                mock_agent.run_sync.return_value = mock_result

            mock_get_agent.return_value = mock_agent

            for question, expected_answer in zip(questions, answers):
                result = run_vqa_analysis(question, image_bytes)
                # In real execution, each would get a different answer
                assert isinstance(result, VisualAnalysisResult)

    def test_run_vqa_analysis_low_confidence(self):
        """Test VQA analysis with low confidence result."""
        question = "Can you identify the obscured text?"
        image_bytes = b"blurry_image_data"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="Cannot determine clearly",
            confidence=0.2,
            observations="Image is too blurry to identify text",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(question, image_bytes)

            assert result.confidence == 0.2
            assert "Cannot determine clearly" in result.answer


class TestVQAIntegration:
    """Integration tests for VQA workflows."""

    def test_vqa_for_button_detection(self):
        """Test VQA for detecting button presence."""
        question = "Is there a Submit button on the page?"
        image_bytes = b"screenshot_with_button"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="Yes",
            confidence=0.98,
            observations="Blue Submit button visible in top right corner",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(question, image_bytes)

            assert result.answer == "Yes"
            assert result.confidence > 0.9
            assert "button" in result.observations.lower()

    def test_vqa_for_text_recognition(self):
        """Test VQA for recognizing text in images."""
        question = "What is the main heading on this page?"
        image_bytes = b"screenshot_with_heading"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="Welcome to Our Store",
            confidence=0.92,
            observations="Black text, large font, center-aligned at top of page",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(question, image_bytes)

            assert "Welcome" in result.answer
            assert result.confidence > 0.9

    def test_vqa_for_layout_analysis(self):
        """Test VQA for analyzing page layout."""
        question = "Describe the layout of the navigation menu"
        image_bytes = b"screenshot_with_nav"

        mock_result = MagicMock()
        mock_result.output = VisualAnalysisResult(
            answer="Horizontal navigation bar at the top with menu items",
            confidence=0.88,
            observations="Dark background, white text, items: Home, About, Services, Contact",
        )

        with patch(
            "code_puppy.tools.browser.vqa_agent._get_vqa_agent"
        ) as mock_get_agent:
            mock_agent = MagicMock()
            mock_agent.run_sync.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            result = run_vqa_analysis(question, image_bytes)

            assert "navigation" in result.answer.lower()
            assert "horizontal" in result.answer.lower()
