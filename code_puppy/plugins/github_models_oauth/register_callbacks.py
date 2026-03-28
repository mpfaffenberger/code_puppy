"""GitHub Models OAuth plugin — authentication and model type handlers."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent

from .config import GITHUB_MODELS_OAUTH_CONFIG, get_client_id, get_token_storage_path
from .device_flow import run_device_flow
from .utils import (
    add_copilot_models_to_config,
    add_models_to_config,
    fetch_copilot_models,
    fetch_github_models,
    get_env_token,
    get_gh_cli_token,
    get_github_username,
    load_github_models_config,
    load_stored_tokens,
    prompt_for_token,
    remove_github_models,
    save_tokens,
)

logger = logging.getLogger(__name__)


def _custom_help() -> List[Tuple[str, str]]:
    return [
        ("github-auth", "Authenticate with GitHub. Use '/github-auth token' to paste a PAT"),
        ("github-status", "Show GitHub auth status and configured models"),
        ("github-logout", "Remove GitHub OAuth tokens and imported models"),
    ]


def _handle_auth(force_prompt: bool = False) -> bool:
    """Authenticate via gh CLI → env var → PAT paste → device flow.

    *force_prompt* skips auto-detect and goes straight to the PAT prompt.
    Returns ``True`` on success.
    """
    tokens = load_stored_tokens()
    if tokens and tokens.get("access_token"):
        emit_warning("Existing GitHub tokens found. This will overwrite them.")

    access_token: Optional[str] = None

    if not force_prompt:
        emit_info("🔍 Checking for gh CLI authentication…")
        access_token = get_gh_cli_token()
        if access_token:
            emit_success("✅ Found token from gh CLI")

        if not access_token:
            access_token = get_env_token()
            if access_token:
                emit_success("✅ Found token from environment variable")

    if not access_token:
        access_token = prompt_for_token()
        if access_token:
            emit_success("✅ Token received")

    if not access_token:
        client_id = get_client_id()
        if client_id:
            access_token = run_device_flow()

    if not access_token:
        emit_error(
            "❌ Authentication failed. Options:\n"
            "  • Install GitHub CLI: brew install gh && gh auth login\n"
            "  • Set GITHUB_TOKEN env var with a Personal Access Token\n"
            "  • Run /github-auth token to paste a PAT directly"
        )
        return False

    username = get_github_username(access_token)
    if not username:
        emit_error("❌ Token validation failed — could not fetch GitHub user.")
        return False

    emit_info(f"👤 Logged in as: {username}")
    if not save_tokens({"access_token": access_token, "username": username}):
        emit_error("Failed to save tokens. Check file permissions.")
        return False

    # Discover and register models from both APIs
    total = 0
    emit_info("📦 Fetching available GitHub Models…")
    models = fetch_github_models(access_token)
    if models and add_models_to_config(models):
        total += len(models)

    emit_info("📦 Fetching available Copilot models (Claude, Gemini, etc.)…")
    copilot_models = fetch_copilot_models(access_token)
    if copilot_models and add_copilot_models_to_config(copilot_models):
        total += len(copilot_models)

    if total:
        emit_success(
            f"✅ {total} models registered!\n"
            "   github-*  → GitHub Models (OpenAI, Meta, Mistral, DeepSeek…)\n"
            "   copilot-* → Copilot API (Claude, Gemini, GPT…)\n"
            "   Run /github-status to see all available models"
        )
    else:
        emit_warning("No models discovered. You can still try models manually.")

    return True


def _handle_status() -> None:
    tokens = load_stored_tokens()
    if not tokens or not tokens.get("access_token"):
        emit_warning("🔓 Not authenticated. Run /github-auth to sign in.")
        return

    username = tokens.get("username", "unknown")
    emit_success(f"🔐 GitHub: Authenticated as {username}")

    config = load_github_models_config()
    gh = sorted(n for n, c in config.items() if c.get("type") == "github_models")
    cp = sorted(n for n, c in config.items() if c.get("type") == "github_copilot")

    if gh:
        emit_info(f"\n🌐 GitHub Models ({len(gh)}) — prefix: github-")
        for name in gh[:8]:
            emit_info(f"   • {name}")
        if len(gh) > 8:
            emit_info(f"   … and {len(gh) - 8} more")
    if cp:
        emit_info(f"\n🤖 Copilot Models ({len(cp)}) — prefix: copilot-")
        for name in cp:
            emit_info(f"   • {name}")
    if not gh and not cp:
        emit_warning("No models configured. Run /github-auth.")


def _handle_logout() -> None:
    token_path = get_token_storage_path()
    if token_path.exists():
        token_path.unlink()
        emit_info("✓ Removed GitHub OAuth tokens")

    removed = remove_github_models()
    if removed:
        emit_info(f"✓ Removed {removed} GitHub models from configuration")

    emit_success("👋 GitHub Models logout complete")


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "github-auth":
        force = "token" in command.lower().split()[1:] if len(command.split()) > 1 else False
        if _handle_auth(force_prompt=force):
            model = "github-openai-gpt-4.1"
            set_model_and_reload_agent(model)
            emit_success(f"🔄 Switched to model: {model}")
            try:
                from code_puppy.config import get_global_model_name
                current = get_global_model_name()
                if current and "copilot" in current:
                    emit_warning(f"⚠️  Agent pinned to '{current}'. Run: /model {model}")
            except Exception:
                pass
        return True

    handlers = {"github-status": _handle_status, "github-logout": _handle_logout}
    handler = handlers.get(name)
    if handler:
        handler()
        return True
    return None


def _create_model_with_token(
    model_config: Dict, *, default_base_url: str, extra_headers: Dict[str, str],
) -> Any:
    """Create an OpenAI-compatible model backed by a stored GitHub token."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.http_utils import create_async_client, get_cert_bundle_path

    tokens = load_stored_tokens()
    if not tokens or not tokens.get("access_token"):
        emit_warning(
            f"GitHub token not found for '{model_config.get('name')}'. Run /github-auth."
        )
        return None

    base_url = model_config.get("custom_endpoint", {}).get("url", default_base_url)
    client = create_async_client(headers=extra_headers, verify=get_cert_bundle_path())
    provider = OpenAIProvider(
        api_key=tokens["access_token"], base_url=base_url, http_client=client,
    )
    return OpenAIChatModel(model_name=model_config["name"], provider=provider)


def _create_github_models_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    return _create_model_with_token(
        model_config,
        default_base_url=GITHUB_MODELS_OAUTH_CONFIG["api_base_url"],
        extra_headers={
            "X-GitHub-Api-Version": GITHUB_MODELS_OAUTH_CONFIG["api_version"],
            "User-Agent": GITHUB_MODELS_OAUTH_CONFIG["user_agent"],
        },
    )


def _create_copilot_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    return _create_model_with_token(
        model_config,
        default_base_url=GITHUB_MODELS_OAUTH_CONFIG["copilot_api_base_url"],
        extra_headers={
            "Copilot-Integration-Id": GITHUB_MODELS_OAUTH_CONFIG["copilot_integration_id"],
            "User-Agent": GITHUB_MODELS_OAUTH_CONFIG["user_agent"],
        },
    )


def _register_model_types() -> List[Dict[str, Any]]:
    return [
        {"type": "github_models", "handler": _create_github_models_model},
        {"type": "github_copilot", "handler": _create_copilot_model},
    ]


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
