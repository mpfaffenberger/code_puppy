"""ChatGPT OAuth plugin callbacks aligned with ChatMock flow.

Provides OAuth authentication for ChatGPT models and registers
the 'chatgpt_oauth' model type handler.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from .config import CHATGPT_OAUTH_CONFIG, get_token_storage_path
from .oauth_flow import run_oauth_flow
from .usage import refresh_usage_in_background
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
        ("codex-auth", "Alias for /chatgpt-auth"),
        (
            "chatgpt-status",
            "Check ChatGPT OAuth authentication status and configured models",
        ),
        ("codex-status", "Alias for /chatgpt-status"),
        ("chatgpt-logout", "Remove ChatGPT OAuth tokens and imported models"),
        ("codex-logout", "Alias for /chatgpt-logout"),
        ("codex-imagegen <prompt>", "Generate an image with Codex OAuth"),
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
    was_authenticated = _is_codex_oauth_authenticated()

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

    if was_authenticated:
        _reload_active_agent()


def _is_codex_oauth_authenticated() -> bool:
    """Whether Codex OAuth tokens are present on disk."""
    tokens = load_stored_tokens()
    return bool(tokens and tokens.get("access_token") and tokens.get("account_id"))


def _reload_active_agent() -> None:
    """Reload the active agent so tool advertisement changes take effect."""
    from code_puppy.agents import get_current_agent

    try:
        current_agent = get_current_agent()
    except Exception:
        return
    if current_agent is None:
        return
    try:
        if hasattr(current_agent, "refresh_config"):
            try:
                current_agent.refresh_config()
            except Exception:
                pass
        current_agent.reload_code_generation_agent()
    except Exception as exc:
        emit_warning(t("codex.logout.reload_failed", error=str(exc)))


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name in {"chatgpt-auth", "codex-auth"}:
        run_oauth_flow()
        set_model_and_reload_agent("codex-gpt-5.6-sol")
        return True

    if name in {"chatgpt-status", "codex-status"}:
        _handle_chatgpt_status()
        return True

    if name in {"chatgpt-logout", "codex-logout"}:
        _handle_chatgpt_logout()
        return True

    if name == "codex-imagegen":
        from .image_generation import (
            CodexImageGenerationError,
            emit_iterm_image,
            generate_image,
        )

        _, _, prompt = command.partition(" ")
        if not prompt.strip():
            emit_warning(t("codex.imagegen.usage"))
            return True
        emit_info(t("codex.imagegen.generating"))
        try:
            output_path = generate_image(prompt)
        except CodexImageGenerationError as exc:
            emit_error(str(exc))
        else:
            emit_success(t("codex.imagegen.saved", path=str(output_path)))
            emit_iterm_image(output_path)
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

    # Refresh plan limits without delaying model creation or terminal rendering.
    refresh_usage_in_background(access_token, account_id)

    # Build headers for ChatGPT Codex API
    originator = CHATGPT_OAUTH_CONFIG.get("originator", "codex_cli_rs")
    client_version = CHATGPT_OAUTH_CONFIG.get("client_version", "0.144.1")

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
    return OpenAIResponsesModel(model_name=model_config["name"], provider=provider)


def _register_imagegen_skill() -> list[dict[str, str]]:
    return [
        {
            "name": "codex-imagegen",
            "skill_md_path": str(Path(__file__).with_name("IMAGEGEN_SKILL.md")),
        }
    ]


def _register_imagegen_tools() -> list[dict[str, Any]]:
    from .image_tool import register_tools_callback

    return register_tools_callback()


def _advertise_imagegen_tool(agent_name: str | None = None) -> list[str]:
    del agent_name
    if not _is_codex_oauth_authenticated():
        return []
    return ["codex_imagegen"]


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the chatgpt_oauth model type handler."""
    return [{"type": "chatgpt_oauth", "handler": _create_chatgpt_oauth_model}]


def _refresh_usage_on_agent_run(
    agent_name: str, model_name: str, session_id: str | None = None
) -> None:
    """Keep limits fresh for Codex runs; the actual HTTP request is asynchronous."""
    del agent_name, session_id
    if not model_name.startswith("codex-"):
        return
    tokens = load_stored_tokens() or {}
    refresh_usage_in_background(
        tokens.get("access_token", ""), tokens.get("account_id", "")
    )


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
register_callback("register_skills", _register_imagegen_skill)
register_callback("register_tools", _register_imagegen_tools)
register_callback("register_agent_tools", _advertise_imagegen_tool)
register_callback("agent_run_start", _refresh_usage_on_agent_run)
