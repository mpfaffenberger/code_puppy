"""ChatGPT OAuth plugin callbacks aligned with ChatMock flow."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.config import set_model_name
from code_puppy.messaging import emit_info, emit_success, emit_warning

from .config import CHATGPT_OAUTH_CONFIG, get_token_storage_path
from .oauth_flow import run_oauth_flow
from .utils import load_chatgpt_models, load_stored_tokens, remove_chatgpt_models


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
        set_model_name("chatgpt-gpt-5.2-codex")
        return True

    if name == "chatgpt-status":
        _handle_chatgpt_status()
        return True

    if name == "chatgpt-logout":
        _handle_chatgpt_logout()
        return True

    return None


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
