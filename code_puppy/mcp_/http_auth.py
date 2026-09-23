"""Explicit, opt-in OAuth for remote MCP transports.

FastMCP owns discovery, PKCE, state validation, browser callbacks and refresh.
Tokens stay in memory; no credentials are written to server configuration.
"""

import warnings
from urllib.parse import urlsplit

from fastmcp.client.auth import OAuth

from code_puppy.i18n import t

# In-memory tokens are the deliberate choice above, so FastMCP's nudge toward a
# persistent backend (emitted from OAuth._bind when the transport is built) is
# pure console noise. Scoped to this exact message, not a blanket ignore; no
# module scoping because stacklevel attributes it to the transport module.
warnings.filterwarnings(
    "ignore",
    message=r"Using in-memory token storage .*",
    category=UserWarning,
)


def http_auth(config: dict, url: str, headers: dict | None) -> OAuth | None:
    """Build authentication without initiating a login or network request."""
    method = config.get("auth")
    if method is None:
        return None
    if method != "oauth":
        raise ValueError(t("mcp.oauth.invalid_method"))
    if any(key.lower() == "authorization" for key in (headers or {})):
        raise ValueError(t("mcp.oauth.header_conflict"))
    parsed = urlsplit(url)
    loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError(t("mcp.oauth.https_required"))
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(t("mcp.oauth.https_required"))
    return OAuth(client_name="Code Puppy", callback_host="127.0.0.1")
