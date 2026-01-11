"""Comprehensive tests for terminal_screenshot_tools.py.

Tests terminal screenshot analysis, output reading, mockup comparison,
and image analysis with extensive mocking to avoid actual browser
and VQA model operations.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.terminal_screenshot_tools import (
    XTERM_TEXT_EXTRACTION_JS,
    _build_screenshot_path,
    _capture_terminal_screenshot,
    _get_terminal_page,
    load_image_for_analysis,
    register_load_image_for_analysis,
    register_terminal_compare_mockup,
    register_terminal_read_output,
    register_terminal_screenshot_analyze,
    terminal_compare_mockup,
    terminal_read_output,
    terminal_screenshot_analyze,
)
from code_puppy.tools.browser.vqa_agent import VisualAnalysisResult


class TestBuildScreenshotPath:
    """Tests for _build_screenshot_path helper function."""

    def test_build_screenshot_path_format(self):
        """Test that screenshot path has correct format."""
        path = _build_screenshot_path("terminal", "20240101_120000")

        assert path.name == "terminal_20240101_120000.png"
        assert path.suffix == ".png"

    def test_build_screenshot_path_different_prefixes(self):
        """Test path generation with different prefixes."""
        terminal_path = _build_screenshot_path("terminal", "123")
        comparison_path = _build_screenshot_path("comparison", "123")

        assert "terminal" in terminal_path.name
        assert "comparison" in comparison_path.name
        assert terminal_path != comparison_path


class TestGetTerminalPage:
    """Tests for _get_terminal_page helper function."""

    @pytest.mark.asyncio
    async def test_get_terminal_page_returns_page(self):
        """Test getting terminal page from manager."""
        mock_page = MagicMock()
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            page = await _get_terminal_page()

            assert page is mock_page
            mock_manager.get_current_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_terminal_page_returns_none_when_no_page(self):
        """Test when no terminal page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_chromium_terminal_manager",
            return_value=mock_manager,
        ):
            page = await _get_terminal_page()

            assert page is None


class TestCaptureTerminalScreenshot:
    """Tests for _capture_terminal_screenshot internal function."""

    @pytest.mark.asyncio
    async def test_capture_screenshot_success(self):
        """Test successful screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"fake_screenshot_data"

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
            ):
                result = await _capture_terminal_screenshot(
                    full_page=False,
                    save_screenshot=False,
                )

                assert result["success"] is True
                assert result["screenshot_data"] == b"fake_screenshot_data"
                assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_capture_screenshot_no_page(self):
        """Test screenshot capture when no page is available."""
        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=None,
        ):
            result = await _capture_terminal_screenshot()

            assert result["success"] is False
            assert "No active terminal page" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_screenshot_full_page(self):
        """Test full page screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"full_page_data"

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            result = await _capture_terminal_screenshot(
                full_page=True,
                save_screenshot=False,
            )

            assert result["success"] is True
            mock_page.screenshot.assert_called_once_with(full_page=True)

    @pytest.mark.asyncio
    async def test_capture_screenshot_saves_file(self):
        """Test that screenshot is saved when save_screenshot=True."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"screenshot_bytes"

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
            ):
                result = await _capture_terminal_screenshot(
                    save_screenshot=True,
                )

                assert result["success"] is True
                assert "screenshot_path" in result
                # Verify the file was created
                screenshot_path = Path(result["screenshot_path"])
                assert screenshot_path.exists()
                assert screenshot_path.read_bytes() == b"screenshot_bytes"
                # Cleanup
                screenshot_path.unlink()

    @pytest.mark.asyncio
    async def test_capture_screenshot_handles_error(self):
        """Test error handling during screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("Screenshot failed")

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            result = await _capture_terminal_screenshot()

            assert result["success"] is False
            assert "Screenshot failed" in result["error"]


