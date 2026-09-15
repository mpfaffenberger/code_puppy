"""Attachment token boundaries and shell-compatible completion insertion."""

import shlex


def active_reference(text: str, symbol: str = "@"):
    """Return decoded path and raw replacement length, or no active reference.

    Only a token beginning with @ qualifies. Spaces require quotes or escaping;
    a closed quote ends completion so subsequent prose is never replaced.
    """
    start = 0
    quote = None
    escaped = False
    closed = False
    for i, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
                closed = True
        elif char in "\"'":
            quote = char
        elif char.isspace():
            start = i + 1
            closed = False
    token = text[start:]
    if not token.startswith(symbol) or closed:
        return None
    raw = token[len(symbol) :]
    try:
        decoded = shlex.split(raw + (quote or "")) if raw else [""]
    except ValueError:
        return None
    return (decoded[0] if decoded else "", len(raw))


def quote_path(path: str) -> str:
    return shlex.quote(path)
