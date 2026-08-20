"""Shared helpers for discovering and managing provider API-key credentials.

Single source of truth for: which env var each configured provider/model needs,
whether it is currently set (mirroring ``model_factory.get_api_key`` precedence:
puppy.cfg first, then ``os.environ``), a masked display value, and saving a new
value so it takes effect immediately (puppy.cfg + current-process env).

Used by:
- the ``/model`` picker and ``/add_model`` browser, to view/edit keys, and
- ``config.load_api_keys_to_environment``, to hydrate every referenced key.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


def _add_env_var_tokens(value: object, names: List[str]) -> None:
    """Append every ``$ENV`` name inside ``value`` to ``names`` (de-duplicated).

    Either a whole-value ``$ENV`` or, mirroring
    ``model_factory.get_custom_config``, a space-separated token that itself
    starts with ``$`` (the token in ``Authorization: Bearer $MY_SERVICE_TOKEN``).
    """
    if not isinstance(value, str):
        return
    if value.startswith("$"):
        env_var = value[1:].strip()
        if env_var and env_var not in names:
            names.append(env_var)
        return
    if "$" not in value:
        return
    for token in value.split(" "):
        if token.startswith("$"):
            env_var = token[1:].strip()
            if env_var and env_var not in names:
                names.append(env_var)


def extract_api_key_env_vars_from_model_config(model_config: dict) -> List[str]:
    """Every ``$ENV`` name a model's api_key fields reference.

    ``custom_endpoint.api_key`` then top-level ``api_key`` (mirrors
    ``model_factory.get_custom_config`` precedence) -- the credentials the
    agent authenticates with, excluding header env vars. Returns names without
    the leading ``$`` (e.g. ``"FIREWORKS_API_KEY"``), de-duplicated.
    """
    if not isinstance(model_config, dict):
        return []
    names: List[str] = []
    custom_endpoint = model_config.get("custom_endpoint")
    if isinstance(custom_endpoint, dict):
        _add_env_var_tokens(custom_endpoint.get("api_key"), names)
    _add_env_var_tokens(model_config.get("api_key"), names)
    return names


# custom_endpoint.headers whose NAME marks the value as a bearer/API credential.
# Only these header vars are scrubbed from the model's shell env; a non-secret
# header like X-Title / HTTP-Referer / $SITE_URL still reaches child commands.
_SECRET_HEADER_NAMES = frozenset(
    {"authorization", "proxy-authorization", "x-api-key", "api-key"}
)


def extract_secret_header_env_vars_from_model_config(
    model_config: dict,
) -> List[str]:
    """Every ``$ENV`` name a secret-named ``custom_endpoint.headers`` entry references.

    A header token that authenticates provider calls (``Authorization: Bearer
    $TOKEN``, ``X-Api-Key: $KEY``) is as sensitive as an api_key and must not
    ride into a model-triggered child shell. Header names outside
    :data:`_SECRET_HEADER_NAMES` are treated as non-secret (e.g. ``$SITE_URL``)
    and left in the child environment.
    """
    if not isinstance(model_config, dict):
        return []
    names: List[str] = []
    custom_endpoint = model_config.get("custom_endpoint")
    if isinstance(custom_endpoint, dict):
        headers = custom_endpoint.get("headers")
        if isinstance(headers, dict):
            for header_name, header_value in headers.items():
                if str(header_name).lower() in _SECRET_HEADER_NAMES:
                    _add_env_var_tokens(header_value, names)
    return names


def extract_env_vars_from_model_config(model_config: dict) -> List[str]:
    """Every ``$ENV`` name a single model config depends on.

    The api_key credentials (see
    :func:`extract_api_key_env_vars_from_model_config`) followed by any
    ``$ENV`` referenced in ``custom_endpoint.headers``. api_key names come
    first so :func:`extract_env_var_from_model_config` returns the real
    credential rather than a header var such as ``$SITE_URL``.
    """
    if not isinstance(model_config, dict):
        return []
    names = extract_api_key_env_vars_from_model_config(model_config)
    custom_endpoint = model_config.get("custom_endpoint")
    if isinstance(custom_endpoint, dict):
        headers = custom_endpoint.get("headers")
        if isinstance(headers, dict):
            for header_value in headers.values():
                _add_env_var_tokens(header_value, names)
    return names


def extract_env_var_from_model_config(model_config: dict) -> Optional[str]:
    """Return the primary ``$ENV`` key a single model config depends on, if any.

    The first of :func:`extract_env_vars_from_model_config`, or ``None``.
    """
    names = extract_env_vars_from_model_config(model_config)
    return names[0] if names else None


def _load_merged_model_config() -> Dict[str, dict]:
    """Load the merged model catalog (builtin + extra + plugin sources)."""
    try:
        from code_puppy.model_factory import ModelFactory

        config = ModelFactory.load_config()
        if isinstance(config, dict):
            return config
    except Exception:
        # Be resilient: a broken catalog must not break key hydration/UX.
        pass
    return {}


def required_env_vars_by_provider() -> Dict[str, List[str]]:
    """Map each configured provider id -> sorted list of required env vars.

    Only includes providers whose models reference a ``$ENV`` credential, so
    keyless/OAuth providers are naturally excluded.
    """
    grouped: Dict[str, set] = {}
    for _model_name, model_config in _load_merged_model_config().items():
        if not isinstance(model_config, dict):
            continue
        provider = str(model_config.get("provider") or "unknown")
        for env_var in extract_env_vars_from_model_config(model_config):
            grouped.setdefault(provider, set()).add(env_var)
    return {provider: sorted(vars_) for provider, vars_ in sorted(grouped.items())}


def required_env_var_for_model(model_name: str) -> Optional[str]:
    """Return the env var the named model needs, or ``None`` if keyless/unknown."""
    config = _load_merged_model_config()
    model_config = config.get(model_name)
    if not isinstance(model_config, dict):
        return None
    return extract_env_var_from_model_config(model_config)


def all_required_env_vars() -> List[str]:
    """Sorted list of every env var referenced by any configured model."""
    found: set = set()
    for vars_ in required_env_vars_by_provider().values():
        found.update(vars_)
    return sorted(found)


def all_api_key_env_vars() -> List[str]:
    """Sorted list of every model's api_key ``$ENV`` var (headers excluded).

    The header-free counterpart of :func:`all_required_env_vars`, used to build
    the child-shell scrub set so non-secret header vars (e.g. ``$SITE_URL``)
    still reach child commands.
    """
    found: set = set()
    for model_config in _load_merged_model_config().values():
        found.update(extract_api_key_env_vars_from_model_config(model_config))
    return sorted(found)


def all_secret_header_env_vars() -> List[str]:
    """Sorted list of every model's secret-header ``$ENV`` var.

    See :func:`extract_secret_header_env_vars_from_model_config`.
    """
    found: set = set()
    for model_config in _load_merged_model_config().values():
        found.update(extract_secret_header_env_vars_from_model_config(model_config))
    return sorted(found)


def get_credential_value(env_var: str) -> Optional[str]:
    """Resolve a credential exactly like ``model_factory.get_api_key``.

    puppy.cfg (case-insensitive key) first, then ``os.environ``.
    """
    from code_puppy.config import get_value

    config_value = get_value(env_var.lower())
    if config_value:
        return config_value
    return os.environ.get(env_var)


def is_credential_set(env_var: str) -> bool:
    """True if a non-empty value is resolvable for ``env_var``."""
    return bool(get_credential_value(env_var))


def mask_secret(value: Optional[str]) -> str:
    """Mask a secret for display, revealing only the last 4 characters."""
    if not value:
        return ""
    value = str(value)
    if len(value) <= 4:
        return "…" + value[-1:] if value else ""
    return "…" + value[-4:]


def credential_display(env_var: str) -> str:
    """Human-readable status string for an env var, e.g. ``set (…abcd)``."""
    value = get_credential_value(env_var)
    if value:
        return f"set ({mask_secret(value)})"
    return "not set"


def save_credential(env_var: str, value: str) -> None:
    """Persist a credential to puppy.cfg and apply it to the current process.

    Stored under the lowercase key (so ``get_value(env_var.lower())`` resolves
    it) and exported to ``os.environ`` so it is effective without a restart.
    """
    from code_puppy.config import set_config_value

    value = (value or "").strip()
    set_config_value(env_var.lower(), value)
    if value:
        os.environ[env_var] = value


# Every provider credential code_puppy manages a key for; mirrors the names in
# ``credential_hint``, plus SYN/AZURE keys hydrated by ``config``.
_WELL_KNOWN_CREDENTIAL_ENV_VARS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "DEEPSEEK_API_KEY",
        "TOGETHER_API_KEY",
        "FIREWORKS_API_KEY",
        "OPENROUTER_API_KEY",
        "PERPLEXITY_API_KEY",
        "CEREBRAS_API_KEY",
        "HUGGINGFACE_API_KEY",
        "XAI_API_KEY",
        "ZAI_API_KEY",
        "SYN_API_KEY",
        "AZURE_OPENAI_API_KEY",
    }
)


def credential_env_var_names() -> frozenset:
    """Every env var name that carries an agent provider credential.

    The well-known provider keys, every configured model's api_key ``$ENV``
    name, and every secret-named ``custom_endpoint.headers`` token (an
    ``Authorization``/``X-Api-Key`` bearer authenticates provider calls just as
    an api_key does), so the scrub below cannot miss a custom provider.
    Non-secret header vars (e.g. ``$SITE_URL``) are left out -- they belong to
    the user's shell. Recomputed on every call so any catalog change --
    including a hand-edit to ``extra_models.json`` -- takes effect immediately.

    Residual: MCP server secrets (``mcp_servers.json`` ``env``/``headers``
    ``$VAR`` references) are not folded in -- there is no clean way to tell a
    secret from a non-secret like ``$HOME``/``$PATH`` there, and scrubbing the
    latter would re-break tooling. Left for the maintainer to decide.
    """
    names = set(_WELL_KNOWN_CREDENTIAL_ENV_VARS)
    try:
        names.update(all_api_key_env_vars())
        names.update(all_secret_header_env_vars())
    except Exception:
        # A broken catalog must not break environment scrubbing.
        pass
    return frozenset(names)


def environment_without_credentials() -> Dict[str, str]:
    """``os.environ`` minus the agent's own provider credentials.

    Removes the well-known provider keys, every model's api_key ``$ENV`` var,
    and every secret-named ``custom_endpoint.headers`` token so a child process
    cannot inherit and exfiltrate the keys the agent authenticates with.
    Everything else passes through so routine tooling keeps working: the user's
    own ``GITHUB_TOKEN``, ``AWS_*`` and proxies, and non-secret header vars like
    ``$SITE_URL``.
    """
    credentials = credential_env_var_names()
    return {
        name: value for name, value in os.environ.items() if name not in credentials
    }


def credential_hint(env_var: str) -> str:
    """Return a help URL hint for common API keys (best-effort)."""
    hints = {
        "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
        "ANTHROPIC_API_KEY": "https://console.anthropic.com/",
        "GEMINI_API_KEY": "https://aistudio.google.com/apikey",
        "GOOGLE_API_KEY": "https://aistudio.google.com/apikey",
        "GROQ_API_KEY": "https://console.groq.com/keys",
        "MISTRAL_API_KEY": "https://console.mistral.ai/",
        "COHERE_API_KEY": "https://dashboard.cohere.com/api-keys",
        "DEEPSEEK_API_KEY": "https://platform.deepseek.com/",
        "TOGETHER_API_KEY": "https://api.together.xyz/settings/api-keys",
        "FIREWORKS_API_KEY": "https://fireworks.ai/api-keys",
        "OPENROUTER_API_KEY": "https://openrouter.ai/keys",
        "PERPLEXITY_API_KEY": "https://www.perplexity.ai/settings/api",
        "CEREBRAS_API_KEY": "https://cloud.cerebras.ai/",
        "HUGGINGFACE_API_KEY": "https://huggingface.co/settings/tokens",
        "XAI_API_KEY": "https://console.x.ai/",
        "ZAI_API_KEY": "https://z.ai/",
    }
    return hints.get(env_var, "")
