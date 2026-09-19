"""Shared safe interpolation grammar for rendering and catalog validation."""

from __future__ import annotations

import re
from collections.abc import Mapping

# Catalogs are untrusted. Only escaped braces and bare identifier fields are
# interpreted; attribute/index access, conversions, and format specs stay text.
FIELD_RE = re.compile(r"\{\{|\}\}|\{(\w+)\}")


def placeholder_names(text: str) -> frozenset[str]:
    """Return fields recognized by the runtime interpolation grammar."""
    return frozenset(
        match.group(1) for match in FIELD_RE.finditer(text) if match.group(1)
    )


def interpolate(text: str, params: Mapping[str, object]) -> str:
    """Safely substitute known bare ``{name}`` fields and preserve unknowns."""

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        name = match.group(1)
        if name in params:
            return str(params[name])
        return token

    return FIELD_RE.sub(replace, text)
