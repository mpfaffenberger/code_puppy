"""Token estimation for binary attachments in code_puppy.agents._history.

The estimator reduces a BinaryContent to a 16-hex-char digest for hashing, so
without a separate charge a full-page screenshot scores about as much as the
word "screenshot". That undercount propagates into compact()'s threshold, the
50k-per-message rule in filter_huge_messages, and the /context badge, so a
session carrying a handful of images can sail past the real context limit and
die on a provider 400 with compaction having never run.
"""

import io

import pytest
from PIL import Image
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents._history import (
    _BINARY_CONTENT_FALLBACK_TOKENS,
    estimate_binary_content_tokens,
    estimate_tokens_for_message,
    hash_message,
    stringify_part,
)


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buf, format="PNG")
    return buf.getvalue()


def _image_message(*images: bytes) -> ModelRequest:
    return ModelRequest(
        parts=[
            UserPromptPart(
                content=[
                    BinaryContent(data=data, media_type="image/png") for data in images
                ]
            )
        ]
    )


def test_large_image_estimates_in_the_thousands():
    # A 2048x2048 screenshot is worth thousands of tokens to any vision model.
    # Before binary charging it scored 16, the length of its digest string.
    tokens = estimate_tokens_for_message(_image_message(_png(2048, 2048)))
    assert tokens > 5000


def test_image_estimate_scales_with_area():
    # Compare the binary charge itself. A whole-message comparison would be
    # muddied by the fixed digest string, which dominates a tiny image.
    small = estimate_binary_content_tokens(
        BinaryContent(data=_png(64, 64), media_type="image/png")
    )
    large = estimate_binary_content_tokens(
        BinaryContent(data=_png(1024, 1024), media_type="image/png")
    )
    # 256x the pixels. Not exactly 256x the charge: the small image's 5.46
    # tokens floor to 5, so the ratio comes out a little above 256.
    assert large > small * 250


def test_many_screenshots_accumulate():
    one = estimate_tokens_for_message(_image_message(_png(1024, 1024)))
    twenty = estimate_tokens_for_message(_image_message(*[_png(1024, 1024)] * 20))
    assert twenty > one * 15


def test_unreadable_image_falls_back_rather_than_undercounting():
    item = BinaryContent(data=b"definitely not a png", media_type="image/png")
    assert estimate_binary_content_tokens(item) == _BINARY_CONTENT_FALLBACK_TOKENS


def test_non_image_binary_uses_fallback():
    item = BinaryContent(data=b"%PDF-1.4 ...", media_type="application/pdf")
    assert estimate_binary_content_tokens(item) == _BINARY_CONTENT_FALLBACK_TOKENS


def test_text_only_message_estimate_is_unchanged():
    # Guard against the binary charge leaking into ordinary messages.
    message = ModelRequest(parts=[UserPromptPart(content="hello puppy")])
    assert estimate_tokens_for_message(message) == 12


def test_binary_content_still_hashes_by_digest():
    # The charge is additive; stringify_part must keep emitting the digest so
    # existing dedup hashes stay stable.
    data = _png(32, 32)
    part = _image_message(data).parts[0]
    assert "BinaryContent=" in stringify_part(part)


def test_differing_images_still_hash_differently():
    assert hash_message(_image_message(_png(32, 32))) != hash_message(
        _image_message(_png(64, 64))
    )


class _UnknownItem:
    """Stands in for ImageUrl / DocumentUrl / whatever pydantic-ai adds next."""

    def __init__(self, url: str):
        self.url = url

    def __repr__(self) -> str:
        return f"_UnknownItem(url={self.url!r})"


def test_unknown_list_items_do_not_collide():
    # Without the else arm in stringify_part these both reduced to
    # "user-prompt" and hashed identically, so distinct pages deduped away.
    a = ModelRequest(parts=[UserPromptPart(content=[_UnknownItem("https://a/1.png")])])
    b = ModelRequest(parts=[UserPromptPart(content=[_UnknownItem("https://b/2.png")])])
    assert stringify_part(a.parts[0]) != stringify_part(b.parts[0])
    assert hash_message(a) != hash_message(b)


@pytest.mark.parametrize("media_type", ["image/png", "image/jpeg", "image/webp"])
def test_common_image_types_are_measured(media_type):
    fmt = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[media_type]
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), "blue").save(buf, format=fmt)
    item = BinaryContent(data=buf.getvalue(), media_type=media_type)
    # Measured from real dimensions, so distinctly not the blind fallback.
    assert estimate_binary_content_tokens(item) == (800 * 600) // 750
