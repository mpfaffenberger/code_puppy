"""VQA (Visual Question Answering) analysis for screenshots."""

from __future__ import annotations


from ..constants import DEFAULT_GRID_SPACING
from ..result_types import VQAResult, CompactSummary
from .capture import screenshot
from datetime import datetime


async def screenshot_analyze(
    question: str | None = None,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    window_title: str | None = None,
    mode: str = "active_window",
    save_path: str | None = None,
    add_grid: bool = False,
    grid_spacing: int = DEFAULT_GRID_SPACING,
    confidence_threshold: float = 0.85,
    auto_refine: bool = False,
    language: str = "eng",
    include_image: bool = False,
) -> dict:
    """
    Unified screenshot + analysis function.

    Combines functionality from:
    - take_desktop_screenshot_and_analyze() - VQA core
    - desktop_screenshot_analyze() - VQA wrapper
    - desktop_extract_text() - OCR analysis
    - desktop_screenshot_with_confidence() - Grid refinement

    DELEGATION PATTERN:
    Screenshots are analyzed in a SEPARATE agent context (for VQA) or locally (for OCR).
    By default, the full image is NOT returned to the main agent - only the text analysis.
    This achieves 99%+ token savings while maintaining full-quality image analysis.

    Args:
        question: VQA question. If None, runs OCR instead.
        x, y, width, height: Region coordinates (all must be provided together)
        window_title: Focus and capture specific window
        mode: "active_window" (default), "full_screen", "region"
        save_path: Custom save path (None = auto temp path)
        add_grid: Add coordinate grid overlay
        grid_spacing: Grid line spacing in pixels
        confidence_threshold: Min confidence for auto-refine
        auto_refine: Automatically add grid if confidence low
        language: Language code for OCR (default: "eng")
        include_image: Include base64 image in result (default: False for token savings)

    Returns:
        Unified analysis result:
        {
            "success": bool,
            "screenshot_path": str,
            "analysis_type": "ocr" | "vqa",
            "image_base64": str | None,  # Only if include_image=True

            # OCR fields (if question=None)
            "full_text": str,
            "text_elements": list,
            "word_count": int,

            # VQA fields (if question provided)
            "question": str,
            "answer": str,
            "confidence": float,
            "observations": str,
        }

    Examples:
        # VQA analysis (default - no image in result)
        result = await screenshot_analyze(
            question="Where is the Submit button?"
        )
        # Returns: ~300 tokens (text analysis only)

        # VQA with image included (for debugging)
        result = await screenshot_analyze(
            question="Where is the Submit button?",
            include_image=True  # Include full image in result
        )
        # Returns: ~120,000 tokens (includes base64 image)

        # VQA with auto grid refinement
        result = await screenshot_analyze(
            question="Find the OK button",
            auto_refine=True,
            confidence_threshold=0.9
        )
    """
    from ..ocr import extract_text_from_image
    from ..vqa_desktop import run_desktop_vqa_analysis
    from PIL import Image
    import os

    # Determine if OCR or VQA mode
    is_ocr = question is None

    # VQA mode needs the screenshot file saved to disk for analysis
    # Generate a temp path if not provided
    if not is_ocr and save_path is None:
        from tempfile import gettempdir
        from pathlib import Path
        temp_dir = Path(gettempdir()) / "code_puppy_vqa_screenshots"
        temp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str(temp_dir / f"vqa_screenshot_{timestamp}.png")

    # Initial capture (without grid if auto_refine is enabled)
    initial_grid = add_grid if not auto_refine else False

    # Capture screenshot using unified screenshot() function
    screenshot_result = screenshot(
        x=x,
        y=y,
        width=width,
        height=height,
        window_title=window_title,
        mode=mode,
        save_path=save_path,
        add_grid=initial_grid,
        grid_spacing=grid_spacing,
    )

    if not screenshot_result.success:
        return {
            "success": False,
            "error": screenshot_result.error,
            "analysis_type": "ocr" if is_ocr else "vqa",
        }

    result = {
        "success": True,
        "screenshot_path": screenshot_result.screenshot_path,
    }

    # Add base64 image if requested (delegation pattern - excluded by default)
    if include_image and screenshot_result.screenshot_path:
        import base64

        with open(screenshot_result.screenshot_path, "rb") as f:
            image_data = f.read()
            result["image_base64"] = base64.b64encode(image_data).decode("utf-8")

    if is_ocr:
        # OCR MODE
        # Load screenshot image
        screenshot_path = screenshot_result.screenshot_path
        if not screenshot_path or not os.path.exists(screenshot_path):
            return {
                "success": False,
                "error": "Screenshot file not found for OCR analysis",
                "analysis_type": "ocr",
            }

        image = Image.open(screenshot_path)
        ocr_result = extract_text_from_image(image, language=language)

        result["analysis_type"] = "ocr"
        result["full_text"] = ocr_result.full_text if ocr_result.success else ""
        result["text_elements"] = ocr_result.text_elements if ocr_result.success else []
        result["word_count"] = (
            len(result["full_text"].split()) if result["full_text"] else 0
        )

        if not ocr_result.success:
            result["success"] = False
            result["error"] = ocr_result.error

    else:
        # VQA MODE
        # Load screenshot image for VQA
        screenshot_path = screenshot_result.screenshot_path
        if not screenshot_path or not os.path.exists(screenshot_path):
            return {
                "success": False,
                "error": "Screenshot file not found for VQA analysis",
                "analysis_type": "vqa",
            }

        with open(screenshot_path, "rb") as f:
            image_bytes = f.read()

        # Run VQA analysis
        vqa_result = run_desktop_vqa_analysis(
            question=question,
            image_bytes=image_bytes,
            media_type="image/png",
        )

        result["analysis_type"] = "vqa"
        result["question"] = question
        result["answer"] = vqa_result.answer
        result["confidence"] = vqa_result.confidence
        result["observations"] = vqa_result.observations

        # Auto-refine logic: if confidence low, retry with grid
        if auto_refine and vqa_result.confidence < confidence_threshold:
            from ..rich_emit import emit_rich

            emit_rich(
                f"🔄 Confidence {vqa_result.confidence:.2f} below threshold {confidence_threshold:.2f}, "
                f"retrying with grid overlay"
            )

            # Retry with grid at increasing densities
            grid_densities = [
                ("low", 100),
                ("medium", 50),
                ("high", 25),
            ]

            for density_name, spacing in grid_densities:
                # Recapture with grid
                screenshot_result_grid = screenshot(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    window_title=window_title,
                    mode=mode,
                    add_grid=True,
                    grid_spacing=spacing,
                )

                if screenshot_result_grid.success:
                    with open(screenshot_result_grid.screenshot_path, "rb") as f:
                        image_bytes_grid = f.read()

                    vqa_result_grid = run_desktop_vqa_analysis(
                        question=question,
                        image_bytes=image_bytes_grid,
                        media_type="image/png",
                    )

                    emit_rich(
                        f"📊 Grid density '{density_name}' ({spacing}px): "
                        f"confidence {vqa_result_grid.confidence:.2f}"
                    )

                    # If confidence improved, use this result
                    if vqa_result_grid.confidence >= confidence_threshold:
                        result["answer"] = vqa_result_grid.answer
                        result["confidence"] = vqa_result_grid.confidence
                        result["observations"] = vqa_result_grid.observations
                        result["screenshot_path"] = (
                            screenshot_result_grid.screenshot_path
                        )
                        result["grid_refined"] = True
                        result["grid_density"] = density_name
                        break

                    # If last iteration, use best result even if below threshold
                    if spacing == 25:  # Last iteration
                        if vqa_result_grid.confidence > vqa_result.confidence:
                            result["answer"] = vqa_result_grid.answer
                            result["confidence"] = vqa_result_grid.confidence
                            result["observations"] = vqa_result_grid.observations
                            result["screenshot_path"] = (
                                screenshot_result_grid.screenshot_path
                            )
                            result["grid_refined"] = True
                            result["grid_density"] = density_name

    return result


