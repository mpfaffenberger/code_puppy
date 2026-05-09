"""MCP secret-validation and config-redaction helpers.

Extracted from ``managed_server.py`` to keep both modules under the
600-line cap while concentrating all secret-safety logic in one place.
"""

from __future__ import annotations

import logging as _logging
import re
from typing import Any, Dict, Optional

from code_puppy.security.redaction import REDACTED, SENSITIVE_KEYS, redact_secrets

_MCP_LOGGER = _logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded-secret heuristics (used by both validation and redaction)
# ---------------------------------------------------------------------------

# Heuristic patterns that suggest a hardcoded secret rather than an env-var
# reference.  Kept in lowercase; comparison is case-insensitive.
_SECRET_HEURISTICS: tuple[str, ...] = (
    "sk-",  # OpenAI
    "sk_live_",  # Stripe
    "ghp_",  # GitHub PAT
    "gho_",  # GitHub OAuth
    "xoxb-",  # Slack bot
    "xoxp-",  # Slack app
    "akia",  # AWS access key ID prefix
    "aiza",  # Google API key
    "key-",  # generic key prefix
)

# Pattern for env-var references ($VAR or ${VAR}) so we can strip them
# before checking for hardcoded secrets.
_ENV_VAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}")


# ---------------------------------------------------------------------------
# Hardcoded-secret detection (validation / warnings)
# ---------------------------------------------------------------------------


def _contains_hardcoded_secret(value: str) -> Optional[str]:
    """Return the matching prefix if *value* contains a hardcoded secret.

    Env-var references (``$VAR`` / ``${VAR}``) are stripped before
    checking.  Each whitespace-separated token is examined so that
    ``Bearer sk-abc`` is caught (the ``sk-`` token, not the leading
    ``Bearer``).

    Returns the matched prefix string, or ``None`` if no secret is found.
    """
    cleaned = _ENV_VAR_RE.sub("", value)
    for token in cleaned.split():
        lower_token = token.lower()
        for prefix in _SECRET_HEURISTICS:
            if lower_token.startswith(prefix.lower()):
                return prefix
    return None


def _validate_no_hardcoded_secrets(
    values: Dict[str, str], server_name: str, source: str = "header"
) -> None:
    """Warn if *values* dict contains values that look like hardcoded API keys.

    Values that reference environment variables (``$VAR`` / ``${VAR}``) are
    considered safe because the secret lives outside the config file.
    Bare literal strings matching known key prefixes raise a warning.
    """
    for name, value in values.items():
        if not isinstance(value, str):
            continue
        match = _contains_hardcoded_secret(value)
        if match:
            _MCP_LOGGER.warning(
                "MCP server %r %s %r appears to contain a hardcoded secret "
                "(prefix %r). Use environment variable references ($VAR) instead.",
                server_name,
                source,
                name,
                match,
            )


def _validate_env_list_secrets(env_list: list, server_name: str) -> None:
    """Warn if env list entries contain hardcoded secrets in their values.

    Each entry is expected to be a ``"KEY=VALUE"`` string; the value
    portion (after the first ``=``) is checked for known secret prefixes.
    """
    for entry in env_list:
        if not isinstance(entry, str) or "=" not in entry:
            continue
        key, _, val = entry.partition("=")
        match = _contains_hardcoded_secret(val)
        if match:
            _MCP_LOGGER.warning(
                "MCP server %r env %r appears to contain a hardcoded secret "
                "(prefix %r). Use environment variable references ($VAR) instead.",
                server_name,
                key,
                match,
            )


# ---------------------------------------------------------------------------
# Config redaction (status output must never leak secrets)
# ---------------------------------------------------------------------------


def _key_is_sensitive(key: str) -> bool:
    """True when *key* (from a headers or env dict) looks sensitive.

    Handles both hyphenated HTTP-header conventions (``X-API-Key``,
    ``Authorization``, ``Auth-Token``) and ``UPPER_SNAKE_CASE`` env-var
    conventions (``OPENAI_API_KEY``, ``MY_SECRET``).

    Normalisation: hyphens → underscores, then lowercase, then check
    whether any ``SENSITIVE_KEYS`` token appears as a substring.
    ``X-API-Key`` → ``x_api_key`` which contains ``api_key`` ✓
    ``auth-token``  → ``auth_token`` which contains ``token`` ✓
    """
    normalised = key.lower().replace("-", "_")
    for sensitive in SENSITIVE_KEYS:
        if sensitive in normalised:
            return True
    return False


def _value_contains_secret(value: Any) -> bool:
    """True when *value* looks like it embeds a secret.

    Detects:
    - Bearer / Basic authentication values (``Bearer sk-...``, ``Basic ...``)
    - Known secret prefixes in any whitespace-separated token (``sk-...``)
    - Env-var references (``$VAR``) are **not** treated as secrets here
      because they resolve at runtime to potentially-sensitive values that
      the caller already validated via ``_validate_no_hardcoded_secrets``.
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    # Bearer / Basic auth patterns
    if stripped.lower().startswith(("bearer ", "basic ")):
        return True
    # Direct secret-prefix match (after stripping env-var refs)
    return _contains_hardcoded_secret(value) is not None


def _redact_header_env_dict(d: dict) -> dict:
    """Redact a headers or env dict, key-sensitivity + value-scanning."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if _key_is_sensitive(k) or _value_contains_secret(v):
            out[k] = REDACTED
        else:
            out[k] = v
    return out


def _redact_env_list_entry(entry: str) -> str:
    """Redact a single ``"KEY=VALUE"`` env-list string if needed.

    Splits on the first ``=``.  The entry is redacted when either the
    key is sensitive (per ``_key_is_sensitive``) **or** the value
    contains a secret (per ``_value_contains_secret``).  Otherwise the
    original entry is returned unchanged after applying the general
    ``redact_secrets`` pass (to catch env-assignment patterns like
    ``OPENAI_API_KEY=sk-...`` that the dict-based matcher already
    handles).
    """
    if "=" not in entry:
        return redact_secrets(entry)
    key, sep, val = entry.partition("=")
    if _key_is_sensitive(key) or _value_contains_secret(val):
        return f"{key}{sep}{REDACTED}"
    # Still run the general pass for patterns redact_secrets covers
    # (e.g. nested bearer tokens, URL query params).
    return redact_secrets(entry)


def redact_mcp_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *config* with sensitive values redacted.

    Headers and env dicts often contain API keys; these must never
    appear verbatim in status output or logs.  The redaction helper
    scrubs:

    * Dict keys matching known sensitive names (including hyphenated
      variants like ``X-API-Key`` → ``api_key``).
    * Dict **values** that contain Bearer/Basic auth or known secret
      prefixes, even when the key name itself is not sensitive
      (e.g. ``{"X-Custom": "sk-abc"}``).
    * Env-list entries (``"KEY=VALUE"`` strings) whose key is
      sensitive or whose value contains a secret, redacting the
      value to ``<redacted>``.
    * Non-header/env values (e.g. ``url`` with ``?api_key=secret``
      query params, nested JSON strings) via ``redact_secrets()``.
    """
    redacted: Dict[str, Any] = {}
    for key, value in config.items():
        if key in ("headers", "env") and isinstance(value, dict):
            redacted[key] = _redact_header_env_dict(value)
        elif key == "env" and isinstance(value, list):
            redacted[key] = [
                _redact_env_list_entry(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            # Apply full redaction to catch URL query params,
            # bearer tokens in strings, nested JSON secrets, etc.
            redacted[key] = redact_secrets(value)
    return redacted
