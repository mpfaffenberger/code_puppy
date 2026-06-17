"""Image-file clipboard attachment helpers.

These cover the LIVE Windows/macOS path where the clipboard yields a list of
file paths (Pillow ``ImageGrab.grabclipboard`` behavior) rather than a native
image object. The capture is funneled through ``get_clipboard_image`` ->
``_image_file_list_to_png_bytes`` -> ``get_image_file_as_png``.
"""

from __future__ import annotations

import pytest

from code_puppy.command_line import clipboard


@pytest.fixture(autouse=True)
def _reset_clipboard_manager(monkeypatch):
    monkeypatch.setattr(clipboard, "_clipboard_manager", None)
    monkeypatch.setattr(clipboard, "_last_clipboard_capture", 0.0)


def _write_png(path):
    if not clipboard.PIL_AVAILABLE or clipboard.Image is None:
        pytest.skip("Pillow not available")
    image = clipboard.Image.new("RGB", (3, 2), color="red")
    image.save(path, format="PNG")


def test_get_clipboard_image_reads_file_list_from_imagegrab(tmp_path, monkeypatch):
    image_path = tmp_path / "screenclip.png"
    _write_png(image_path)
    if clipboard.ImageGrab is None:
        pytest.skip("ImageGrab not available")

    monkeypatch.setattr(clipboard.sys, "platform", "win32")
    monkeypatch.setattr(clipboard.ImageGrab, "grabclipboard", lambda: [str(image_path)])

    image_bytes = clipboard.get_clipboard_image()

    assert image_bytes is not None
    assert image_bytes.startswith(b"\x89PNG")


def test_get_image_file_as_png_rejects_non_image_suffix(tmp_path):
    text_path = tmp_path / "not-an-image.txt"
    text_path.write_text("nope", encoding="utf-8")

    assert clipboard.get_image_file_as_png(str(text_path)) is None
