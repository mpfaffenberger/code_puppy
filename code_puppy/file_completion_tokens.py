"""Attachment token boundaries and shell-compatible completion insertion."""

import shlex


def _opens_quote(text: str, i: int, symbol: str) -> bool:
    """Decide whether the quote character at ``text[i]`` starts a quoted span.

    Quotes group characters only when they begin a word (start of input or
    right after whitespace) or immediately follow the attachment symbol —
    the two positions a user quotes a filename from. A quote embedded in a
    word (the apostrophe in ``don't``) is ordinary prose and must never open
    quote state, or it would swallow later whitespace and hide the active
    ``@token`` boundary.
    """
    if i == 0 or text[i - 1].isspace():
        return True
    return i >= len(symbol) and text[i - len(symbol) : i] == symbol


def active_reference(text: str, symbol: str = "@"):
    """Return decoded path and raw replacement length, or no active reference.

    Only a token beginning with @ qualifies. Within the active token, spaces
    require quotes or escaping; a closed quote ends completion so subsequent
    prose is never replaced. Apostrophes in surrounding prose (contractions)
    are literal characters and never open a quote.
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
            if _opens_quote(text, i, symbol):
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
