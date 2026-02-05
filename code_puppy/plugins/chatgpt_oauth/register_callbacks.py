"""ChatGPT OAuth plugin callbacks aligned with ChatMock flow.

Provides OAuth authentication for ChatGPT models and registers
the 'chatgpt_oauth' model type handler.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from .config import CHATGPT_OAUTH_CONFIG, get_token_storage_path
from .oauth_flow import run_oauth_flow
from .utils import (
    get_valid_access_token,
    load_chatgpt_models,
    load_stored_tokens,
    remove_chatgpt_models,
)


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "chatgpt-auth",
            "Authenticate with ChatGPT via OAuth and import available models",
        ),
        (
            "chatgpt-status",
            "Check ChatGPT OAuth authentication status and configured models",
        ),
        ("chatgpt-logout", "Remove ChatGPT OAuth tokens and imported models"),
    ]


def _handle_chatgpt_status() -> None:
    tokens = load_stored_tokens()
    if tokens and tokens.get("access_token"):
        emit_success("🔐 ChatGPT OAuth: Authenticated")

        api_key = tokens.get("api_key")
        if api_key:
            os.environ[CHATGPT_OAUTH_CONFIG["api_key_env_var"]] = api_key
            emit_info("✅ OAuth access token available for API requests")
        else:
            emit_warning("⚠️ No access token obtained. Authentication may have failed.")

        chatgpt_models = [
            name
            for name, cfg in load_chatgpt_models().items()
            if cfg.get("oauth_source") == "chatgpt-oauth-plugin"
        ]
        if chatgpt_models:
            emit_info(f"🎯 Configured ChatGPT models: {', '.join(chatgpt_models)}")
        else:
            emit_warning("⚠️ No ChatGPT models configured yet.")
    else:
        emit_warning("🔓 ChatGPT OAuth: Not authenticated")
        emit_info("🌐 Run /chatgpt-auth to launch the browser sign-in flow.")


def _handle_chatgpt_logout() -> None:
    token_path = get_token_storage_path()
    if token_path.exists():
        token_path.unlink()
        emit_info("Removed ChatGPT OAuth tokens")

    if CHATGPT_OAUTH_CONFIG["api_key_env_var"] in os.environ:
        del os.environ[CHATGPT_OAUTH_CONFIG["api_key_env_var"]]

    removed = remove_chatgpt_models()
    if removed:
        emit_info(f"Removed {removed} ChatGPT models from configuration")

    emit_success("ChatGPT logout complete")


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "chatgpt-auth":
        run_oauth_flow()
        set_model_and_reload_agent("chatgpt-gpt-5.3-codex")
        return True

    if name == "chatgpt-status":
        _handle_chatgpt_status()
        return True

    if name == "chatgpt-logout":
        _handle_chatgpt_logout()
        return True

    return None


def _create_chatgpt_oauth_model(
    model_name: str, model_config: Dict, config: Dict
) -> Any:
    """Create a ChatGPT OAuth model instance.

    This handler is registered via the 'register_model_type' callback to handle
    models with type='chatgpt_oauth'.
    """
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.chatgpt_codex_client import create_codex_async_client
    from code_puppy.http_utils import get_cert_bundle_path

    # Get a valid access token (refreshing if needed)
    access_token = get_valid_access_token()
    if not access_token:
        emit_warning(
            f"Failed to get valid ChatGPT OAuth token; skipping model '{model_config.get('name')}'. "
            "Run /chatgpt-auth to authenticate."
        )
        return None

    # Get account_id from stored tokens (required for ChatGPT-Account-Id header)
    tokens = load_stored_tokens()
    account_id = tokens.get("account_id", "") if tokens else ""
    if not account_id:
        emit_warning(
            f"No account_id found in ChatGPT OAuth tokens; skipping model '{model_config.get('name')}'. "
            "Run /chatgpt-auth to re-authenticate."
        )
        return None

    # Build headers for ChatGPT Codex API
    originator = CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs")
    client_version = CHATGPT_OAUTH_CONFIG.get("client_version", "0.72.0")

    headers = {
        "ChatGPT-Account-Id": account_id,
        "originator": originator,
        "User-Agent": f"{originator}/{client_version}",
    }
    # Merge with any headers from model config
    config_headers = model_config.get("custom_endpoint", {}).get("headers", {})
    headers.update(config_headers)

    # Get base URL - Codex API uses chatgpt.com, not api.openai.com
    base_url = model_config.get("custom_endpoint", {}).get(
        "url", CHATGPT_OAUTH_CONFIG["api_base_url"]
    )

    # Create HTTP client with Codex interceptor for store=false injection
    verify = get_cert_bundle_path()
    client = create_codex_async_client(headers=headers, verify=verify)

    provider = OpenAIProvider(
        api_key=access_token,
        base_url=base_url,
        http_client=client,
    )

    # ChatGPT Codex API only supports Responses format
    model = OpenAIResponsesModel(model_name=model_config["name"], provider=provider)
    setattr(model, "provider", provider)
    return model


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the chatgpt_oauth model type handler."""
    return [{"type": "chatgpt_oauth", "handler": _create_chatgpt_oauth_model}]


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
