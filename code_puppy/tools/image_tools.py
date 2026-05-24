"""Image loading tool for visual analysis.

Provides ``load_image_for_analysis`` — a tiny generic tool that reads an image
from disk, validates it, downsizes it if it's billboard-sized, and returns it
as a ``ToolReturn`` with ``BinaryContent`` so multimodal models can see it.

Lives outside the browser package because it has nothing to do with browsers.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any, Dict, Union

from PIL import Image, UnidentifiedImageError
from pydantic_ai import BinaryContent, RunContext, ToolReturn

from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.common import generate_group_id

logger = logging.getLogger(__name__)

# Bigger than this on either edge and we resize to save tokens.
MAX_IMAGE_EDGE = 2048
DEFAULT_MAX_HEIGHT = 768  # kept for backward-compat in tool signature


def _validate_and_prepare_image(
    image_bytes: bytes,
    source_path: str | None = None,
    max_edge: int | None = None,
) -> Dict[str, Any]:
    """Verify image bytes, determine the real MIME type, and optionally resize.

    The MIME type is determined from the decoded image content, not from the
    file extension. If the image is resized, the output is normalized to PNG so
    the returned bytes and MIME type stay in sync like civilized software.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as verified_image:
            verified_image.verify()
    except UnidentifiedImageError as exc:
        raise ValueError("File is not a valid image") from exc
    except Exception as exc:
        raise ValueError(f"Failed to verify image: {exc}") from exc

    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load()
        original_width, original_height = image.size
        image_format = image.format
        actual_media_type = Image.MIME.get(image_format or "")

        if not actual_media_type or not actual_media_type.startswith("image/"):
            raise ValueError("Could not determine a valid image MIME type")

        guessed_media_type = None
        if source_path:
            guessed_media_type, _ = mimetypes.guess_type(source_path)

        largest_edge = max(original_width, original_height)
        was_resized = False
        output_bytes = image_bytes
        output_media_type = actual_media_type
        output_width = original_width
        output_height = original_height

        if max_edge and largest_edge > max_edge:
            ratio = max_edge / largest_edge
            output_width = max(1, int(round(original_width * ratio)))
            output_height = max(1, int(round(original_height * ratio)))
            resized = image.resize(
                (output_width, output_height), Image.Resampling.LANCZOS
            )
            output = io.BytesIO()
            resized.save(output, format="PNG", optimize=True)
            output.seek(0)
            output_bytes = output.read()
            output_media_type = "image/png"
            was_resized = True

        return {
            "image_bytes": output_bytes,
            "media_type": output_media_type,
            "actual_media_type": actual_media_type,
            "guessed_media_type": guessed_media_type,
            "mime_type_matches_extension": guessed_media_type
            in (None, output_media_type),
            "original_width": original_width,
            "original_height": original_height,
            "output_width": output_width,
            "output_height": output_height,
            "was_resized": was_resized,
        }


async def load_image(
    image_path: str,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> Union[ToolReturn, Dict[str, Any]]:
    """Load an image from the filesystem for visual analysis."""
    group_id = generate_group_id("load_image", image_path)
    emit_info(f"LOAD IMAGE 🖼️ {image_path}", message_group=group_id)

    try:
        image_file = Path(image_path)

        if not image_file.exists():
            error_msg = f"Image file not found: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "image_path": image_path}

        if not image_file.is_file():
            error_msg = f"Path is not a file: {image_path}"
            emit_error(error_msg, message_group=group_id)
            return {"success": False, "error": error_msg, "image_path": image_path}

        image_bytes = image_file.read_bytes()
        prepared_image = _validate_and_prepare_image(
            image_bytes,
            source_path=str(image_file),
            max_edge=MAX_IMAGE_EDGE,
        )

        emit_success(f"Loaded image: {image_path}", message_group=group_id)

        return ToolReturn(
            return_value=f"Image loaded from: {image_path}",
            content=[
                f"Here's the image from {image_file.name}:",
                BinaryContent(
                    data=prepared_image["image_bytes"],
                    media_type=prepared_image["media_type"],
                ),
                "Please analyze what you see in this image.",
            ],
            metadata={
                "success": True,
                "image_path": image_path,
                "media_type": prepared_image["media_type"],
                "actual_media_type": prepared_image["actual_media_type"],
                "guessed_media_type": prepared_image["guessed_media_type"],
                "mime_type_matches_extension": prepared_image[
                    "mime_type_matches_extension"
                ],
                "was_resized": prepared_image["was_resized"],
                "original_size": [
                    prepared_image["original_width"],
                    prepared_image["original_height"],
                ],
                "output_size": [
                    prepared_image["output_width"],
                    prepared_image["output_height"],
                ],
                "max_height": max_height,
                "max_edge": MAX_IMAGE_EDGE,
                "timestamp": time.time(),
            },
        )

    except Exception as e:
        error_msg = f"Failed to load image: {str(e)}"
        emit_error(error_msg, message_group=group_id)
        logger.exception("Error loading image")
        return {"success": False, "error": error_msg, "image_path": image_path}


def register_load_image(agent):
    """Register the image loading tool."""

    @agent.tool
    async def load_image_for_analysis(
        context: RunContext,
        image_path: str,
    ) -> Union[ToolReturn, Dict[str, Any]]:
        """Load an image file so you can see and analyze it.

        Args:
            image_path: Path to the image file.

        Returns:
            ToolReturn with the image, or error dict.
        """
        return await load_image(image_path=image_path)
