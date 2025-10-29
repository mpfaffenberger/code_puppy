"""Comprehensive tests for desktop VQA functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.rpa.vqa_desktop import (
    DesktopVisualAnalysisResult,
    _load_desktop_vqa_agent,
    _get_desktop_vqa_agent,
    run_desktop_vqa_analysis,
)


class TestDesktopVisualAnalysisResult:
    """Test the result model."""

    def test_create_result(self):
        result = DesktopVisualAnalysisResult(
            answer="Submit button found",
            confidence=0.95,
            observations="Button is located in the top right corner"
        )
        
        assert result.answer == "Submit button found"
        assert result.confidence == 0.95
        assert "top right" in result.observations

    def test_confidence_validation_high(self):
        result = DesktopVisualAnalysisResult(
            answer="Test",
            confidence=1.0,
            observations="Max confidence"
        )
        assert result.confidence == 1.0

    def test_confidence_validation_low(self):
        result = DesktopVisualAnalysisResult(
            answer="Test",
            confidence=0.0,
            observations="Min confidence"
        )
        assert result.confidence == 0.0

    def test_confidence_must_be_in_range(self):
        # Confidence > 1.0 should fail
        with pytest.raises(Exception):  # Pydantic validation error
            DesktopVisualAnalysisResult(
                answer="Test",
                confidence=1.5,
                observations="Invalid"
            )

    def test_confidence_negative_fails(self):
        # Confidence < 0.0 should fail
        with pytest.raises(Exception):  # Pydantic validation error
            DesktopVisualAnalysisResult(
                answer="Test",
                confidence=-0.1,
                observations="Invalid"
            )


class TestLoadDesktopVQAAgent:
    """Test agent loading and caching."""

    @patch('code_puppy.tools.rpa.vqa_desktop.ModelFactory')
    @patch('code_puppy.tools.rpa.vqa_desktop.Agent')
    def test_load_agent_creates_agent(self, mock_agent_class, mock_factory):
        mock_model = MagicMock()
        mock_factory.load_config.return_value = {}
        mock_factory.get_model.return_value = mock_model
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance
        
        # Clear cache
        _load_desktop_vqa_agent.cache_clear()
        
        agent = _load_desktop_vqa_agent("test-model")
        
        assert agent == mock_agent_instance
        mock_factory.load_config.assert_called_once()
        mock_factory.get_model.assert_called_once_with("test-model", {})
        mock_agent_class.assert_called_once()

    @patch('code_puppy.tools.rpa.vqa_desktop.ModelFactory')
    @patch('code_puppy.tools.rpa.vqa_desktop.Agent')
    def test_load_agent_caching(self, mock_agent_class, mock_factory):
        mock_model = MagicMock()
        mock_factory.load_config.return_value = {}
        mock_factory.get_model.return_value = mock_model
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance
        
        # Clear cache
        _load_desktop_vqa_agent.cache_clear()
        
        # Load twice with same model name
        agent1 = _load_desktop_vqa_agent("test-model")
        agent2 = _load_desktop_vqa_agent("test-model")
        
        # Should be the same instance (cached)
        assert agent1 is agent2
        # Agent should only be created once
        assert mock_agent_class.call_count == 1

    @patch('code_puppy.tools.rpa.vqa_desktop.ModelFactory')
    @patch('code_puppy.tools.rpa.vqa_desktop.Agent')
    def test_load_agent_different_models(self, mock_agent_class, mock_factory):
        mock_model = MagicMock()
        mock_factory.load_config.return_value = {}
        mock_factory.get_model.return_value = mock_model
        mock_agent_class.side_effect = [MagicMock(), MagicMock()]
        
        # Clear cache
        _load_desktop_vqa_agent.cache_clear()
        
        # Load with different model names
        agent1 = _load_desktop_vqa_agent("model-1")
        agent2 = _load_desktop_vqa_agent("model-2")
        
        # Should be different instances
        assert agent1 is not agent2
        assert mock_agent_class.call_count == 2


class TestGetDesktopVQAAgent:
    """Test agent getter function."""

    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    @patch('code_puppy.tools.rpa.vqa_desktop._load_desktop_vqa_agent')
    def test_get_agent_uses_config_model(self, mock_load, mock_get_model_name):
        mock_get_model_name.return_value = "configured-model"
        mock_agent = MagicMock()
        mock_load.return_value = mock_agent
        
        agent = _get_desktop_vqa_agent()
        
        assert agent == mock_agent
        mock_get_model_name.assert_called_once()
        mock_load.assert_called_once_with("configured-model")


class TestRunDesktopVQAAnalysis:
    """Test VQA analysis execution."""

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed: Patch at correct location
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_success(self, mock_get_model, mock_emit, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = DesktopVisualAnalysisResult(
            answer="Found Submit button",
            confidence=0.95,
            observations="Blue button in top right"
        )
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent
        
        image_data = b"fake_png_data"
        result = run_desktop_vqa_analysis(
            question="Find the Submit button",
            image_bytes=image_data
        )
        
        assert isinstance(result, DesktopVisualAnalysisResult)
        assert result.answer == "Found Submit button"
        assert result.confidence == 0.95
        assert "Blue button" in result.observations
        
        # Should emit info messages
        assert mock_emit.call_count >= 2  # Request and response

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed
    @patch('code_puppy.messaging.emit_warning')  # Fixed
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_failure(self, mock_get_model, mock_emit_warn, mock_emit_info, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_agent.run_sync.side_effect = RuntimeError("VQA model error")
        mock_get_agent.return_value = mock_agent
        
        image_data = b"fake_png_data"
        
        with pytest.raises(RuntimeError, match="VQA model error"):
            run_desktop_vqa_analysis(
                question="Find the Submit button",
                image_bytes=image_data
            )
        
        # Should emit warning on failure
        mock_emit_warn.assert_called_once()
        call_args = str(mock_emit_warn.call_args)
        assert "FAILED" in call_args or "Error" in call_args

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_with_custom_media_type(self, mock_get_model, mock_emit, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = DesktopVisualAnalysisResult(
            answer="Found",
            confidence=0.8,
            observations="Test"
        )
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent
        
        result = run_desktop_vqa_analysis(
            question="Test question",
            image_bytes=b"fake_jpeg",
            media_type="image/jpeg"
        )
        
        assert result is not None
        # Check that BinaryContent was created with correct media_type
        call_args = mock_agent.run_sync.call_args
        assert call_args is not None

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_emits_image_size(self, mock_get_model, mock_emit, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = DesktopVisualAnalysisResult(
            answer="Test",
            confidence=0.5,
            observations="Test"
        )
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent
        
        # 1MB image
        image_data = b"x" * 1_000_000
        run_desktop_vqa_analysis(
            question="Test",
            image_bytes=image_data
        )
        
        # Check that image size was logged
        calls = [str(call) for call in mock_emit.call_args_list]
        size_logged = any("1.00 MB" in call or "size" in call.lower() for call in calls)
        assert size_logged

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_truncates_long_question(self, mock_get_model, mock_emit, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = DesktopVisualAnalysisResult(
            answer="Test",
            confidence=0.5,
            observations="Test"
        )
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent
        
        # Very long question
        long_question = "x" * 200
        run_desktop_vqa_analysis(
            question=long_question,
            image_bytes=b"test"
        )
        
        # Check that question was truncated in logs
        calls = [str(call) for call in mock_emit.call_args_list]
        any_truncated = any("..." in call for call in calls)
        assert any_truncated

    @patch('code_puppy.tools.rpa.vqa_desktop._get_desktop_vqa_agent')
    @patch('code_puppy.messaging.emit_info')  # Fixed
    @patch('code_puppy.tools.rpa.vqa_desktop.get_vqa_model_name')
    def test_run_analysis_truncates_long_answer(self, mock_get_model, mock_emit, mock_get_agent):
        mock_get_model.return_value = "test-model"
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.output = DesktopVisualAnalysisResult(
            answer="x" * 200,  # Long answer
            confidence=0.9,
            observations="y" * 150  # Long observations
        )
        mock_agent.run_sync.return_value = mock_result
        mock_get_agent.return_value = mock_agent
        
        result = run_desktop_vqa_analysis(
            question="Test",
            image_bytes=b"test"
        )
        
        # Result should not be truncated
        assert len(result.answer) == 200
        assert len(result.observations) == 150
        
        # But logs should be truncated
        calls = [str(call) for call in mock_emit.call_args_list]
        # Check for success message with truncation
        success_calls = [c for c in calls if "RESPONSE" in c or "Answer" in c]
        assert len(success_calls) > 0