class TestTerminalScreenshotAnalyze:
    """Tests for terminal_screenshot_analyze function."""

    @pytest.mark.asyncio
    async def test_analyze_success(self):
        """Test successful terminal screenshot analysis."""
        mock_vqa_result = VisualAnalysisResult(
            answer="The terminal shows a command prompt",
            confidence=0.95,
            observations="Bash prompt visible with cursor",
        )

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
            return_value={
                "success": True,
                "screenshot_data": b"screenshot",
                "timestamp": "20240101_120000",
                "screenshot_path": "/tmp/test.png",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                    ):
                        result = await terminal_screenshot_analyze(
                            question="What is shown in the terminal?"
                        )

                        assert result["success"] is True
                        assert result["question"] == "What is shown in the terminal?"
                        assert result["answer"] == "The terminal shows a command prompt"
                        assert result["confidence"] == 0.95
                        assert (
                            result["observations"] == "Bash prompt visible with cursor"
                        )

    @pytest.mark.asyncio
    async def test_analyze_screenshot_failure(self):
        """Test handling when screenshot capture fails."""
        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
            return_value={"success": False, "error": "No browser page"},
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_screenshot_analyze(
                        question="What do you see?"
                    )

                    assert result["success"] is False
                    assert "No browser page" in result["error"]
                    assert result["question"] == "What do you see?"

    @pytest.mark.asyncio
    async def test_analyze_vqa_failure(self):
        """Test handling when VQA analysis fails."""
        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
            return_value={
                "success": True,
                "screenshot_data": b"data",
                "timestamp": "123",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                side_effect=RuntimeError("VQA model unavailable"),
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                    ):
                        result = await terminal_screenshot_analyze(
                            question="What is this?"
                        )

                        assert result["success"] is False
                        assert "VQA model unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_no_screenshot_data(self):
        """Test handling when screenshot has no data."""
        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
            return_value={
                "success": True,
                "screenshot_data": None,
                "timestamp": "123",
            },
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_screenshot_analyze(question="Question?")

                    assert result["success"] is False
                    assert "no image bytes" in result["error"]


class TestTerminalReadOutput:
    """Tests for terminal_read_output function."""

    @pytest.mark.asyncio
    async def test_read_output_success(self):
        """Test successful terminal output reading."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["$ ls", "file1.txt", "file2.txt", "$ _"],
            "method": "dom_scraping",
        }

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await terminal_read_output(lines=50)

                    assert result["success"] is True
                    assert "$ ls" in result["output"]
                    assert result["line_count"] == 4

    @pytest.mark.asyncio
    async def test_read_output_limited_lines(self):
        """Test reading limited number of lines."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["line1", "line2", "line3", "line4", "line5"],
            "method": "dom_scraping",
        }

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await terminal_read_output(lines=2)

                    assert result["success"] is True
                    assert result["line_count"] == 2
                    # Should get last 2 lines
                    assert "line4" in result["output"]
                    assert "line5" in result["output"]

    @pytest.mark.asyncio
    async def test_read_output_no_page(self):
        """Test reading when no terminal page is available."""
        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=None,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "No active terminal page" in result["error"]

    @pytest.mark.asyncio
    async def test_read_output_extraction_failure(self):
        """Test handling when DOM extraction fails."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": False,
            "error": "Could not find xterm.js terminal container",
        }

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "xterm.js" in result["error"]

    @pytest.mark.asyncio
    async def test_read_output_javascript_error(self):
        """Test handling when page.evaluate throws error."""
        mock_page = AsyncMock()
        mock_page.evaluate.side_effect = RuntimeError("JavaScript error")

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "JavaScript error" in result["error"]


class TestTerminalCompareMockup:
    """Tests for terminal_compare_mockup function."""

    @pytest.mark.asyncio
    async def test_compare_success_matches(self):
        """Test successful comparison that matches."""
        mock_vqa_result = VisualAnalysisResult(
            answer="The terminal closely matches the mockup",
            confidence=0.92,
            observations="Both show the same prompt style",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_mockup_image")
            mockup_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
                return_value={
                    "success": True,
                    "screenshot_data": b"terminal_screenshot",
                    "screenshot_path": "/tmp/terminal.png",
                },
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                        ):
                            result = await terminal_compare_mockup(
                                mockup_path=mockup_path
                            )

                            assert result["success"] is True
                            assert result["matches"] is True
                            assert "match" in result["comparison"].lower()
        finally:
            Path(mockup_path).unlink()

    @pytest.mark.asyncio
    async def test_compare_success_no_match(self):
        """Test successful comparison that doesn't match."""
        mock_vqa_result = VisualAnalysisResult(
            answer="The terminal does not match the mockup - different colors",
            confidence=0.88,
            observations="Colors differ significantly",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"mockup_data")
            mockup_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
                return_value={
                    "success": True,
                    "screenshot_data": b"data",
                    "screenshot_path": "/tmp/t.png",
                },
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                        ):
                            result = await terminal_compare_mockup(
                                mockup_path=mockup_path
                            )

                            assert result["success"] is True
                            assert result["matches"] is False
        finally:
            Path(mockup_path).unlink()

    @pytest.mark.asyncio
    async def test_compare_mockup_not_found(self):
        """Test handling when mockup file doesn't exist."""
        with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_error"):
                result = await terminal_compare_mockup(
                    mockup_path="/nonexistent/mockup.png"
                )

                assert result["success"] is False
                assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_mockup_is_directory(self):
        """Test handling when mockup path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_compare_mockup(mockup_path=tmpdir)

                    assert result["success"] is False
                    assert "not a file" in result["error"]

    @pytest.mark.asyncio
    async def test_compare_screenshot_failure(self):
        """Test handling when screenshot capture fails."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"mockup")
            mockup_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
                return_value={"success": False, "error": "Browser not available"},
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                    ):
                        result = await terminal_compare_mockup(mockup_path=mockup_path)

                        assert result["success"] is False
                        assert "Browser not available" in result["error"]
        finally:
            Path(mockup_path).unlink()

    @pytest.mark.asyncio
    async def test_compare_custom_question(self):
        """Test comparison with custom question."""
        mock_vqa_result = VisualAnalysisResult(
            answer="Yes, the welcome message is visible",
            confidence=0.95,
            observations="Welcome text at top",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"data")
            mockup_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
                return_value={
                    "success": True,
                    "screenshot_data": b"data",
                    "screenshot_path": "/tmp/t.png",
                },
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ) as mock_vqa:
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                        ):
                            result = await terminal_compare_mockup(
                                mockup_path=mockup_path,
                                question="Is the welcome message visible?",
                            )

                            assert result["success"] is True
                            # Check that custom question was used
                            call_args = mock_vqa.call_args
                            assert "welcome message" in call_args[0][0].lower()
        finally:
            Path(mockup_path).unlink()


