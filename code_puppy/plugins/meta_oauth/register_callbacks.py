"""Callbacks for Meta Muse OAuth authentication and model registration."""

from __future__ import annotations

from typing import Any

from code_puppy.callbacks import register_callback
from code_puppy.i18n import t
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from .config import FALLBACK_MODELS, META_OAUTH_CONFIG, get_token_storage_path
from .oauth_flow import run_oauth_flow
from .utils import discover_models, load_credentials

_PREFIX = str(META_OAUTH_CONFIG["prefix"])
_DEFAULT_MODEL = f"{_PREFIX}{META_OAUTH_CONFIG['default_model']}"
_model_cache: dict[str, dict[str, Any]] | None = None


def _custom_help() -> list[tuple[str, str]]:
    return [
        ("meta-auth", t("oauth.meta.help.auth")),
        ("meta-status", t("oauth.meta.help.status")),
        ("meta-logout", t("oauth.meta.help.logout")),
    ]


def _get_model_specs(credentials: dict[str, Any]) -> dict[str, dict[str, Any]]:
    global _model_cache
    stored = credentials.get("models")
    if isinstance(stored, dict):
        valid = {
            model_id: spec
            for model_id, spec in stored.items()
            if isinstance(model_id, str) and isinstance(spec, dict)
        }
        if valid:
            return valid
    if _model_cache is None:
        try:
            _model_cache = discover_models(credentials)
        except Exception:  # noqa: BLE001 - catalogue outage must not break startup
            _model_cache = dict(FALLBACK_MODELS)
    return _model_cache


def _meta_model_names(credentials: dict[str, Any] | None = None) -> list[str]:
    credentials = credentials or load_credentials()
    if not credentials:
        return []
    return [f"{_PREFIX}{model_id}" for model_id in _get_model_specs(credentials)]


def _load_meta_models() -> dict[str, Any]:
    """Inject Muse models when an API key is available."""
    credentials = load_credentials()
    if not credentials:
        return {}
    return {
        f"{_PREFIX}{model_id}": {
            "type": "meta_oauth",
            "provider": "meta",
            "name": model_id,
            "context_length": int(spec.get("context_length") or 128_000),
            "supported_settings": list(spec.get("supported_settings") or []),
            "oauth_source": "meta-oauth-plugin",
        }
        for model_id, spec in _get_model_specs(credentials).items()
    }


def _handle_meta_status() -> None:
    credentials = load_credentials()
    if not credentials:
        emit_warning(t("oauth.meta.status.none"))
        emit_info(t("oauth.meta.status.hint"))
        return
    emit_success(t("oauth.meta.status.authenticated"))
    emit_info(
        t("oauth.meta.status.source", source=credentials.get("_source", "unknown"))
    )
    emit_info(
        t("oauth.meta.status.models", models=", ".join(_meta_model_names(credentials)))
    )


def _handle_meta_logout() -> None:
    path = get_token_storage_path()
    if path.exists():
        path.unlink()
        emit_info(t("oauth.meta.logout.removed"))
    remaining = load_credentials()
    if remaining:
        emit_warning(
            t("oauth.meta.logout.external", source=remaining.get("_source", "external"))
        )
    else:
        emit_success(t("oauth.meta.logout.success"))


def _handle_custom_command(command: str, name: str) -> bool | None:
    del command
    if name == "meta-auth":
        if run_oauth_flow():
            set_model_and_reload_agent(_DEFAULT_MODEL)
        return True
    if name == "meta-status":
        _handle_meta_status()
        return True
    if name == "meta-logout":
        _handle_meta_logout()
        return True
    return None


def _create_meta_oauth_model(
    model_name: str, model_config: dict[str, Any], config: dict[str, Any]
) -> Any:
    """Create a Muse model using Meta's OpenAI Responses-compatible API."""
    del config
    from pydantic_ai.models.openai import OpenAIResponsesModel

    from code_puppy.http_utils import create_async_client
    from code_puppy.provider_identity import make_openai_provider

    credentials = load_credentials()
    if not credentials:
        emit_warning(
            t("oauth.meta.model.no_credentials", model=model_config.get("name"))
        )
        return None

    client = create_async_client(
        headers={"x-api-version": str(META_OAUTH_CONFIG["api_version"])},
        model_name=model_name,
    )
    provider = make_openai_provider(
        "meta",
        api_key=credentials["api_key"],
        base_url=credentials["api_base_url"],
        http_client=client,
    )
    return OpenAIResponsesModel(model_name=model_config["name"], provider=provider)


def _register_model_types() -> list[dict[str, Any]]:
    return [{"type": "meta_oauth", "handler": _create_meta_oauth_model}]


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
register_callback("load_models_config", _load_meta_models)
