"""Scrub credentials and home-directory paths from text persisted to ``errors.log``.

Best-effort pattern matching, not a guarantee: it covers the shapes that show up in
exception text, tracebacks and ``Args`` reprs, and it must stay linear-time because it
runs on the failure path. Called by: ``error_format::_redact_head``.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

REDACTED = "[REDACTED]"

# ``key: value`` / ``key=value`` / ``'key': 'value'`` where the key names a credential. A quoted
# value is consumed whole (spaces, commas, escaped quotes; an unterminated one runs to the
# end), including one whose delimiters repr() escaped (``b'password=\'x\''``); a bare one
# may carry an auth scheme, which is dropped. ``(?!\[REDACTED\])`` keeps a second pass
# over already-redacted text from adding a stray bracket.
#
# Whether a backslash-quote closes a value depends on how many escaping layers (source
# literal, then repr) the text went through, and that cannot be known here. So the
# matching is conservative: a plain quote closes the value only when no backslash precedes
# it, and for a repr-escaped quote only a lone backslash-quote closes it. Ambiguous text
# therefore redacts more than strictly needed, never less. Possessive quantifiers and the
# bounded key suffix keep the scan linear (a longer suffix is not a realistic credential name).
_CREDENTIAL_PAIR = re.compile(
    r"(api[_-]?key|secret|password|passwd|authorization|token)([\w.-]{0,64}+['\"]?\s*[:=]\s*)"
    r"(?:(?P<quoted>"
    r"\\(?P<esc>['\"])(?:[^\\]|\\{2,}+(?P=esc)?|\\(?!\\|(?P=esc)))*+(?:\\(?P=esc)|$)"
    r"|\"(?:[^\"\\]|\\++\"?)*+\"?"
    r"|'(?:[^'\\]|\\++'?)*+'?)"
    r"|(?:(?:bearer|basic|token)\s+)?(?!\[REDACTED\])[^\s'\",;&)}\]]+)",
    re.IGNORECASE | re.DOTALL,
)
_BEARER = re.compile(r"\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_URL_CREDENTIALS = re.compile(r"(://[^/\s:@]+:)[^@\s/]+(@)")
# Well-known token shapes that appear without a naming key (min lengths avoid prose).
_TOKEN_SHAPE = re.compile(
    r"\b(?:(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_\w{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,})"
)
# /Users/<name>, /home/<name>, C:\Users\<name>; repr() doubles backslashes, hence ``++``.
# The lookbehind keeps URL paths such as ``https://host/home/x`` intact, and excluding
# separators from it means only the start of a separator run is tried (linear scan).
HOME_PLACEHOLDER = "<home>"
_HOME_PATH = re.compile(
    r"(?<![\w.\-\\/])(?:[A-Za-z]:)?[\\/]++(?:Users|home)[\\/]++[^\\/\s'\"]+"
)
# A name continuing after the home (``bobby``, ``bob.old``) is a different user.
_SEGMENT_END = r"(?![\w\-]|\.\w)"


@lru_cache(maxsize=4)
def _current_home(home: str) -> re.Pattern[str] | None:
    segments = [re.escape(part) for part in re.split(r"[\\/]+", home) if part]
    if len(segments) < 2:  # "/" or a bare drive root would erase every path
        return None
    prefix = r"(?<![\\/])[\\/]++" if home[0] in "\\/" else ""
    return re.compile(prefix + r"[\\/]++".join(segments) + _SEGMENT_END, re.IGNORECASE)


def _redact_pair(match: re.Match[str]) -> str:
    quoted = match["quoted"] or ""
    quote = quoted[:2] if match["esc"] else quoted[:1]
    return f"{match[1]}{match[2]}{quote}{REDACTED}{quote}"


def redact(text: str) -> str:
    """Replace credentials and the user's home directory in *text*; layout is preserved."""
    text = _CREDENTIAL_PAIR.sub(_redact_pair, text)
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    text = _URL_CREDENTIALS.sub(rf"\1{REDACTED}\2", text)
    text = _TOKEN_SHAPE.sub(REDACTED, text)
    own_home = _current_home(os.path.expanduser("~"))
    if own_home is not None:
        text = own_home.sub("~", text)
    return _HOME_PATH.sub(HOME_PLACEHOLDER, text)
