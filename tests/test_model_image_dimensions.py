"""Dimension limits apply even when screenshots compress to only a few KB."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from code_puppy.command_line.image_utils import normalize_image_bytes


def png(size):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("size", [(2002, 1120), (3840, 2160), (6000, 40), (40, 6000)])
def test_small_byte_images_obey_dimension_limit_and_aspect_ratio(size):
    data = png(size)
    assert len(data) < 100_000
    normalized, mime = normalize_image_bytes(data, "image/png")
    with Image.open(io.BytesIO(normalized)) as image:
        assert max(image.size) <= 2000
        scale = 2000 / max(size)
        assert image.size == tuple(max(1, int(edge * scale)) for edge in size)
    assert mime == "image/png"


@pytest.mark.parametrize("size", [(1920, 1080), (2000, 2000)])
def test_in_bounds_bytes_unchanged(size):
    data = png(size)
    assert normalize_image_bytes(data, "image/png") == (data, "image/png")


async def test_browser_normalizes_payload_but_preserves_saved_capture(
    monkeypatch, tmp_path
):
    from code_puppy.tools.browser import browser_screenshot

    data = png((3840, 2160))
    page = SimpleNamespace(screenshot=AsyncMock(return_value=data))
    manager = SimpleNamespace(get_current_page=AsyncMock(return_value=page))
    monkeypatch.setattr(
        browser_screenshot, "get_session_browser_manager", lambda: manager
    )
    path = tmp_path / "capture.png"
    monkeypatch.setattr(
        browser_screenshot, "_build_screenshot_path", lambda stamp: path
    )
    result = await browser_screenshot.take_screenshot()
    assert path.read_bytes() == data
    with Image.open(io.BytesIO(result.content[1].data)) as image:
        assert image.size == (2000, 1125)


def test_file_loader_uses_shared_limit():
    from code_puppy.tools.image_tools import MAX_IMAGE_EDGE

    assert MAX_IMAGE_EDGE == 2000


def test_linux_clipboard_normalizes_small_byte_capture(monkeypatch):
    from code_puppy.command_line import clipboard

    data = png((2002, 1120))
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard, "_get_linux_clipboard_image", lambda: data)
    result = clipboard.get_clipboard_image()
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (2000, 1118)


def test_linux_clipboard_reencodes_oversized_encoding(monkeypatch):
    from code_puppy.command_line import clipboard

    buf = io.BytesIO()
    Image.new("RGB", (2000, 2000), "white").save(buf, format="PNG", compress_level=0)
    data = buf.getvalue()
    assert len(data) > clipboard.MAX_IMAGE_SIZE_BYTES
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard, "_get_linux_clipboard_image", lambda: data)
    result = clipboard.get_clipboard_image()
    assert len(result) < clipboard.MAX_IMAGE_SIZE_BYTES
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (2000, 2000)


def test_file_loader_normalizes_cmyk_when_new_limit_requires_resize():
    from code_puppy.tools.image_tools import MAX_IMAGE_EDGE, _validate_and_prepare_image

    buf = io.BytesIO()
    Image.new("CMYK", (2048, 1024)).save(buf, format="JPEG")
    result = _validate_and_prepare_image(buf.getvalue(), max_edge=MAX_IMAGE_EDGE)
    assert result["media_type"] == "image/png"
    with Image.open(io.BytesIO(result["image_bytes"])) as image:
        assert image.size == (2000, 1000)
        assert image.mode == "RGB"
