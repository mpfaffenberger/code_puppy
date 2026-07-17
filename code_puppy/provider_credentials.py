"""Shared helpers for discovering and managing provider API-key credentials.

Single source of truth for: which env var each configured provider/model needs,
whether it is currently set (mirroring ``model_factory.get_api_key`` precedence:
mist.cfg first, then ``os.environ``), a masked display value, and saving a new
value so it takes effect immediately (mist.cfg + current-process env).

Used by:
- the ``/model`` picker and ``/add_model`` browser, to view/edit keys, and
- ``config.load_api_keys_to_environment``, to hydrate every referenced key.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


def extract_env_var_from_model_config(model_config: dict) -> Optional[str]:
    """Return the ``$ENV`` key a single model config depends on, if any.

    Mirrors ``model_factory`` resolution: a credential is referenced as a
    string of the form ``"$ENV_NAME"`` either at the top-level ``api_key`` or
    nested under ``custom_endpoint.api_key``. Returns the env var name without
    the leading ``$`` (e.g. ``"FIREWORKS_API_KEY"``), or ``None``.
    """
    if not isinstance(model_config, dict):
        return None

    candidates = []
    # Prefer custom_endpoint.api_key over top-level api_key (mirrors model_factory)
    custom_endpoint = model_config.get("custom_endpoint")
    if isinstance(custom_endpoint, dict):
        endpoint_key = custom_endpoint.get("api_key")
        if isinstance(endpoint_key, str):
            candidates.append(endpoint_key)

    top_level = model_config.get("api_key")
    if isinstance(top_level, str):
        candidates.append(top_level)

    for value in candidates:
        if value.startswith("$"):
            env_var = value[1:].strip()
            if env_var:
                return env_var
    return None


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
        env_var = extract_env_var_from_model_config(model_config)
        if not env_var:
            continue
        provider = str(model_config.get("provider") or "unknown")
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

    mist.cfg (case-insensitive key) first, then ``os.environ``.
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
    """Persist a credential to mist.cfg and apply it to the current process.

    Stored under the lowercase key (so ``get_value(env_var.lower())`` resolves
    it) and exported to ``os.environ`` so it is effective without a restart.
    """
    from code_puppy.config import set_config_value

    value = (value or "").strip()
    set_config_value(env_var.lower(), value)
    if value:
        os.environ[env_var] = value


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
