"""Helpers for the Chat Completions video-content patch.

pydantic-ai's ``OpenAIChatModel`` refuses video outright: both ``VideoUrl``
parts and ``BinaryContent`` with a ``video/*`` media type raise
``NotImplementedError``.  That refusal is CORRECT for api.openai.com --
OpenAI's Chat Completions API has no video content part at all -- but it is
wrong as a blanket rule for the OpenAI-*compatible* endpoints code-puppy also
talks to (OpenRouter, synthetic.new, Cerebras, self-hosted gateways), several
of which accept the OpenRouter-style ``video_url`` part.  pydantic-ai itself
proves the wire format works: ``OpenRouterModel`` overrides both mappers to
emit ``{"type": "video_url", "video_url": {"url": ...}}``, and the openai SDK
passes the part straight through to the JSON body.

So the failure is a model-*class* limitation, not a protocol one.

This module holds the pure helpers; ``pydantic_patches`` holds the wiring.
Split out (like ``_pydantic_tool_helpers``) to keep the patch module inside
the project's 600-line budget.
"""

from typing import Any

# Provider identities (see ``code_puppy.provider_identity``) that are
# first-party OpenAI-family APIs.  Their Chat Completions surface really has
# no video part, so the original ``NotImplementedError`` is the most useful
# thing we can say -- a 400 from the API would be strictly less informative.
# Everything else (custom endpoints, gateways, OpenRouter, ...) gets the
# benefit of the doubt: we send ``video_url`` and let the provider answer.
FIRST_PARTY_OPENAI_IDENTITIES = frozenset(
    {
        "openai",
        "chatgpt",
        "azure_openai",
        "azure_foundry_openai",
    }
)

# Largest video we will base64-inline into a request body. 20 MiB is the
# strictest common inline budget (Gemini caps the entire request at 20MB);
# past that a request is a guaranteed failure or a multi-minute stall, so we
# fail fast with something actionable instead.
MAX_INLINE_VIDEO_BYTES = 20 * 1024 * 1024

# Profile key pydantic-ai would use if it ever grows first-class video
# support.  Reading it means the patch keeps working (and follows an upstream
# decision) if that lands, and it doubles as the manual override for
# self-hosted endpoints we cannot recognise by provider name.
VIDEO_INPUT_PROFILE_KEY = "openai_chat_supports_video_input"


def chat_completions_accepts_video(model: Any) -> bool:
    """Return True when *model*'s endpoint may accept a ``video_url`` part.

    An explicit boolean in the model profile always wins; otherwise every
    provider that is not first-party OpenAI-family gets the ``video_url``
    part.  Never raises: the video path is already a degraded path, and a
    crash here would be worse than the original ``NotImplementedError``.
    """
    try:
        override = model.profile.get(VIDEO_INPUT_PROFILE_KEY)
        if isinstance(override, bool):
            return override
        return model.system not in FIRST_PARTY_OPENAI_IDENTITIES
    except Exception:
        return False


def video_content_part(url: str) -> dict[str, Any]:
    """Build the OpenRouter-style ``video_url`` chat content part.

    Not part of the openai SDK's ``ChatCompletionContentPartParam`` union --
    exactly the gap ``OpenRouterModel`` documents -- but the SDK serializes
    the dict as-is, so the part reaches the wire verbatim.
    """
    return {"type": "video_url", "video_url": {"url": url}}


def inline_video_url(item: Any) -> str:
    """Return a base64 data URI for a video ``BinaryContent``.

    Raises ``UserError`` (pydantic-ai's "this is your fault, not a bug"
    exception) for videos too large to inline -- see
    :data:`MAX_INLINE_VIDEO_BYTES`.
    """
    from pydantic_ai.exceptions import UserError

    size = len(item.data)
    if size > MAX_INLINE_VIDEO_BYTES:
        raise UserError(
            f"Video attachment is {size / 1024 / 1024:.1f} MB, over the "
            f"{MAX_INLINE_VIDEO_BYTES // 1024 // 1024} MB inline limit. Attach an "
            "http(s) URL to the video instead -- the URL is then passed through "
            "to the model as-is instead of being base64-inlined -- or trim the clip."
        )
    return item.data_uri