class TestLoadImageForAnalysis:
    """Tests for load_image_for_analysis function."""

    @pytest.mark.asyncio
    async def test_load_and_analyze_success(self):
        """Test successful image loading and analysis."""
        mock_vqa_result = VisualAnalysisResult(
            answer="The image shows a blue button",
            confidence=0.9,
            observations="Large centered button",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_image_data")
            image_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                    ):
                        result = await load_image_for_analysis(
                            image_path=image_path,
                            question="What do you see?",
                        )

                        assert result["success"] is True
                        assert result["image_path"] == image_path
                        assert result["question"] == "What do you see?"
                        assert result["answer"] == "The image shows a blue button"
                        assert result["confidence"] == 0.9
        finally:
            Path(image_path).unlink()

    @pytest.mark.asyncio
    async def test_load_image_not_found(self):
        """Test handling when image file doesn't exist."""
        with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_error"):
                result = await load_image_for_analysis(
                    image_path="/nonexistent/image.png",
                    question="What is this?",
                )

                assert result["success"] is False
                assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_load_image_is_directory(self):
        """Test handling when image path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await load_image_for_analysis(
                        image_path=tmpdir,
                        question="What is this?",
                    )

                    assert result["success"] is False
                    assert "not a file" in result["error"]

    @pytest.mark.asyncio
    async def test_load_image_different_formats(self):
        """Test loading different image formats."""
        formats = [
            (".png", "image/png"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".gif", "image/gif"),
            (".webp", "image/webp"),
        ]

        mock_vqa_result = VisualAnalysisResult(
            answer="Test",
            confidence=0.9,
            observations="Test",
        )

        for suffix, expected_media_type in formats:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(b"image_data")
                image_path = f.name

            try:
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ) as mock_vqa:
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                        ):
                            result = await load_image_for_analysis(
                                image_path=image_path,
                                question="Test?",
                            )

                            assert result["success"] is True
                            # Verify correct media type was passed
                            call_args = mock_vqa.call_args
                            assert call_args[0][2] == expected_media_type
            finally:
                Path(image_path).unlink()

    @pytest.mark.asyncio
    async def test_load_image_vqa_failure(self):
        """Test handling when VQA analysis fails."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"data")
            image_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                side_effect=RuntimeError("VQA failed"),
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                    ):
                        result = await load_image_for_analysis(
                            image_path=image_path,
                            question="What is this?",
                        )

                        assert result["success"] is False
                        assert "VQA failed" in result["error"]
        finally:
            Path(image_path).unlink()


