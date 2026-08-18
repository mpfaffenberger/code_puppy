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

import functools
import os
from typing import Dict, List, Optional


def extract_env_vars_from_model_config(model_config: dict) -> List[str]:
    """Every ``$ENV`` name a single model config depends on.

    Mirrors ``model_factory.get_custom_config``: ``custom_endpoint.api_key``,
    string values of ``custom_endpoint.headers`` (a whole-value ``$ENV`` or a
    space-separated token such as ``Authorization: Bearer $MY_SERVICE_TOKEN``),
    and the top-level ``api_key``. Returns env var names without the leading
    ``$`` (e.g. ``"FIREWORKS_API_KEY"``), de-duplicated in precedence order.
    """
    if not isinstance(model_config, dict):
        return []

    names: List[str] = []

    def _add(value: object) -> None:
        if not isinstance(value, str):
            return
        if value.startswith("$"):
            env_var = value[1:].strip()
            if env_var and env_var not in names:
                names.append(env_var)
            return
        if "$" not in value:
            return
        # Same split as model_factory.get_custom_config: only a space-
        # separated token that itself starts with ``$`` is a credential.
        for token in value.split(" "):
            if token.startswith("$"):
                env_var = token[1:].strip()
                if env_var and env_var not in names:
                    names.append(env_var)

    # Prefer custom_endpoint.api_key over top-level api_key (mirrors model_factory)
    custom_endpoint = model_config.get("custom_endpoint")
    if isinstance(custom_endpoint, dict):
        _add(custom_endpoint.get("api_key"))
        headers = custom_endpoint.get("headers")
        if isinstance(headers, dict):
            for header_value in headers.values():
                _add(header_value)
    _add(model_config.get("api_key"))
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


_WELL_KNOWN_CREDENTIAL_ENV_VARS = frozenset(
    {
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CEREBRAS_API_KEY",
        "SYN_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ZAI_API_KEY",
    }
)


@functools.lru_cache(maxsize=1)
def credential_env_var_names() -> frozenset:
    """Every env var name that carries an agent provider credential.

    The well-known provider keys plus every ``$ENV`` name referenced by a
    configured model (including custom-endpoint header credentials), so the
    scrub below cannot miss a custom provider. Cached because the model
    catalog is read from disk and this runs on every child-process spawn; a
    catalog edited mid-session applies after restart.
    """
    names = set(_WELL_KNOWN_CREDENTIAL_ENV_VARS)
    try:
        names.update(all_required_env_vars())
    except Exception:
        # A broken catalog must not break environment scrubbing.
        pass
    return frozenset(names)


def environment_without_credentials() -> Dict[str, str]:
    """``os.environ`` minus the agent's own provider credentials.

    Child shell commands and hooks have no legitimate use for the keys the
    agent itself authenticates with; removing them keeps a child process
    from inheriting and exfiltrating them. Everything else in the user's
    environment (``GITHUB_TOKEN``, ``AWS_*``, proxies) passes through so
    routine tooling keeps working.
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
