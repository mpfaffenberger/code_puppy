"""Tests for the Chat Completions video-content patch.

The contract under test:
- A ``video/*`` ``BinaryContent`` and a ``VideoUrl`` become OpenRouter-style
  ``video_url`` chat content parts on OpenAI-*compatible* endpoints.
- First-party OpenAI-family identities keep pydantic-ai's original, more
  informative ``NotImplementedError``.
- An explicit ``openai_chat_supports_video_input`` profile boolean wins over
  the identity heuristic, in both directions.
- Non-video binary content is untouched (pydantic-ai still maps it).
- Oversized videos fail fast with an actionable ``UserError``.
- A missing pydantic-ai internal is a loud failure, not a crash.
"""

import logging

import pytest
from pydantic_ai import BinaryContent, VideoUrl
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.openai import OpenAIChatModel

from code_puppy import pydantic_patches
from code_puppy._pydantic_video_patch import (
    FIRST_PARTY_OPENAI_IDENTITIES,
    MAX_INLINE_VIDEO_BYTES,
    chat_completions_accepts_video,
    video_content_part,
)
from code_puppy.provider_identity import make_openai_provider

LOGGER_NAME = "code_puppy.pydantic_patches"

VIDEO_BYTES = b"\x00\x01fake-mp4"


@pytest.fixture(autouse=True)
def _patched():
    """Apply the patch for every test (and leave the class patched)."""
    assert pydantic_patches.patch_openai_chat_video_url() is True


def _model(system: str, profile: dict | None = None):
    """A real OpenAIChatModel wired to *system*'s base URL."""
    base_urls = {
        "openai": "https://api.openai.com/v1",
        "synthetic": "https://api.synthetic.new/openai/v1/",
    }
    return OpenAIChatModel(
        "some-model",
        provider=make_openai_provider(
            system,
            api_key="sk-not-real",
            base_url=base_urls.get(system, "https://x/v1"),
        ),
        profile=profile,
    )


# ---------------------------------------------------------------------------
# The happy path: this is the regression (NotImplementedError on attach).
# ---------------------------------------------------------------------------


async def test_local_video_becomes_inline_video_url_part():
    part = await OpenAIChatModel._map_binary_content_item(
        _model("synthetic"), BinaryContent(data=VIDEO_BYTES, media_type="video/mp4")
    )

    assert part["type"] == "video_url"
    assert part["video_url"]["url"].startswith("data:video/mp4;base64,")


async def test_remote_video_url_passes_through_untouched():
    item = VideoUrl(url="https://cdn.test/clip.mp4")

    part = await OpenAIChatModel._map_video_url_item(_model("synthetic"), item)

    assert part == {
        "type": "video_url",
        "video_url": {"url": "https://cdn.test/clip.mp4"},
    }


async def test_force_download_inlines_the_remote_video(monkeypatch):
    """``force_download`` opts into bytes-on-the-wire, like OpenRouterModel."""
    calls = []

    async def fake_safe_download(url, *, allow_local, max_bytes):
        calls.append((url, allow_local, max_bytes))
        return _FakeResponse(b"\x00\x01downloaded", "video/mp4")

    monkeypatch.setattr("pydantic_ai._ssrf.safe_download", fake_safe_download)
    item = VideoUrl(url="https://cdn.test/clip.mp4", force_download=True)

    part = await OpenAIChatModel._map_video_url_item(_model("synthetic"), item)

    assert calls == [("https://cdn.test/clip.mp4", False, 50 * 1024 * 1024)]
    assert part["video_url"]["url"].startswith("data:video/mp4;base64,")


async def test_map_messages_emits_video_parts_end_to_end():
    """The exact path that used to blow up: UserPromptPart -> chat body."""
    messages = [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "what is in this clip?",
                        BinaryContent(data=VIDEO_BYTES, media_type="video/mp4"),
                        VideoUrl(url="https://cdn.test/clip.mp4"),
                    ]
                )
            ]
        )
    ]

    body = await _model("synthetic")._map_messages(messages, ModelRequestParameters())

    assert [part["type"] for part in body[0]["content"]] == [
        "text",
        "video_url",
        "video_url",
    ]


