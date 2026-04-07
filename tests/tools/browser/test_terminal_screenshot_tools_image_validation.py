import io

import pytest
from PIL import Image
from pydantic_ai import BinaryContent, ToolReturn

from code_puppy.tools.browser.terminal_screenshot_tools import (
    MAX_IMAGE_EDGE,
    load_image,
)


def _make_image_bytes(fmt: str, size: tuple[int, int], color: str = "red") -> bytes:
    image = Image.new("RGB", size, color=color)
    output = io.BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


@pytest.mark.asyncio
async def test_load_image_rejects_non_image(tmp_path):
    bad_file = tmp_path / "not-really-an-image.png"
    bad_file.write_bytes(b"definitely not image bytes lol")

    result = await load_image(str(bad_file))

    assert result["success"] is False
    assert "valid image" in result["error"].lower()


@pytest.mark.asyncio
async def test_load_image_uses_actual_mime_type_for_real_image(tmp_path):
    jpeg_file = tmp_path / "photo.jpg"
    jpeg_file.write_bytes(_make_image_bytes("JPEG", (320, 200)))

    result = await load_image(str(jpeg_file))

    assert isinstance(result, ToolReturn)
    image_content = next(
        item for item in result.content if isinstance(item, BinaryContent)
    )
    assert image_content.media_type == "image/jpeg"
    assert result.metadata["media_type"] == "image/jpeg"
    assert result.metadata["actual_media_type"] == "image/jpeg"
    assert result.metadata["mime_type_matches_extension"] is True
    assert result.metadata["was_resized"] is False
    assert result.metadata["output_size"] == [320, 200]


@pytest.mark.asyncio
async def test_load_image_resizes_gigantic_images_to_max_edge(tmp_path):
    huge_file = tmp_path / "massive.jpg"
    huge_file.write_bytes(_make_image_bytes("JPEG", (5000, 3000)))

    result = await load_image(str(huge_file))

    assert isinstance(result, ToolReturn)
    image_content = next(
        item for item in result.content if isinstance(item, BinaryContent)
    )
    assert image_content.media_type == "image/png"
    assert result.metadata["media_type"] == "image/png"
    assert result.metadata["actual_media_type"] == "image/jpeg"
    assert result.metadata["was_resized"] is True
    assert max(result.metadata["output_size"]) == MAX_IMAGE_EDGE
    assert result.metadata["original_size"] == [5000, 3000]

    resized_image = Image.open(io.BytesIO(image_content.data))
    assert resized_image.format == "PNG"
    assert resized_image.size == tuple(result.metadata["output_size"])
