"""Image generation through the ChatGPT Codex OAuth backend.

Two endpoints are used, both on the Codex backend rather than api.openai.com:

``POST /images/generations``
    Plain text-to-image. JSON body ``{model, prompt, size, quality,
    background}``.

``POST /images/edits``
    Reference-conditioned generation — the model sees one or more input images
    and preserves their subject/style. JSON body ``{model, prompt, images,
    size, quality}`` where ``images`` is a list of OBJECTS, each with exactly
    one accepted key, ``image_url``, holding a base64 data-URL string::

        {"images": [{"image_url": "data:image/png;base64,iVBORw0..."}]}

.. note::
   This endpoint is undocumented and its request shape was derived empirically
   against the live service (2026-07). Deviations are rejected with HTTP 400:
   a singular ``image`` key reports "Missing required parameter: 'images'";
   bare base64 strings report "expected an object, but got a string";
   ``url`` / ``b64_json`` / ``data`` / ``type`` object keys report "Unknown
   parameter"; and multipart/form-data uploads (the shape the public OpenAI
   images API uses) are rejected outright. If reference conditioning starts
   failing, re-probe those variants first — and note that unknown keys on
   ``/images/generations`` are silently IGNORED rather than rejected, so a
   wrong shape there fails open as an unconditioned image.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests

from code_puppy import config
from code_puppy.i18n import t

from .config import CHATGPT_OAUTH_CONFIG
from .utils import get_valid_access_token, load_stored_tokens

_IMAGE_MODEL = "gpt-image-2"
_REQUEST_TIMEOUT_SECONDS = 180

# Guard against pathologically large payloads: references are inlined as base64
# data URLs, so a huge file becomes a huge request body.
_MAX_REFERENCE_BYTES = 20 * 1024 * 1024


class CodexImageGenerationError(RuntimeError):
    """A safe, user-displayable image generation failure."""


def generate_image(
    prompt: str, reference_images: Sequence[str | Path] | None = None
) -> Path:
    """Generate one image with Codex OAuth and save it under Code Puppy data.

    Args:
        prompt: The image description.
        reference_images: Optional paths to existing images. When provided, the
            request goes to ``/images/edits`` and the model conditions on them,
            preserving subject identity and style far better than describing the
            subject in words. When omitted, behavior is unchanged: a plain
            text-to-image call to ``/images/generations``.

    Returns:
        Path to the saved PNG.
    """
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise CodexImageGenerationError(t("codex.imagegen.prompt_required"))

    access_token = get_valid_access_token()
    tokens = load_stored_tokens() or {}
    account_id = str(tokens.get("account_id", "")).strip()
    if not access_token or not account_id:
        raise CodexImageGenerationError(t("codex.imagegen.auth_required"))

    encoded_references = _encode_references(reference_images or ())
    response = _post_generation_request(
        access_token, account_id, normalized_prompt, encoded_references
    )
    image_bytes = _decode_first_image(response)
    return _save_image(image_bytes)


def _encode_references(paths: Iterable[str | Path]) -> list[str]:
    """Read reference images and return them as base64 data-URL strings."""
    encoded: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise CodexImageGenerationError(
                t("codex.imagegen.reference_missing", path=str(path))
            )
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CodexImageGenerationError(
                t("codex.imagegen.reference_unreadable", path=str(path))
            ) from exc
        if len(data) > _MAX_REFERENCE_BYTES:
            raise CodexImageGenerationError(
                t("codex.imagegen.reference_too_large", path=str(path))
            )
        mime, _ = mimetypes.guess_type(str(path))
        if not (mime or "").startswith("image/"):
            mime = "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        encoded.append(f"data:{mime};base64,{b64}")
    return encoded


def _post_generation_request(
    access_token: str,
    account_id: str,
    prompt: str,
    reference_data_urls: Sequence[str] | None = None,
) -> dict[str, Any]:
    base_url = str(CHATGPT_OAUTH_CONFIG["api_base_url"]).rstrip("/")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "ChatGPT-Account-Id": account_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "originator": CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs"),
        "User-Agent": (
            f"{CHATGPT_OAUTH_CONFIG.get('originator', 'codex_cli_rs')}/"
            f"{CHATGPT_OAUTH_CONFIG.get('client_version', 'unknown')}"
        ),
    }
    if reference_data_urls:
        # Reference-conditioned edit: `images` entries must be `{"image_url": ...}`
        # objects only; `background` isn't accepted on this endpoint.
        endpoint = "/images/edits"
        payload = {
            "prompt": prompt,
            "model": _IMAGE_MODEL,
            "images": [{"image_url": url} for url in reference_data_urls],
            "quality": "auto",
            "size": "auto",
        }
    else:
        endpoint = "/images/generations"
        payload = {
            "prompt": prompt,
            "background": "auto",
            "model": _IMAGE_MODEL,
            "quality": "auto",
            "size": "auto",
        }

    try:
        response = requests.post(
            f"{base_url}{endpoint}",
            headers=headers,
            json=payload,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except requests.RequestException as exc:
        detail = _response_error_detail(getattr(exc, "response", None))
        suffix = f": {detail}" if detail else ""
        raise CodexImageGenerationError(
            t("codex.imagegen.request_failed", detail=suffix)
        ) from exc
    except ValueError as exc:
        raise CodexImageGenerationError(t("codex.imagegen.invalid_json")) from exc

    if not isinstance(body, dict):
        raise CodexImageGenerationError(t("codex.imagegen.invalid_response"))
    return body


def _response_error_detail(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip()[:300]
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message", ""))[:300]
    return str(error or body.get("detail", ""))[:300]


def _decode_first_image(body: dict[str, Any]) -> bytes:
    data = body.get("data")
    encoded = data[0].get("b64_json") if isinstance(data, list) and data else None
    if not isinstance(encoded, str) or not encoded:
        raise CodexImageGenerationError(t("codex.imagegen.no_data"))
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CodexImageGenerationError(t("codex.imagegen.malformed_data")) from exc


def emit_iterm_image(output_path: Path) -> bool:
    """Display a saved image with iTerm2's OSC 1337 inline-image protocol."""
    if not _is_iterm2() or not sys.stdout.isatty():
        return False

    try:
        image_data = base64.b64encode(output_path.read_bytes()).decode("ascii")
        encoded_name = base64.b64encode(output_path.name.encode()).decode("ascii")
        sequence = (
            f"\033]1337;File=name={encoded_name};inline=1;"
            f"preserveAspectRatio=1:{image_data}\a\n"
        )
        from code_puppy.messaging.run_ui import suspended_run_ui

        with suspended_run_ui():
            sys.stdout.write(sequence)
            sys.stdout.flush()
    except Exception:
        # Inline display is best-effort; the image remains safely saved even if
        # terminal detection lied or the active UI cannot be suspended.
        return False
    return True


def _is_iterm2() -> bool:
    return bool(
        os.environ.get("ITERM_SESSION_ID")
        or os.environ.get("TERM_PROGRAM", "").lower() == "iterm.app"
    )


def _save_image(image_bytes: bytes) -> Path:
    output_dir = Path(config.DATA_DIR) / "generated_images"
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path = output_dir / f"codex-{uuid.uuid4().hex}.png"
    temporary_path = output_path.with_suffix(".tmp")
    try:
        temporary_path.write_bytes(image_bytes)
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(output_path)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise CodexImageGenerationError(t("codex.imagegen.save_failed")) from exc
    return output_path
