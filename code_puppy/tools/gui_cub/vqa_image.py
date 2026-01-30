"""Visual Question Answering for image files.

This module provides VQA analysis for any image file on the filesystem,
not just screenshots. Useful for analyzing:
- Saved screenshots
- UI mockups/designs
- Diagrams and charts
- Any image format supported by the LLM vision model
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from pydantic_ai import RunContext

if TYPE_CHECKING:
    from pydantic_ai import Agent

from code_puppy.tools.common import generate_group_id

from .image_conversion import get_mime_type_from_extension
from .result_types import VQAResult
from .rich_emit import emit_rich
from .vqa_desktop import run_desktop_vqa_analysis


# Maximum image file size in MB (prevents memory issues with huge files)
MAX_IMAGE_SIZE_MB: Final = 50

# Supported image file extensions (format conversion handled by vqa_desktop)
SUPPORTED_IMAGE_EXTENSIONS: Final[set[str]] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
}


def vqa_analyze_image_impl(
    file_path: str,
    question: str,
) -> VQAResult:
    """Implementation of VQA image analysis.

    Args:
        file_path: Path to the image file
        question: Question to ask about the image

    Returns:
        VQAResult with analysis results
    """
    group_id = generate_group_id("vqa_analyze_image", file_path)

    # Validate file exists
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return VQAResult(
            success=False,
            question=question,
            error=f"File not found: {file_path}",
        )

    if not path.is_file():
        return VQAResult(
            success=False,
            question=question,
            error=f"Path is not a file: {file_path}",
        )

    # Validate extension is supported
    extension = path.suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(
            ext.upper().lstrip(".") for ext in sorted(SUPPORTED_IMAGE_EXTENSIONS)
        )
        return VQAResult(
            success=False,
            question=question,
            error=f"Unsupported image format: {extension}. Supported: {supported}",
        )

    # Get MIME type from extension (conversion handled by vqa_desktop if needed)
    media_type = get_mime_type_from_extension(extension)

    # Get file size and check against limit
    file_size_mb = path.stat().st_size / 1_000_000
    if file_size_mb > MAX_IMAGE_SIZE_MB:
        return VQAResult(
            success=False,
            question=question,
            error=f"Image too large: {file_size_mb:.1f}MB (max: {MAX_IMAGE_SIZE_MB}MB)",
        )

    emit_rich(
        f"[bold cyan]🖼️  VQA ANALYZE IMAGE 🐻 [/bold cyan]\n"
        f"[dim]   File: {path}[/dim]\n"
        f"[dim]   Size: {file_size_mb:.2f} MB[/dim]\n"
        f"[dim]   Format: {extension.upper().lstrip('.')}[/dim]\n"
        f"[dim]   Question: {question[:100]}{'...' if len(question) > 100 else ''}[/dim]",
        message_group=group_id,
    )

    try:
        # Read image bytes
        with open(path, "rb") as f:
            image_bytes = f.read()

        # Run VQA analysis
        vqa_result = run_desktop_vqa_analysis(
            question=question,
            image_bytes=image_bytes,
            media_type=media_type,
        )

        return VQAResult(
            success=True,
            question=question,
            answer=vqa_result.answer,
            confidence=vqa_result.confidence,
            observations=vqa_result.observations,
            screenshot_path=str(path),  # Include original path for reference
        )

    except Exception as e:
        emit_rich(
            f"[red]❌ VQA ANALYZE IMAGE FAILED[/red]\n"
            f"[dim]   Error: {str(e)[:200]}[/dim]",
            message_group=group_id,
        )
        return VQAResult(
            success=False,
            question=question,
            error=str(e),
        )


def register_vqa_image_tools(agent: "Agent[Any, Any]") -> "Agent[Any, Any]":
    """Register VQA image analysis tools with an agent.

    Args:
        agent: The pydantic-ai Agent instance to register tools with.

    Returns:
        The same agent instance with tools registered.

    Registers:
        - vqa_analyze_image: Analyze any image file with VQA
    """

    @agent.tool
    def vqa_analyze_image(
        _context: RunContext,
        file_path: str,
        question: str,
    ) -> VQAResult:
        """
        Analyze any image file using visual question answering (VQA).

        Use this when you have an image file and want to ask questions about it.
        Works with screenshots, UI mockups, diagrams, charts, photos, or any
        image format supported by the vision model.

        DELEGATION PATTERN:
        The image is analyzed in a SEPARATE vision model context. Only the text
        analysis is returned - the image is NOT included in the result by default.
        This achieves 99%+ token savings while maintaining full-quality analysis.

        Args:
            file_path: Path to the image file (absolute or relative)
            question: Natural language question about the image

        Returns:
            VQAResult with:
            - success: Whether analysis succeeded
            - answer: The VQA model's answer to your question
            - confidence: Confidence score (0.0-1.0)
            - observations: Additional observations about the image
            - screenshot_path: Original file path for reference

        Supported Image Formats:
            - PNG (recommended for screenshots)
            - JPEG/JPG
            - GIF (first frame only)
            - BMP
            - WebP

        Examples:
            # Analyze a saved screenshot
            result = vqa_analyze_image(
                file_path="/tmp/screenshot.png",
                question="What buttons are visible in this dialog?"
            )

            # Analyze a UI mockup
            result = vqa_analyze_image(
                file_path="./mockups/login_page.png",
                question="Where is the submit button located?"
            )

            # Analyze a diagram
            result = vqa_analyze_image(
                file_path="~/Documents/architecture.png",
                question="What services are connected to the database?"
            )

            # Analyze a previously captured debug screenshot
            result = vqa_analyze_image(
                file_path="/tmp/code_puppy_debug_screenshots/1_stage1_coarse_crop.png",
                question="What text is visible in the center of this image?"
            )

        Note:
            For analyzing the CURRENT screen, use desktop_vqa_window() instead,
            which captures a fresh screenshot before analysis.
        """
        return vqa_analyze_image_impl(file_path=file_path, question=question)

    return agent