def _compact_vqa_result(
    full_result: "VQAResult",
    truncate_answer: bool = True,
    max_answer_length: int = 1000,  # Increased: 500 → 1000 for better error debugging
) -> "VQAResult":
    """
    Compress VQA result to minimal data with structured summary.

    Strategy:
    - Keep question, answer, confidence
    - Smart truncation: Don't truncate low-confidence responses (likely debugging info)
    - Truncate high-confidence to max_answer_length (default: 1000 chars)
    - Keep screenshot path only (strip full metadata)
    - Remove verbose screenshot_info details
    - Generate structured CompactSummary

    Args:
        full_result: Full VQA result with all metadata
        truncate_answer: Whether to truncate long answers (default: True)
        max_answer_length: Maximum answer length in chars (default: 1000)

    Returns:
        Compact VQA result with essentials and structured summary
    """
    from ..result_types import VQAResult

    # Smart truncation: Don't truncate low-confidence responses (debugging info)
    answer = full_result.answer
    was_truncated = False
    if truncate_answer and answer and len(answer) > max_answer_length:
        # Don't truncate if low confidence (likely contains debugging details)
        if full_result.confidence and full_result.confidence < 0.7:
            # Low confidence - keep full answer for debugging
            pass
        else:
            # High confidence - safe to truncate
            answer = (
                answer[:max_answer_length]
                + "... (truncated. Use truncate_answer=False for full response)"
            )
            was_truncated = True

    # Generate structured summary
    summary = CompactSummary(
        tool="vqa",
        success=full_result.success,
        timestamp=datetime.now().isoformat(),
        found_count=1,  # Single VQA response
        returned_count=1,
        filtered_count=0,
        one_line=f"VQA confidence: {full_result.confidence:.0%}"
        if full_result.confidence
        else "VQA response",
        compaction_ratio=1.0,  # No elements filtered, just metadata stripped
        filters_applied=["metadata_stripped"],
        thresholds={
            "max_answer_length": max_answer_length,
            "smart_truncation_threshold": 0.7,
        },
        confidence_stats={
            "confidence": full_result.confidence if full_result.confidence else 0.0,
        },
        detail_hint="Low confidence responses not truncated for debugging"
        if full_result.confidence and full_result.confidence < 0.7
        else None,
        progressive_hints=[
            "Screenshot saved for review at: "
            + (
                full_result.screenshot_info.path
                if full_result.screenshot_info
                else "N/A"
            ),
            "Use truncate_answer=False for full response" if was_truncated else None,
        ],
        extra={
            "answer_length": len(answer) if answer else 0,
            "was_truncated": was_truncated,
            "coordinate_system": full_result.coordinate_system,
        },
    )

    return VQAResult(
        success=full_result.success,
        question=full_result.question,
        answer=answer,
        confidence=full_result.confidence,
        screenshot_path=full_result.screenshot_info.path
        if full_result.screenshot_info
        else None,
        summary=summary.model_dump(),
        error=full_result.error,
        # Explicitly exclude verbose fields
        observations=None,
        screenshot_info=None,
        window_bounds=None,
        coordinate_system=full_result.coordinate_system,
    )
