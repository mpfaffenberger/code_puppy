"""Parse ACP prompt content blocks into a Code Puppy prompt.

The client delivers a prompt as a list of typed content blocks. The SDK parses
the wire into pydantic models before our ``prompt`` handler runs, so we work
with objects (``TextContentBlock``, ``ImageContentBlock``,
``EmbeddedResourceContentBlock``, …) rather than raw dicts.

We split a prompt into three parts that map onto ``run_with_mcp``'s signature:

* **text** — text blocks, embedded text resources (spliced in under a header,
  honouring the advertised ``embeddedContext`` capability), and resource-link
  references.
* **attachments** — image blocks carrying base64 data → pydantic-ai
  ``BinaryContent`` (honouring the advertised ``image`` capability).
* **link_attachments** — image blocks carrying only a URI → ``ImageUrl``.

Blocks are duck-typed (``getattr``) so a newer SDK adding fields never breaks
parsing. Audio is not advertised, so audio blocks degrade to a text note.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, List

logger = logging.getLogger(__name__)


@dataclass
class ParsedPrompt:
    """A prompt split into text + multimodal attachments for ``run_with_mcp``."""

    text: str = ""
    attachments: List[Any] = field(default_factory=list)  # BinaryContent
    link_attachments: List[Any] = field(default_factory=list)  # ImageUrl


def parse_prompt(blocks: List[Any]) -> ParsedPrompt:
    """Split a list of ACP content blocks into text + attachments."""
    parts: List[str] = []
    result = ParsedPrompt()
    for block in blocks or []:
        text = _render_block(block, result)
        if text:
            parts.append(text)
    result.text = "\n\n".join(parts)
    return result


def flatten_prompt(blocks: List[Any]) -> str:
    """Back-compat text-only view (used where attachments aren't needed)."""
    return parse_prompt(blocks).text


def _render_block(block: Any, result: ParsedPrompt) -> str:
    block_type = getattr(block, "type", None)

    if block_type == "text":
        return getattr(block, "text", "") or ""

    if block_type == "resource":
        return _render_embedded_resource(getattr(block, "resource", None))

    if block_type == "resource_link":
        uri = getattr(block, "uri", "") or ""
        name = getattr(block, "name", "") or uri
        return f"[Referenced resource: {name} ({uri})]" if uri else ""

    if block_type == "image":
        _collect_image(block, result)
        return ""

    if block_type == "audio":
        return "[Audio attached]"

    # Unknown/newer block type: fall back to any ``text`` it carries.
    return getattr(block, "text", "") or ""


def _collect_image(block: Any, result: ParsedPrompt) -> None:
    """Turn an image block into a BinaryContent (data) or ImageUrl (uri)."""
    data = getattr(block, "data", None)
    mime = getattr(block, "mime_type", None) or "image/png"
    if data:
        try:
            from pydantic_ai import BinaryContent

            result.attachments.append(
                BinaryContent(data=base64.b64decode(data), media_type=mime)
            )
            return
        except Exception:  # noqa: BLE001
            logger.debug("ACP: could not decode image data", exc_info=True)
    uri = getattr(block, "uri", None)
    if uri:
        try:
            from pydantic_ai import ImageUrl

            result.link_attachments.append(ImageUrl(url=uri))
        except Exception:  # noqa: BLE001
            logger.debug("ACP: could not build ImageUrl", exc_info=True)


def _render_embedded_resource(resource: Any) -> str:
    """Render an embedded resource; only the text variant carries usable text."""
    if resource is None:
        return ""
    text = getattr(resource, "text", None)
    if not text:
        uri = getattr(resource, "uri", "") or ""
        return f"[Embedded binary resource: {uri}]" if uri else ""
    uri = getattr(resource, "uri", "") or "embedded"
    return f"<context uri={uri!r}>\n{text}\n</context>"
