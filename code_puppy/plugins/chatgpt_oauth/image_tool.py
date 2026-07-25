"""Agent-facing Codex OAuth image-generation tool."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic_ai import RunContext

from .image_generation import (
    CodexImageGenerationError,
    emit_iterm_image,
    generate_image,
)

TOOL_NAME = "codex_imagegen"


def register_codex_imagegen(agent: Any) -> None:
    """Register image generation on a pydantic-ai agent."""

    @agent.tool
    async def codex_imagegen(
        context: RunContext,
        prompt: str,
        reference_images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a raster image using gpt-image-2 and Codex OAuth.

        Use this when the user asks you to create a photo, illustration, icon,
        sprite, texture, product image, banner, or other raster artwork. Write a
        complete standalone visual prompt because the image model does not see
        the conversation. The PNG is saved automatically and displayed inline
        in iTerm2 when supported.

        Pass ``reference_images`` to condition the result on existing images
        instead of generating from text alone. Reach for it whenever the output
        must stay visually consistent with something that already exists:

        * the SAME character across multiple images (portraits, expressions,
          poses) — conditioning on a canonical reference holds identity far
          better than re-describing the face in words;
        * matching an established art style, palette, or lighting;
        * iterating on an existing asset ("same logo, but on a dark
          background").

        Args:
            prompt: Detailed standalone description of the image to generate.
            reference_images: Optional paths to existing image files to
                condition on. Describe the CHANGE you want in ``prompt``; the
                references supply the subject and style to preserve.
        """
        del context
        try:
            output_path = await asyncio.to_thread(
                generate_image, prompt, reference_images
            )
        except CodexImageGenerationError as exc:
            return {"success": False, "error": str(exc)}

        displayed_inline = emit_iterm_image(output_path)
        return {
            "success": True,
            "path": str(output_path),
            "displayed_inline": displayed_inline,
        }


def register_tools_callback() -> list[dict[str, Any]]:
    return [{"name": TOOL_NAME, "register_func": register_codex_imagegen}]
