"""
Claude Code OAuth Plugin for Code Puppy.

Provides OAuth authentication for Claude Code models and registers
the 'claude_code' model type handler.
"""

from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from code_puppy.callbacks import register_callback
from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.model_switching import set_model_and_reload_agent
from code_puppy.provider_identity import (
    make_anthropic_provider,
    resolve_provider_identity,
)

from ..oauth_pasteback import parse_oauth_callback_input, read_available_stdin_line
from ..oauth_puppy_html import oauth_failure_html, oauth_success_html
from .config import CLAUDE_CODE_OAUTH_CONFIG, get_token_storage_path
from .fast_mode import (
    FAST_SETTING_KEY,
    ensure_fast_beta_header,
    is_fast_mode_enabled,
    patch_anthropic_client_fast_mode,
)
from .prompt_handler import is_claude_code_model, prepare_claude_code_prompt
from .utils import (
    OAuthContext,
    add_models_to_extra_config,
    assign_redirect_uri,
    build_authorization_url,
    exchange_code_for_tokens,
    fetch_claude_code_models,
    get_valid_access_token,
    load_claude_models_filtered,
    load_stored_tokens,
    prepare_oauth_context,
    remove_claude_code_models,
    save_tokens,
)

logger = logging.getLogger(__name__)


class _OAuthResult:
    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.state: Optional[str] = None
        self.error: Optional[str] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    result: _OAuthResult
    received_event: threading.Event

    def do_GET(self) -> None:  # noqa: N802
        logger.info("Callback received: path=%s", self.path)
        parsed = urlparse(self.path)
        params: Dict[str, List[str]] = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code and state:
            self.result.code = code
            self.result.state = state
            success_html = oauth_success_html(
                "Claude Code",
                "You're totally synced with Claude Code now!",
            )
            self._write_response(200, success_html)
        else:
            self.result.error = "Missing code or state"
            failure_html = oauth_failure_html(
                "Claude Code",
                "Missing code or state parameter 🥺",
            )
            self._write_response(400, failure_html)

        self.received_event.set()

    def log_message(self, log_format: str, *args: Any) -> None:
        return

    def _write_response(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


def _start_callback_server(
    context: OAuthContext,
) -> Optional[Tuple[HTTPServer, _OAuthResult, threading.Event]]:
    port_range = CLAUDE_CODE_OAUTH_CONFIG["callback_port_range"]

    for port in range(port_range[0], port_range[1] + 1):
        try:
            server = HTTPServer(("localhost", port), _CallbackHandler)
            assign_redirect_uri(context, port)
            result = _OAuthResult()
            event = threading.Event()
            _CallbackHandler.result = result
            _CallbackHandler.received_event = event

            def run_server(server=server) -> None:
                with server:
                    server.serve_forever()

            threading.Thread(target=run_server, daemon=True).start()
            return server, result, event
        except OSError:
            continue

    emit_error("Could not start OAuth callback server; all candidate ports are in use")
    return None


def _assign_manual_redirect_uri(context: OAuthContext) -> bool:
    port_range = CLAUDE_CODE_OAUTH_CONFIG["callback_port_range"]
    try:
        assign_redirect_uri(context, port_range[0])
    except Exception as exc:  # noqa: BLE001
        emit_error(f"Failed to assign redirect URI for OAuth flow: {exc}")
        return False
    return True


def _parse_pasted_callback(context: OAuthContext, raw_input: str) -> Optional[str]:
    try:
        parsed = parse_oauth_callback_input(raw_input)
    except ValueError as exc:
        emit_error(f"Could not parse pasted OAuth input: {exc}")
        return None

    if parsed.error:
        emit_error(f"OAuth provider returned an error: {parsed.error_message}")
        return None

    if not parsed.code:
        emit_error(t("oauth.pasteback.no_code"))
        return None

    if parsed.state:
        if parsed.state != context.state:
            emit_error(t("oauth.state_mismatch"))
            return None
    else:
        emit_warning(t("oauth.pasteback.no_state"))

    return parsed.code


def _wait_for_callback_or_paste(
    *,
    context: OAuthContext,
    result: Optional[_OAuthResult],
    event: Optional[threading.Event],
    timeout: float,
) -> Optional[str]:
    elapsed = 0.0
    interval = 0.25

    while elapsed < timeout:
        if event and event.is_set() and result:
            if result.error:
                emit_error(t("oauth.callback.error", error=result.error))
                return None

            if result.state != context.state:
                emit_error(t("oauth.state_mismatch"))
                return None

            return result.code

        pasted = read_available_stdin_line()
        if pasted is not None and pasted.strip():
            code = _parse_pasted_callback(context, pasted)
            if code:
                return code

        time.sleep(interval)
        elapsed += interval

    emit_error(t("oauth.callback.timeout"))
    return None


def _await_callback(context: OAuthContext) -> Optional[str]:
    timeout = CLAUDE_CODE_OAUTH_CONFIG["callback_timeout"]

    started = _start_callback_server(context)
    server: Optional[HTTPServer] = None
    result: Optional[_OAuthResult] = None
    event: Optional[threading.Event] = None
    if started:
        server, result, event = started
    else:
        emit_warning(t("oauth.server.pasteback_mode"))
        if not _assign_manual_redirect_uri(context):
            return None

    redirect_uri = context.redirect_uri
    if not redirect_uri:
        emit_error(t("oauth.server.no_redirect_uri"))
        if server:
            server.shutdown()
        return None

    auth_url = build_authorization_url(context)

    suppress_browser = False
    try:
        import webbrowser

        from code_puppy.tools.common import should_suppress_browser

        suppress_browser = should_suppress_browser()
        if suppress_browser:
            emit_info(t("oauth.browser.headless"))
            emit_info(t("oauth.browser.headless_url", url=auth_url))
        else:
            emit_info(t("oauth.browser.opening"))
            webbrowser.open(auth_url)
            emit_info(t("oauth.browser.fallback_url", url=auth_url))
    except Exception as exc:  # pragma: no cover
        if not suppress_browser:
            emit_warning(t("oauth.browser.open_failed", error=exc))
            emit_info(t("oauth.browser.manual_url", url=auth_url))

    if server:
        emit_info(t("oauth.server.listening", uri=redirect_uri))
    else:
        emit_info(t("oauth.server.pasteback_uri", uri=redirect_uri))
    emit_info(t("oauth.server.paste_hint"))

    code = _wait_for_callback_or_paste(
        context=context,
        result=result,
        event=event,
        timeout=timeout,
    )

    if server:
        server.shutdown()

    return code


def _custom_help() -> List[Tuple[str, str]]:
    return [
        (
            "claude-code-auth",
            "Authenticate with Claude Code via OAuth and import available models",
        ),
        (
            "claude-code-status",
            "Check Claude Code OAuth authentication status and configured models",
        ),
        ("claude-code-logout", "Remove Claude Code OAuth tokens and imported models"),
        (
            "claude-code-fast",
            "Toggle fast mode (speed=fast + fast-mode beta) for the active Claude Code model",
        ),
    ]


def _perform_authentication() -> None:
    context = prepare_oauth_context()
    code = _await_callback(context)
    if not code:
        return

    emit_info(t("oauth.auth.exchanging"))
    tokens = exchange_code_for_tokens(code, context)
    if not tokens:
        emit_error(t("oauth.auth.exchange_failed"))
        return

    if not save_tokens(tokens):
        emit_error(t("oauth.auth.save_failed"))
        return

    emit_success(t("oauth.auth.success"))

    access_token = tokens.get("access_token")
    if not access_token:
        emit_warning(t("oauth.auth.no_access_token"))
        return

    emit_info(t("oauth.auth.fetching_models"))
    models = fetch_claude_code_models(access_token)
    if not models:
        emit_warning(t("oauth.auth.no_models"))
        return

    emit_info(
        t("oauth.auth.discovered_models", count=len(models), models=", ".join(models))
    )
    if add_models_to_extra_config(models):
        emit_success(t("oauth.auth.models_added"))


def _reauthenticate_after_expired_oauth(model_name: str) -> Optional[str]:
    """Run full Claude Code OAuth only for configured claude-code-* models."""
    prefix = CLAUDE_CODE_OAUTH_CONFIG["prefix"]
    if not model_name.startswith(prefix):
        logger.debug(
            "Skipping Claude Code OAuth flow for non-prefixed model: %s", model_name
        )
        return None

    emit_warning(t("oauth.reauth.refresh_failed"))
    _perform_authentication()

    access_token = get_valid_access_token()
    if access_token:
        emit_success(t("oauth.reauth.restored"))
        return access_token

    emit_error(t("oauth.reauth.no_token"))
    return None


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "claude-code-auth":
        emit_info(t("oauth.cmd.auth.starting"))
        tokens = load_stored_tokens()
        if tokens and tokens.get("access_token"):
            emit_warning(t("oauth.cmd.auth.overwrite_warning"))
        _perform_authentication()
        set_model_and_reload_agent("claude-code-claude-opus-4-8-long")
        return True

    if name == "claude-code-status":
        tokens = load_stored_tokens()
        if tokens and tokens.get("access_token"):
            emit_success(t("oauth.cmd.status.authenticated"))
            expires_at = tokens.get("expires_at")
            if expires_at:
                remaining = max(0, int(expires_at - time.time()))
                hours, minutes = divmod(remaining // 60, 60)
                emit_info(t("oauth.cmd.status.expires", hours=hours, minutes=minutes))

            claude_models = [
                name
                for name, cfg in load_claude_models_filtered().items()
                if cfg.get("oauth_source") == "claude-code-plugin"
            ]
            if claude_models:
                emit_info(t("oauth.cmd.status.models", models=", ".join(claude_models)))
            else:
                emit_warning(t("oauth.cmd.status.no_models"))
        else:
            emit_warning(t("oauth.cmd.status.not_authenticated"))
            emit_info(t("oauth.cmd.status.hint"))
        return True

    if name == "claude-code-fast":
        from code_puppy.config import (
            get_global_model_name,
            set_model_setting,
        )

        active_model = get_global_model_name() or ""
        if not active_model.startswith(CLAUDE_CODE_OAUTH_CONFIG["prefix"]):
            emit_warning(t("oauth.cmd.fast.wrong_model"))
            return True

        currently_on = is_fast_mode_enabled(active_model)
        new_value = not currently_on
        # Config stores bools as string values; "true"/"false" round-trips cleanly
        set_model_setting(active_model, FAST_SETTING_KEY, str(new_value).lower())

        if new_value:
            emit_success(t("oauth.cmd.fast.enabled", model=active_model))
            emit_info(t("oauth.cmd.fast.enabled_detail"))
        else:
            emit_info(t("oauth.cmd.fast.disabled", model=active_model))

        # Reload agent so the anthropic-beta header update (set at client
        # construction time) takes effect. Payload side is live either way.
        set_model_and_reload_agent(active_model, warn_on_pinned_mismatch=False)
        return True

    if name == "claude-code-logout":
        token_path = get_token_storage_path()
        if token_path.exists():
            token_path.unlink()
            emit_info(t("oauth.cmd.logout.tokens_removed"))

        removed = remove_claude_code_models()
        if removed:
            emit_info(t("oauth.cmd.logout.models_removed", count=removed))

        emit_success(t("oauth.cmd.logout.success"))
        return True

    return None


def _resolve_cache_ttl(model_name: str) -> Optional[str]:
    """Prompt-cache TTL for a claude_code-type model.

    ``claude-code-*`` models (OAuth subscription) always get the free 1-hour
    TTL; anything else falls back to Anthropic's 5-minute default (None).
    """
    from code_puppy.claude_cache_client import CACHE_TTL_1H

    return CACHE_TTL_1H if is_claude_code_model(model_name) else None


def _create_claude_code_model(model_name: str, model_config: Dict, config: Dict) -> Any:
    """Create a Claude Code model instance.

    This handler is registered via the 'register_model_type' callback to handle
    models with type='claude_code'.
    """
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel

    from code_puppy.claude_cache_client import (
        ClaudeCacheAsyncClient,
        patch_anthropic_client_messages,
    )
    from code_puppy.http_utils import get_cert_bundle_path
    from code_puppy.model_factory import get_custom_config

    url, headers, verify, api_key, timeout = get_custom_config(model_config)

    # Refresh token if this is from the plugin
    if model_config.get("oauth_source") == "claude-code-plugin":
        refreshed_token = get_valid_access_token()
        if refreshed_token:
            api_key = refreshed_token
            custom_endpoint = model_config.get("custom_endpoint")
            if isinstance(custom_endpoint, dict):
                custom_endpoint["api_key"] = refreshed_token

    if not api_key:
        emit_warning(t("oauth.model.no_api_key", model=model_config.get("name")))
        return None

    # Check if interleaved thinking is enabled (defaults to True for OAuth models).
    # NOTE: we read via get_all_model_settings (not get_effective_model_settings)
    # because these are plugin-owned settings that aren't in the core
    # supported_settings allowlist and would otherwise be filtered out.
    # See fast_mode.FAST_SETTING_KEY for the full rationale.
    from code_puppy.config import get_all_model_settings

    per_model_settings = get_all_model_settings(model_name)
    interleaved_thinking = per_model_settings.get("interleaved_thinking", True)
    fast_enabled = bool(per_model_settings.get(FAST_SETTING_KEY, False))

    # Handle anthropic-beta header based on interleaved_thinking setting
    if "anthropic-beta" in headers:
        beta_parts = [p.strip() for p in headers["anthropic-beta"].split(",")]
        if interleaved_thinking:
            if "interleaved-thinking-2025-05-14" not in beta_parts:
                beta_parts.append("interleaved-thinking-2025-05-14")
        else:
            beta_parts = [p for p in beta_parts if "interleaved-thinking" not in p]
        headers["anthropic-beta"] = ",".join(beta_parts) if beta_parts else None
        if headers.get("anthropic-beta") is None:
            del headers["anthropic-beta"]
    elif interleaved_thinking:
        headers["anthropic-beta"] = "interleaved-thinking-2025-05-14"

    # Add 1M context beta header for long-context models
    from code_puppy.model_factory import CONTEXT_1M_BETA

    if model_config.get("context_length", 0) >= 1_000_000:
        if "anthropic-beta" in headers:
            beta_parts = [p.strip() for p in headers["anthropic-beta"].split(",")]
            if CONTEXT_1M_BETA not in beta_parts:
                beta_parts.append(CONTEXT_1M_BETA)
            headers["anthropic-beta"] = ",".join(beta_parts)
        else:
            headers["anthropic-beta"] = CONTEXT_1M_BETA

    # Fast mode: append fast-mode-2026-02-01 beta marker when enabled
    ensure_fast_beta_header(headers, fast_enabled)

    # Use a dedicated client wrapper that injects cache_control on /v1/messages
    if verify is None:
        verify = get_cert_bundle_path()

    # Claude Code OAuth includes 1-hour prompt caching for free, so
    # claude-code-* models ALWAYS request the extended TTL. Anything else
    # (hand-rolled claude_code configs without the prefix) keeps Anthropic's
    # default 5-minute TTL — this is deliberately NOT applied to plain
    # anthropic/custom_anthropic models.
    cache_ttl = _resolve_cache_ttl(model_name)

    # Disable HTTP/2 for Claude Code OAuth - the UnprefixingStream wrapper
    # that transforms tool names in streaming responses doesn't play well
    # with HTTP/2's compression handling, causing zlib decompression errors.
    client = ClaudeCacheAsyncClient(
        headers=headers,
        verify=verify,
        timeout=180,
        http2=False,
        # Claude Code OAuth requires the ``cp_`` tool-name prefix; the wire
        # format Anthropic's CLI uses won't accept un-prefixed tools.
        apply_claude_code_prefix=True,
        cache_ttl=cache_ttl,
        oauth_reauthentication_callback=lambda: _reauthenticate_after_expired_oauth(
            model_name
        ),
    )

    anthropic_client = AsyncAnthropic(
        base_url=url,
        http_client=client,
        auth_token=api_key,
    )

    def _update_runtime_token(access_token: str) -> None:
        anthropic_client.auth_token = access_token
        custom_endpoint = model_config.get("custom_endpoint")
        if isinstance(custom_endpoint, dict):
            custom_endpoint["api_key"] = access_token

    client.set_token_update_callback(_update_runtime_token)
    patch_anthropic_client_messages(anthropic_client, cache_ttl=cache_ttl)
    # Fast mode wrapper sits outside cache-control injector and re-reads
    # the setting on every call so /claude-code-fast takes effect live.
    patch_anthropic_client_fast_mode(anthropic_client, model_name)
    anthropic_client.api_key = None
    anthropic_client.auth_token = api_key
    provider = make_anthropic_provider(
        resolve_provider_identity(model_name, model_config),
        anthropic_client=anthropic_client,
    )
    return AnthropicModel(model_name=model_config["name"], provider=provider)


def _register_model_types() -> List[Dict[str, Any]]:
    """Register the claude_code model type handler."""
    return [{"type": "claude_code", "handler": _create_claude_code_model}]


# Global storage for the token refresh heartbeat
# Using a dict to allow multiple concurrent agent runs (keyed by session_id)
_active_heartbeats: Dict[str, Any] = {}


async def _on_agent_run_start(
    agent_name: str,
    model_name: str,
    session_id: Optional[str] = None,
) -> None:
    """Start token refresh heartbeat for Claude Code OAuth models.

    This callback is triggered when an agent run starts. If the model is a
    Claude Code OAuth model, we start a background heartbeat to keep the
    token fresh during long-running operations.
    """
    # Only start heartbeat for Claude Code models
    if not model_name.startswith("claude-code"):
        return

    try:
        from .token_refresh_heartbeat import TokenRefreshHeartbeat

        heartbeat = TokenRefreshHeartbeat()
        await heartbeat.start()

        # Store heartbeat for cleanup, keyed by session_id
        key = session_id or "default"
        _active_heartbeats[key] = heartbeat
        logger.debug(
            "Started token refresh heartbeat for session %s (model: %s)",
            key,
            model_name,
        )
    except ImportError:
        logger.debug("Token refresh heartbeat module not available")
    except Exception as exc:
        logger.debug("Failed to start token refresh heartbeat: %s", exc)


async def _on_agent_run_end(
    agent_name: str,
    model_name: str,
    session_id: Optional[str] = None,
    success: bool = True,
    error: Optional[Exception] = None,
    response_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Stop token refresh heartbeat when agent run ends.

    This callback is triggered when an agent run completes (success or failure).
    We stop any heartbeat that was started for this session.
    """
    # We don't use response_text or metadata, just cleanup the heartbeat
    key = session_id or "default"
    heartbeat = _active_heartbeats.pop(key, None)

    if heartbeat is not None:
        try:
            await heartbeat.stop()
            logger.debug(
                "Stopped token refresh heartbeat for session %s (refreshed %d times)",
                key,
                heartbeat.refresh_count,
            )
        except Exception as exc:
            logger.debug("Error stopping token refresh heartbeat: %s", exc)


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
register_callback("register_model_type", _register_model_types)
register_callback("prepare_model_prompt", prepare_claude_code_prompt)
register_callback("agent_run_start", _on_agent_run_start)
register_callback("agent_run_end", _on_agent_run_end)
