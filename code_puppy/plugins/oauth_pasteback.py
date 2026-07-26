"""Helpers for OAuth flows that support terminal paste-back."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class ParsedOAuthCallback:
    """Parsed authorization result from a pasted callback URL or code."""

    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None
    error_description: Optional[str] = None

    @property
    def error_message(self) -> Optional[str]:
        if not self.error:
            return None
        if self.error_description:
            return f"{self.error}: {self.error_description}"
        return self.error


def _first(params: dict[str, list[str]], name: str) -> Optional[str]:
    values = params.get(name)
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _looks_like_query(value: str) -> bool:
    if value.startswith("?"):
        return True
    return "=" in value and (
        "&" in value or value.startswith(("code=", "state=", "error="))
    )


def parse_oauth_callback_input(raw_input: str) -> ParsedOAuthCallback:
    """Parse pasted OAuth input into code/state/error fields.

    Supported inputs include full callback URLs, raw query strings, Claude's
    ``code#state`` and ``code state`` console formats, and bare codes.
    """
    value = raw_input.strip()
    if not value:
        raise ValueError("Authorization code cannot be empty")

    parsed_url = urlparse(value)
    query = parsed_url.query
    if query or _looks_like_query(value):
        params = parse_qs(query or value.lstrip("?"), keep_blank_values=False)
        result = ParsedOAuthCallback(
            code=_first(params, "code"),
            state=_first(params, "state"),
            error=_first(params, "error"),
            error_description=_first(params, "error_description"),
        )
        if result.code or result.error:
            return result
        raise ValueError("No authorization code found in pasted OAuth input")

    if "#" in value:
        code, state = value.split("#", 1)
        code = code.strip()
        state = state.strip() or None
        if not code:
            raise ValueError("Authorization code cannot be empty")
        return ParsedOAuthCallback(code=code, state=state)

    parts = value.split()
    if len(parts) == 2:
        return ParsedOAuthCallback(code=parts[0].strip(), state=parts[1].strip())
    if len(parts) > 2:
        raise ValueError("Pasted OAuth input has too many whitespace-separated parts")

    return ParsedOAuthCallback(code=value)


def read_available_stdin_line() -> Optional[str]:
    """Return one stdin line when available without blocking.

    The OAuth callback server can complete in parallel, so the auth flow must
    not block indefinitely on input. This helper is intentionally POSIX-only;
    Windows callers still retain browser callback behavior and explicit timeout.
    """
    if os.name == "nt":
        return None

    try:
        import select

        readable, _, _ = select.select([sys.stdin], [], [], 0)
    except (OSError, ValueError):
        return None

    if not readable:
        return None

    line = sys.stdin.readline()
    if line == "":
        return None
    return line.rstrip("\r\n")