# ---------------------------------------------------------------------------
# First-party OpenAI keeps the honest client-side error.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("system", sorted(FIRST_PARTY_OPENAI_IDENTITIES))
async def test_first_party_openai_keeps_not_implemented_error(system):
    with pytest.raises(NotImplementedError):
        await OpenAIChatModel._map_video_url_item(
            _model(system), VideoUrl(url="https://cdn.test/clip.mp4")
        )

    with pytest.raises(NotImplementedError):
        await OpenAIChatModel._map_binary_content_item(
            _model(system), BinaryContent(data=VIDEO_BYTES, media_type="video/mp4")
        )


async def test_profile_flag_forces_video_on_for_first_party():
    model = _model("openai", {"openai_chat_supports_video_input": True})

    part = await OpenAIChatModel._map_video_url_item(
        model, VideoUrl(url="https://cdn.test/clip.mp4")
    )

    assert part["type"] == "video_url"


async def test_profile_flag_forces_video_off_for_a_gateway():
    model = _model("synthetic", {"openai_chat_supports_video_input": False})

    with pytest.raises(NotImplementedError):
        await OpenAIChatModel._map_video_url_item(
            model, VideoUrl(url="https://cdn.test/clip.mp4")
        )


# ---------------------------------------------------------------------------
# Everything else keeps going through pydantic-ai untouched.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "media_type,data,expected_type",
    [
        ("image/png", b"\x89PNG", "image_url"),
        ("application/pdf", b"%PDF-1.7", "file"),
        ("text/plain", b"hello", "text"),
    ],
)
async def test_non_video_binary_content_still_maps_via_pydantic_ai(
    media_type, data, expected_type
):
    part = await OpenAIChatModel._map_binary_content_item(
        _model("synthetic"), BinaryContent(data=data, media_type=media_type)
    )

    assert part["type"] == expected_type


async def test_oversized_video_fails_fast_with_an_actionable_error():
    item = BinaryContent(
        data=b"0" * (MAX_INLINE_VIDEO_BYTES + 1), media_type="video/mp4"
    )

    with pytest.raises(UserError) as excinfo:
        await OpenAIChatModel._map_binary_content_item(_model("synthetic"), item)

    message = str(excinfo.value)
    assert "over the 20 MB inline limit" in message
    assert "http(s) URL" in message


# ---------------------------------------------------------------------------
# Helper-level contract.
# ---------------------------------------------------------------------------


def test_accepts_video_is_false_when_the_model_looks_broken():
    class Exploding:
        @property
        def profile(self):
            raise RuntimeError("nope")

    assert chat_completions_accepts_video(Exploding()) is False


def test_video_content_part_shape():
    assert video_content_part("https://cdn.test/clip.mp4") == {
        "type": "video_url",
        "video_url": {"url": "https://cdn.test/clip.mp4"},
    }


# ---------------------------------------------------------------------------
# Loud failure: a missing pydantic-ai internal must not crash, and must say so.
# ---------------------------------------------------------------------------


def test_missing_pydantic_internal_logs_loudly(monkeypatch, caplog):
    monkeypatch.delattr(OpenAIChatModel, "_map_video_url_item")

    with caplog.at_level(logging.ERROR, logger=LOGGER_NAME):
        result = pydantic_patches.patch_openai_chat_video_url()  # must NOT raise

    assert result is False
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("patch_openai_chat_video_url" in m for m in errors)


class _FakeResponse:
    """Minimal stand-in for the httpx response ``safe_download`` returns."""

    def __init__(self, content: bytes, content_type: str):
        self.content = content
        self.headers = {"content-type": content_type}
