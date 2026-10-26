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

# ``key: value`` / ``key=value`` / ``'key': 'value'`` where the key names a credential. An
# optional auth scheme before the value is swallowed so the scheme does not hide the secret.
_CREDENTIAL_PAIR = re.compile(
    r"(api[_-]?key|secret|password|passwd|authorization|token)([\w.-]*['\"]?\s*[:=]\s*['\"]?)"
    r"(?:(?:bearer|basic|token)\s+)?[^\s'\",;&)}\]]+",
    re.IGNORECASE,
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
# /Users/<name>, /home/<name>, C:\Users\<name>; repr() doubles backslashes, hence ``+``.
# The lookbehind keeps URL paths such as ``https://host/home/x`` intact.
_HOME_PATH = re.compile(
    r"(?<![\w.\-])(?:[A-Za-z]:)?[\\/]+(?:Users|home)[\\/]+[^\\/\s'\"]+"
)


@lru_cache(maxsize=4)
def _current_home(home: str) -> re.Pattern[str] | None:
    segments = [re.escape(part) for part in re.split(r"[\\/]+", home) if part]
    if len(segments) < 2:  # "/" or a bare drive root would erase every path
        return None
    prefix = r"[\\/]+" if home[0] in "\\/" else ""
    return re.compile(prefix + r"[\\/]+".join(segments), re.IGNORECASE)


def redact(text: str) -> str:
    """Replace credentials and the user's home directory in *text*; layout is preserved."""
    text = _CREDENTIAL_PAIR.sub(rf"\1\2{REDACTED}", text)
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    text = _URL_CREDENTIALS.sub(rf"\1{REDACTED}\2", text)
    text = _TOKEN_SHAPE.sub(REDACTED, text)
    own_home = _current_home(os.path.expanduser("~"))
    if own_home is not None:
        text = own_home.sub("~", text)
    return _HOME_PATH.sub("~", text)
