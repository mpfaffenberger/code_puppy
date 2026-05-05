"""GitHub Copilot auth plugin — callback registrations.

Provides:
- ``/copilot-login``  — browser-based GitHub Device Flow auth
- ``/copilot-status`` — show auth & model status
- ``/copilot-logout`` — remove tokens and registered Copilot models
- ``copilot`` model-type handler for ``model_factory``
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

from .config import COPILOT_AUTH_CONFIG
from .utils import (
    add_models_to_config,
    clear_caches,
    fetch_copilot_models,
    get_api_endpoint_for_host,
    get_token_for_host,
    get_valid_session_token,
    load_copilot_models,
    load_device_tokens,
    poll_for_token,
    remove_copilot_models,
    save_device_token,
    start_device_flow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# /help entries
# ---------------------------------------------------------------------------


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "copilot-login",
            "Authenticate with GitHub/GitHub Enterprise Copilot via browser",
        ),
        ("copilot-status", "Show GitHub Copilot authentication status and models"),
        ("copilot-logout", "Remove Copilot tokens and registered models"),
    ]


# ---------------------------------------------------------------------------
# /copilot-status
# ---------------------------------------------------------------------------


def _handle_copilot_status() -> None:
    tokens = load_device_tokens()

    if not tokens:
        emit_warning(
            "🔓 GitHub Copilot: Not authenticated.\n"
            "   Run /copilot-login to sign in via your browser."
        )
        return

    emit_success("🔐 GitHub Copilot: Authenticated")
    for t in tokens:
        host_label = t.host
        user_label = f" ({t.user})" if t.user else ""
        emit_info(f"   • {host_label}{user_label}")

    # Check session token for each host
    for t in tokens:
        session = get_valid_session_token(t.oauth_token, t.host)
        if session:
            emit_info(f"   ✅ {t.host}: active session (auto-refreshes on expiry)")
        else:
            emit_warning(
                f"   ⚠️  {t.host}: could not obtain a session token — may be expired"
            )
            emit_info(f"      Run /copilot-login {t.host} to re-authenticate.")

    # Registered models
    models = load_copilot_models()
    copilot_models = [
        name
        for name, cfg in models.items()
        if cfg.get("oauth_source") == "copilot-auth-plugin"
    ]
    if copilot_models:
        emit_info(f"🎯 Registered Copilot models: {', '.join(sorted(copilot_models))}")
    else:
        emit_warning(
            "⚠️  No Copilot models registered yet. Run /copilot-login to set up."
        )


# ---------------------------------------------------------------------------
# /copilot-logout
# ---------------------------------------------------------------------------


def _handle_copilot_logout() -> None:
    errors: list[str] = []

    # 1. Remove registered models from copilot_models.json
    removed = remove_copilot_models()
    if removed:
        emit_info(f"Removed {removed} Copilot model(s) from configuration")
    else:
        emit_info("No Copilot models were registered")

    # 2. Delete on-disk token/session caches
    from .config import get_device_token_storage_path, get_session_cache_path

    for path in (get_session_cache_path(), get_device_token_storage_path()):
        if path.exists():
            try:
                path.unlink()
            except Exception as exc:
                errors.append(f"Could not remove {path.name}: {exc}")

    # 3. Clear in-memory session and endpoint caches
    clear_caches()

    # 4. If the active model was a copilot model, reset it so the app
    #    doesn't keep trying to use a model whose tokens are gone.
    try:
        from code_puppy.config import (
            clear_model_cache,
            get_model_name,
            reset_session_model,
        )

        current = get_model_name()
        if current and current.startswith(COPILOT_AUTH_CONFIG["prefix"]):
            reset_session_model()
            clear_model_cache()
            emit_info(f"Reset active model (was {current})")
    except Exception:
        pass  # Non-critical — worst case the next prompt will error and user switches

    # 5. Report outcome
    if errors:
        for err in errors:
            emit_warning(err)
        emit_warning("Copilot logout completed with errors (see above)")
    else:
        emit_success("Copilot logout complete — all tokens removed")


# ---------------------------------------------------------------------------
# /copilot-login — browser-based GitHub Device Flow
# ---------------------------------------------------------------------------


def _normalize_github_host(raw_host: str) -> str | None:
    """Validate and normalize a GitHub hostname for safe URL interpolation.

    The hostname is interpolated into URLs like
    ``https://{host}/login/device/code``, so we must reject anything that
    could alter the URL structure (schemes, paths, credentials, etc.).

    Returns:
        The cleaned lowercase hostname on success, or ``None`` if the input
        is invalid.

    Rejects inputs containing:
        - URL schemes    (``://``)   — e.g. ``https://evil.com``
        - Path segments  (``/``, ``\\``) — e.g. ``github.com/evil``
        - Credentials    (``@``)     — e.g. ``user@attacker.tld``
        - Query strings  (``?``)     — e.g. ``host?q=1``
        - Fragments      (``#``)     — e.g. ``host#frag``
    """
    host = raw_host.strip().lower()
    if not host:
        return "github.com"

    # Block characters that would alter URL structure when interpolated
    unsafe_chars = ("://", "/", "\\", "@", "?", "#")
    for marker in unsafe_chars:
        if marker in host:
            return None

    # Strip trailing dots (DNS allows them but they're not meaningful here)
    return host.rstrip(".")


def _handle_copilot_login(command: str) -> None:
    """Authenticate with GitHub Copilot via the GitHub Device Flow.

    Opens a browser for the user to enter a one-time code.  Supports
    GitHub Enterprise by passing the hostname:
    ``/copilot-login ghes.example.com``

    When no hostname is given the user is prompted (default: github.com).
    """
    # Parse optional GHE hostname from command arguments
    parts = command.strip().split()
    host: str | None = None
    if len(parts) > 1:
        host = parts[1].strip()

    # If no host was provided as an argument, prompt the user
    if not host:
        emit_info(
            "🌐 Enter your GitHub hostname — just the domain, no https:// or path.\n"
            "   Examples: github.com, ghe.mycompany.com\n"
            "   Press Enter to use github.com."
        )
        try:
            from prompt_toolkit import prompt as pt_prompt

            raw = pt_prompt("GitHub host: ", default="github.com").strip()
            host = raw if raw else "github.com"
        except ImportError:
            host = "github.com"
        except (EOFError, KeyboardInterrupt):
            emit_warning("Copilot login cancelled.")
            return

    # Validate the hostname before interpolating it into any URLs
    host = _normalize_github_host(host)
    if not host:
        emit_error(
            "Invalid hostname — expected a bare domain like github.com or ghe.mycompany.com.\n"
            "   Do not include https://, paths, or special characters."
        )
        return

    if host != "github.com":
        emit_info(f"Using GitHub Enterprise host: {host}")

    emit_info(f"🔑 Starting GitHub Device Flow for {host}…")

    device_resp = start_device_flow(host)
    if not device_resp:
        emit_error(
            "Failed to start Device Flow. Check your network connection "
            "and ensure the host is reachable."
        )
        return

    user_code = device_resp["user_code"]
    verification_uri = device_resp.get(
        "verification_uri", f"https://{host}/login/device"
    )
    expires_in = int(device_resp.get("expires_in", 900))
    interval = int(device_resp.get("interval", 5))

    # Show the code prominently
    emit_success(f"🔗 Your one-time code:  {user_code}")
    emit_info(f"   Open {verification_uri} and enter the code above.")

    # Try to open the browser
    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        if should_suppress_browser():
            emit_info(f"[HEADLESS MODE] Visit: {verification_uri}")
        else:
            webbrowser.open(verification_uri)
    except Exception as exc:
        logger.debug("Could not open browser: %s", exc)
        emit_info(f"Please open this URL manually: {verification_uri}")

    emit_info("⏳ Waiting for you to authorize in the browser…")

    oauth_token = poll_for_token(
        device_code=device_resp["device_code"],
        host=host,
        interval=interval,
        expires_in=expires_in,
    )

    if not oauth_token:
        emit_error(
            "Authorization was not completed in time, or was denied. "
            "Please try /copilot-login again."
        )
        return

    emit_success("✅ GitHub authorization successful!")

    # Persist the token
    if not save_device_token(host, oauth_token):
        emit_warning("Token obtained but could not be saved to disk.")

    # Exchange for Copilot session token & register models
    emit_info("Exchanging for Copilot session token…")
    session = get_valid_session_token(oauth_token, host)
    if not session:
        emit_warning(
            "Got a GitHub token but could not obtain a Copilot session token.\n"
            "   Your GitHub account may not have Copilot access."
        )
        return

    emit_success("✅ Copilot session token obtained")

    emit_info("Fetching available Copilot models…")
    model_list = fetch_copilot_models(session, host)
    if model_list and add_models_to_config(model_list, host):
        emit_success(
            f"Registered {len(model_list)} Copilot model(s). "
            "Use the `copilot-` prefix with /model."
        )
        try:
            from code_puppy.model_switching import set_model_and_reload_agent

            default_model = f"{COPILOT_AUTH_CONFIG['prefix']}{model_list[0]}"
            set_model_and_reload_agent(default_model)
        except Exception as exc:
            logger.debug("Could not auto-switch to Copilot model: %s", exc)
    else:
        emit_warning("Could not register Copilot models.")


# ---------------------------------------------------------------------------
# custom_command dispatcher
# ---------------------------------------------------------------------------


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None
    if name == "copilot-login":
        _handle_copilot_login(command)
        return True
    if name == "copilot-status":
        _handle_copilot_status()
        return True
    if name == "copilot-logout":
        _handle_copilot_logout()
        return True
    return None


# ---------------------------------------------------------------------------
# Model-type handler — creates OpenAI-compatible model for Copilot API
# ---------------------------------------------------------------------------


def _create_copilot_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    """Create an OpenAI-compatible model backed by GitHub Copilot API.

    Called by ``model_factory`` when ``type == "copilot"``.

    Uses a dynamic auth flow that refreshes the short-lived Copilot session
    token automatically before each API request, preventing mid-conversation
    token expiry errors.
    """
    import httpx
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.http_utils import create_async_client

    # Discover token — match against the host stored in the model config
    host = model_config.get("copilot_host", "github.com")
    preferred = get_token_for_host(host)
    if not preferred:
        emit_warning(
            f"No Copilot token available for host '{host}'; skipping model '{model_config.get('name')}'. "
            "Run /copilot-login first."
        )
        return None

    # Verify we can get an initial session token
    session_token = get_valid_session_token(preferred.oauth_token, preferred.host)
    if not session_token:
        emit_warning(
            f"Could not obtain Copilot session token; skipping model '{model_config.get('name')}'. "
            "Run /copilot-login to re-authenticate."
        )
        return None

    # Build HTTP client with Copilot-required headers and dynamic token refresh.
    # The CopilotAuth flow replaces the Authorization header before every request,
    # so the session token is always fresh even for long-running conversations.
    copilot_headers = {
        "Editor-Version": COPILOT_AUTH_CONFIG["editor_version"],
        "Editor-Plugin-Version": COPILOT_AUTH_CONFIG["editor_plugin_version"],
        "Copilot-Integration-Id": COPILOT_AUTH_CONFIG["copilot_integration_id"],
        "Openai-Intent": COPILOT_AUTH_CONFIG["openai_intent"],
    }

    class _CopilotAuth(httpx.Auth):
        """httpx auth flow that refreshes the Copilot session token per-request."""

        def __init__(self, oauth_token: str, token_host: str):
            self._oauth_token = oauth_token
            self._host = token_host

        def auth_flow(self, request: httpx.Request):
            token = get_valid_session_token(self._oauth_token, self._host)
            if token:
                request.headers["Authorization"] = f"Bearer {token}"
            yield request

    client = create_async_client(headers=copilot_headers)
    # Attach the dynamic auth so every request gets a fresh token
    client.auth = _CopilotAuth(preferred.oauth_token, preferred.host)

    # Use the API endpoint discovered during session-token exchange.
    # Falls back to whatever was stored in the model config at registration.
    base_url = get_api_endpoint_for_host(host)
    if base_url == COPILOT_AUTH_CONFIG["api_base_url"]:
        config_url = model_config.get("custom_endpoint", {}).get("url")
        if config_url:
            base_url = config_url

    # Use a placeholder API key — the actual token is injected by _CopilotAuth
    provider = OpenAIProvider(
        api_key="copilot-session-managed",
        base_url=base_url,
        http_client=client,
    )

    # Build a model profile that tells pydantic-ai how to handle thinking.
    # Claude models behind the Copilot API return thinking in a custom field
    # called "reasoning_text" (and encrypted round-trip data in "reasoning_opaque").
    profile = None
    underlying_name = model_config.get("name", "").lower()
    if underlying_name.startswith("claude-"):
        from pydantic_ai.profiles.openai import OpenAIModelProfile

        from .reasoning_client import patch_client_for_reasoning_opaque

        # Enable field-mode so thinking persists across tool calls.
        # The reasoning_opaque round-trip interceptor (patched onto the
        # httpx client below) captures the encrypted blob from responses
        # and re-injects it into subsequent requests, preventing 400s.
        profile = OpenAIModelProfile(
            openai_chat_thinking_field="reasoning_text",
            openai_supports_reasoning=True,
            openai_chat_send_back_thinking_parts="field",
        )
        patch_client_for_reasoning_opaque(client, thinking_field="reasoning_text")

    return OpenAIChatModel(
        model_name=model_config["name"],
        provider=provider,
        profile=profile,
    )


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the ``copilot`` model type handler."""
    return [{"type": "copilot", "handler": _create_copilot_model}]


# ---------------------------------------------------------------------------
# Hook registrations — executed at module import time
# ---------------------------------------------------------------------------

register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
