"""Attachment token boundaries and shell-compatible completion insertion."""

import shlex


def _opens_quote(text: str, i: int, symbol: str, token_start: int) -> bool:
    """Decide whether the quote character at ``text[i]`` starts a quoted span.

    Quotes group characters at word boundaries and anywhere within an
    attachment token, including partially quoted paths like ``@dir/"my file``.
    A quote embedded in ordinary prose (the apostrophe in ``don't``) must
    never open quote state and hide a later attachment boundary.
    """
    if i == 0 or text[i - 1].isspace():
        return True
    return text.startswith(symbol, token_start, i)


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
            if _opens_quote(text, i, symbol, start):
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
