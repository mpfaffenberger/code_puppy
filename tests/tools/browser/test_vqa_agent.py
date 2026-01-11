"""Comprehensive tests for vqa_agent.py visual question answering.

Tests VQA analysis without requiring actual image processing models.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.vqa_agent import (
    DEFAULT_VQA_INSTRUCTIONS,
    VisualAnalysisResult,
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
        assert isinstance(DEFAULT_VQA_INSTRUCTIONS, str)
        assert len(DEFAULT_VQA_INSTRUCTIONS) > 0

    def test_vqa_instructions_contain_key_phrases(self):
        """Test that instructions contain important guidance."""
        # Should mention visual analysis
        assert (
            "visual" in DEFAULT_VQA_INSTRUCTIONS.lower()
            or "image" in DEFAULT_VQA_INSTRUCTIONS.lower()
        )
        # Should mention structure/schema
        assert (
            "schema" in DEFAULT_VQA_INSTRUCTIONS.lower()
            or "structured" in DEFAULT_VQA_INSTRUCTIONS.lower()
        )
        # Should mention confidence
        assert "confidence" in DEFAULT_VQA_INSTRUCTIONS.lower()


def _create_mock_agent_result(output: str) -> MagicMock:
    """Create a mock agent run result with string output."""
    mock_result = MagicMock()
    mock_result.output = output
    return mock_result


class TestRunVQAAnalysis:
    """Test VQA analysis execution."""

    @pytest.mark.asyncio
    async def test_run_vqa_analysis_basic(self):
        """Test basic VQA analysis."""
        question = "What do you see in this image?"
        image_bytes = b"fake_image_data"

        expected_output = "I see a button"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            # Setup mocks
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            # Mock the agent instance
            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            # Result is now a string
            assert isinstance(result, str)
            assert result == "I see a button"

    @pytest.mark.asyncio
    async def test_run_vqa_analysis_with_custom_media_type(self):
        """Test VQA analysis with custom image media type."""
        question = "What is this?"
        image_bytes = b"fake_jpeg_data"

        expected_output = "It's a test image"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(
                question,
                image_bytes,
                media_type="image/jpeg",
            )

            assert result == "It's a test image"

    @pytest.mark.asyncio
    async def test_run_vqa_analysis_with_custom_system_prompt(self):
        """Test VQA analysis - system prompt is now fixed (no custom parameter)."""
        question = "What color is the sky?"
        image_bytes = b"fake_image_data"

        expected_output = "Blue"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            # No custom system_prompt parameter anymore
            result = await run_vqa_analysis(
                question,
                image_bytes,
            )

            assert result == "Blue"

    @pytest.mark.asyncio
    async def test_run_vqa_analysis_low_confidence(self):
        """Test VQA analysis with uncertain result."""
        question = "Can you identify the obscured text?"
        image_bytes = b"blurry_image_data"

        expected_output = "Cannot determine clearly - image is too blurry"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert "Cannot determine clearly" in result

    @pytest.mark.asyncio
    async def test_run_vqa_analysis_with_prompt_additions(self):
        """Test VQA analysis applies callback prompt additions."""
        question = "What do you see?"
        image_bytes = b"fake_image_data"

        expected_output = "A dog"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            # Return some prompt additions
            mock_on_load.return_value = ["Extra instruction 1", "Extra instruction 2"]
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert result == "A dog"
            # Verify prepare_prompt was called with instructions that include additions
            call_args = mock_prep.call_args[0]
            assert "Extra instruction 1" in call_args[1]
            assert "Extra instruction 2" in call_args[1]


class TestVQAIntegration:
    """Integration tests for VQA workflows."""

    @pytest.mark.asyncio
    async def test_vqa_for_button_detection(self):
        """Test VQA for detecting button presence."""
        question = "Is there a Submit button on the page?"
        image_bytes = b"screenshot_with_button"

        expected_output = (
            "Yes, there is a blue Submit button visible in top right corner"
        )
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert "Yes" in result
            assert "button" in result.lower()

    @pytest.mark.asyncio
    async def test_vqa_for_text_recognition(self):
        """Test VQA for recognizing text in images."""
        question = "What is the main heading on this page?"
        image_bytes = b"screenshot_with_heading"

        expected_output = "Welcome to Our Store"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert "Welcome" in result

    @pytest.mark.asyncio
    async def test_vqa_for_layout_analysis(self):
        """Test VQA for analyzing page layout."""
        question = "Describe the layout of the navigation menu"
        image_bytes = b"screenshot_with_nav"

        expected_output = "Horizontal navigation bar at the top with menu items: Home, About, Services, Contact"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = False

            mock_agent = MagicMock()
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_agent_class.return_value = mock_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert "navigation" in result.lower()
            assert "horizontal" in result.lower()

    @pytest.mark.asyncio
    async def test_vqa_with_dbos_enabled(self):
        """Test VQA analysis when DBOS is enabled."""
        question = "What do you see?"
        image_bytes = b"fake_image_data"

        expected_output = "A cat"
        mock_result = _create_mock_agent_result(expected_output)

        with (
            patch("code_puppy.model_factory.ModelFactory") as mock_mf,
            patch("code_puppy.callbacks.on_load_prompt") as mock_on_load,
            patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prep,
            patch("code_puppy.tools.browser.vqa_agent.get_vqa_model_name") as mock_gmn,
            patch("code_puppy.tools.browser.vqa_agent.get_use_dbos") as mock_dbos,
            patch("code_puppy.tools.browser.vqa_agent.Agent") as mock_agent_class,
            patch("pydantic_ai.durable_exec.dbos.DBOSAgent") as mock_dbos_agent,
        ):
            mock_gmn.return_value = "test-model"
            mock_mf.load_config.return_value = {"test-model": {}}
            mock_mf.get_model.return_value = MagicMock()
            mock_on_load.return_value = []
            mock_prep.return_value = MagicMock(
                instructions="prepared", user_prompt=question
            )
            mock_dbos.return_value = True  # DBOS enabled!

            mock_agent = MagicMock()
            mock_agent_class.return_value = mock_agent

            # DBOSAgent wraps the agent
            mock_wrapped_agent = MagicMock()
            mock_wrapped_agent.run = AsyncMock(return_value=mock_result)
            mock_dbos_agent.return_value = mock_wrapped_agent

            result = await run_vqa_analysis(question, image_bytes)

            assert result == "A cat"
            # Verify DBOSAgent was called to wrap the agent
            mock_dbos_agent.assert_called_once_with(mock_agent, name="vqa-agent")
