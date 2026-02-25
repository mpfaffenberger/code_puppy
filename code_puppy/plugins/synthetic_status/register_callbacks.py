"""Slash commands for Synthetic provider subscription status."""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.panel import Panel

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.model_factory import get_api_key

from .status_api import fetch_synthetic_quota, resolve_syn_api_key

_PROVIDER_ENV_KEYS = {
    "synthetic": "SYN_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "zai": "ZAI_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
}


def _custom_help() -> List[Tuple[str, str]]:
    return [
        ("synthetic-status", "Check Synthetic subscription quota and renewal time"),
        ("provider", "Provider utilities (usage: /provider synthetic status)"),
        (
            "status",
            "Show provider status when only Synthetic appears configured",
        ),
    ]


def _format_amount(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _render_synthetic_status_panel(
    limit: float,
    used: float,
    renews_at_utc: str,
) -> Panel:
    remaining = max(limit - used, 0.0)
    body = "\n".join(
        [
            "Provider      : Synthetic",
            f"Requests used : {_format_amount(used)} / {_format_amount(limit)}",
            f"Requests left : {_format_amount(remaining)}",
            f"Renews at     : {renews_at_utc}",
        ]
    )
    return Panel(body, border_style="cyan")


def _handle_synthetic_status() -> None:
    api_key = resolve_syn_api_key()
    if not api_key:
        emit_error("SYN_API_KEY is not configured. Set it with /set syn_api_key <key>.")
        return

    result = fetch_synthetic_quota(api_key=api_key)
    if not result.ok or not result.quota:
        emit_warning(result.error or "Failed to fetch Synthetic quota status.")
        return

    renews_at_str = result.quota.renews_at_utc.strftime("%Y-%m-%d %H:%M UTC")
    panel = _render_synthetic_status_panel(
        limit=result.quota.limit,
        used=result.quota.requests_used,
        renews_at_utc=renews_at_str,
    )
    emit_info(panel)


def _is_synthetic_only_provider_configured() -> bool:
    configured = {
        provider
        for provider, env_name in _PROVIDER_ENV_KEYS.items()
        if get_api_key(env_name)
    }
    return configured == {"synthetic"}


def _handle_provider_command(command: str) -> Optional[bool]:
    tokens = command.strip().split()
    if len(tokens) < 2:
        return None

    provider = tokens[1].lower()
    if provider != "synthetic":
        return None

    if len(tokens) == 3 and tokens[2].lower() == "status":
        _handle_synthetic_status()
        return True

    emit_info("Usage: /provider synthetic status")
    return True


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    if not name:
        return None

    if name == "synthetic-status":
        _handle_synthetic_status()
        return True

    if name == "provider":
        return _handle_provider_command(command)

    if name == "status":
        if _is_synthetic_only_provider_configured():
            _handle_synthetic_status()
        else:
            emit_warning(
                "Multiple providers appear configured. Use /provider synthetic status."
            )
        return True

    return None


register_callback("custom_command_help", _custom_help)
register_callback("custom_command", _handle_custom_command)
