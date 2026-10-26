"""Best-effort output-cap inference for Claude models models.dev has not indexed.

The bundled models.dev snapshot lags behind new Claude releases, and a guessed
15%-of-context cap starves adaptive-thinking models of output budget. A model
of a known family borrows the cap of the newest *known* sibling that is not
newer than itself. This is an inference, not a guarantee.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

from code_puppy.models_dev_parser import ModelInfo

ANTHROPIC_CATALOG_TYPES = frozenset({"anthropic", "custom_anthropic"})
ANTHROPIC_PROVIDER_ID = "anthropic"

_FAMILIES = frozenset({"opus", "sonnet", "haiku"})
_SNAPSHOT_SUFFIX = re.compile(r"\d{8}|latest")

Version = tuple[int, ...]


def parse_claude_alias(model_id: str) -> Optional[tuple[str, Version]]:
    """Split a Claude id into ``(family, version)``, whichever order it uses.

    Handles ``claude-opus-5-5``, ``claude-5-opus``, ``claude-3-7-sonnet-latest``
    and dated snapshot ids. Anything else (unknown family, stray words) is
    ``None``.
    """
    parts = str(model_id).lower().split("-")
    if len(parts) < 2 or parts[0] != "claude":
        return None
    rest = parts[1:]
    if _SNAPSHOT_SUFFIX.fullmatch(rest[-1]):
        rest = rest[:-1]
    families = [part for part in rest if part in _FAMILIES]
    numbers = [part for part in rest if part not in _FAMILIES]
    if len(families) != 1 or not numbers or not all(n.isdigit() for n in numbers):
        return None
    return families[0], tuple(int(n) for n in numbers)


def infer_family_output_cap(
    model_id: str, catalog_type: str, models: Iterable[ModelInfo]
) -> Optional[int]:
    """Output cap of the newest known Anthropic sibling not newer than ``model_id``.

    Returns ``None`` when the entry is not Anthropic-backed, the id is not a
    recognisable Claude alias, no older-or-equal sibling is known, or the
    siblings at the chosen version disagree on the cap.
    """
    if catalog_type not in ANTHROPIC_CATALOG_TYPES:
        return None
    target = parse_claude_alias(model_id)
    if target is None:
        return None
    family, target_version = target

    caps_by_version: dict[Version, set[int]] = defaultdict(set)
    for model in models:
        if model.provider_id != ANTHROPIC_PROVIDER_ID or model.max_output <= 0:
            continue
        sibling = parse_claude_alias(model.model_id)
        if sibling is None or sibling[0] != family or sibling[1] > target_version:
            continue
        caps_by_version[sibling[1]].add(model.max_output)

    if not caps_by_version:
        return None
    caps = caps_by_version[max(caps_by_version)]
    return next(iter(caps)) if len(caps) == 1 else None


__all__ = ["infer_family_output_cap", "parse_claude_alias"]