class TestToolRegistration:
    """Tests for tool registration functions."""

    def test_register_terminal_screenshot_analyze(self):
        """Test terminal_screenshot_analyze registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_screenshot_analyze(mock_agent)

        assert mock_agent.tool.called

    def test_register_terminal_read_output(self):
        """Test terminal_read_output registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_read_output(mock_agent)

        assert mock_agent.tool.called

    def test_register_terminal_compare_mockup(self):
        """Test terminal_compare_mockup registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_compare_mockup(mock_agent)

        assert mock_agent.tool.called

    def test_register_load_image_for_analysis(self):
        """Test load_image_for_analysis registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_load_image_for_analysis(mock_agent)

        assert mock_agent.tool.called


class TestXtermExtractionJavaScript:
    """Tests for the xterm.js text extraction JavaScript."""

    def test_javascript_is_valid_string(self):
        """Test that the JS extraction code is a valid string."""
        assert isinstance(XTERM_TEXT_EXTRACTION_JS, str)
        assert len(XTERM_TEXT_EXTRACTION_JS) > 0

    def test_javascript_contains_selectors(self):
        """Test that JS code contains expected xterm selectors."""
        assert ".xterm-rows" in XTERM_TEXT_EXTRACTION_JS
        assert ".xterm" in XTERM_TEXT_EXTRACTION_JS

    def test_javascript_returns_structure(self):
        """Test that JS code returns expected structure."""
        assert "success" in XTERM_TEXT_EXTRACTION_JS
        assert "lines" in XTERM_TEXT_EXTRACTION_JS
        assert "error" in XTERM_TEXT_EXTRACTION_JS


class TestIntegrationScenarios:
    """Integration-like tests for full workflows."""

    @pytest.mark.asyncio
    async def test_analyze_then_compare_workflow(self):
        """Test analyzing terminal then comparing to mockup."""
        mock_vqa_result = VisualAnalysisResult(
            answer="Terminal shows command prompt",
            confidence=0.9,
            observations="Bash prompt",
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"mockup")
            mockup_path = f.name

        try:
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
                return_value={
                    "success": True,
                    "screenshot_data": b"data",
                    "screenshot_path": "/tmp/t.png",
                },
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                    return_value=mock_vqa_result,
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                    ):
                        with patch(
                            "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                        ):
                            # First analyze
                            analyze_result = await terminal_screenshot_analyze(
                                question="What is shown?"
                            )
                            assert analyze_result["success"] is True

                            # Then compare
                            compare_result = await terminal_compare_mockup(
                                mockup_path=mockup_path
                            )
                            assert compare_result["success"] is True
        finally:
            Path(mockup_path).unlink()

    @pytest.mark.asyncio
    async def test_read_output_then_analyze_workflow(self):
        """Test reading output then analyzing screenshot."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["$ echo hello", "hello"],
            "method": "dom_scraping",
        }

        mock_vqa_result = VisualAnalysisResult(
            answer="Shows echo command output",
            confidence=0.95,
            observations="Simple echo",
        )

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._get_terminal_page",
            return_value=mock_page,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    # First read output
                    read_result = await terminal_read_output(lines=10)
                    assert read_result["success"] is True
                    assert "hello" in read_result["output"]

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools._capture_terminal_screenshot",
            return_value={
                "success": True,
                "screenshot_data": b"data",
                "screenshot_path": "/tmp/t.png",
            },
        ):
            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.run_vqa_analysis",
                return_value=mock_vqa_result,
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                    ):
                        # Then analyze
                        analyze_result = await terminal_screenshot_analyze(
                            question="What command was run?"
                        )
                        assert analyze_result["success"] is True
