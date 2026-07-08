"""Grok (x.ai) OAuth plugin callbacks.

Provides OAuth authentication for Grok models (SuperGrok / Grok CLI flow)
and registers the 'grok_oauth' model type handler plus the Grok model
catalogue (headlined by grok-4.5).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from .config import GROK_MODELS, GROK_OAUTH_CONFIG, get_token_storage_path
from .oauth_flow import run_oauth_flow
from .utils import get_valid_access_token, load_stored_tokens

_PREFIX = GROK_OAUTH_CONFIG["prefix"]
_DEFAULT_MODEL = f"{_PREFIX}{GROK_OAUTH_CONFIG['default_model']}"


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "grok-auth",
            "Authenticate with x.ai (Grok) via OAuth and register Grok models",
        ),
        ("grok-status", "Check Grok OAuth authentication status"),
        ("grok-logout", "Remove Grok OAuth tokens and registered models"),
    ]


def _handle_grok_status() -> None:
    tokens = load_stored_tokens()
    if tokens and tokens.get("access_token"):
        emit_success(" Grok OAuth: Authenticated")
        emit_info(f" Available Grok models: {', '.join(_grok_model_names())}")
    else:
        emit_warning(" Grok OAuth: Not authenticated")
        emit_info(" Run /grok-auth to launch the browser sign-in flow.")


def _handle_grok_logout() -> None:
    token_path = get_token_storage_path()
    if token_path.exists():
        token_path.unlink()
        emit_info("Removed Grok OAuth tokens")
    emit_success("Grok logout complete")


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "grok-auth":
        if run_oauth_flow():
            emit_info(f"Registering Grok models: {', '.join(_grok_model_names())}")
            set_model_and_reload_agent(_DEFAULT_MODEL)
        return True

    if name == "grok-status":
        _handle_grok_status()
        return True

    if name == "grok-logout":
        _handle_grok_logout()
        return True

    return None


def _grok_model_names() -> List[str]:
    return [f"{_PREFIX}{model_id}" for model_id in GROK_MODELS]


def _load_grok_models() -> Dict[str, Any]:
    """Inject Grok models into the catalogue once authenticated."""
    tokens = load_stored_tokens()
    if not (tokens and tokens.get("access_token")):
        return {}

    return {
        f"{_PREFIX}{model_id}": {
            "type": "grok_oauth",
            "name": model_id,
            "context_length": spec["context_length"],
            "supported_settings": spec.get("supported_settings", []),
            "oauth_source": "grok-oauth-plugin",
        }
        for model_id, spec in GROK_MODELS.items()
    }


def _create_grok_oauth_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    """Create a Grok OAuth model instance.

    This handler is registered via the 'register_model_type' callback to
    handle models with type='grok_oauth'. Grok models speak the OpenAI
    Responses API on api.x.ai with the OAuth access token as bearer key.
    """
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.http_utils import create_async_client

    access_token = get_valid_access_token()
    if not access_token:
        emit_warning(
            f"Failed to get valid Grok OAuth token; skipping model "
            f"'{model_config.get('name')}'. Run /grok-auth to authenticate."
        )
        return None

    provider = OpenAIProvider(
        api_key=access_token,
        base_url=GROK_OAUTH_CONFIG["api_base_url"],
        http_client=create_async_client(model_name=model_name),
    )
    return OpenAIResponsesModel(model_name=model_config["name"], provider=provider)


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the grok_oauth model type handler."""
    return [{"type": "grok_oauth", "handler": _create_grok_oauth_model}]


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
register_callback("load_models_config", _load_grok_models)
