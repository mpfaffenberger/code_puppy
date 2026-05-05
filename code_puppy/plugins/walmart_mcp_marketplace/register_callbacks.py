"""Plugin entry point for the Walmart MCP marketplace.

Hooks:
    * ``register_mcp_catalog_servers`` — yields BFF entries as catalog
      templates so they appear in the existing ``/mcp install`` TUI.
    * ``startup`` — (a) seeds the PingFed env var from puppy.cfg, and
      (b) rebuilds the catalog singleton so our entries are picked up
      even when another plugin imported the catalog before we got to
      register our hook (load order: walmart_specific < walmart_mcp_marketplace).
    * ``custom_command`` — adds ``/refresh-mcp-marketplace`` to bust the
      24-hour cache.
    * ``custom_command_help`` — advertises the refresh command in /help.

We deliberately do NOT import ``server_registry_catalog`` at module top level —
that would instantiate the singleton during plugin import, before our hook
is registered. All catalog interaction is lazy / inside callback functions.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from code_puppy.callbacks import register_callback
from code_puppy.config import get_value as _get_config_value
from code_puppy.messaging import emit_info, emit_success, emit_warning

from .client import clear_cache, fetch_marketplace
from .log_silencer import install_mcp_log_silencer
from .redirect_patch import apply_streamable_http_redirect_patch
from .templates import PINGFED_ENV_VAR, build_templates

logger = logging.getLogger(__name__)

REFRESH_COMMAND_NAMES = {
    "refresh-mcp-marketplace",
    "mcp-refresh-marketplace",
}


def _provide_catalog_servers():
    """Fetch the BFF (cached) and convert to catalog templates.

    Returns ``list[MCPServerTemplate]`` but the type is imported lazily so
    we don't trigger catalog instantiation at plugin-load time.
    """
    try:
        entries = fetch_marketplace()
    except Exception as exc:  # noqa: BLE001 — never break the catalog
        logger.warning("Walmart MCP marketplace unavailable: %s", exc)
        return []
    templates = build_templates(entries)
    if templates:
        logger.info(
            "Walmart MCP marketplace contributed %d catalog entries", len(templates)
        )
    return templates


def _seed_pingfed_env() -> None:
    """If the user has a marketplace_token saved, expose it as the env var
    our generated Authorization headers reference. Saves a manual `export`.
    """
    if os.environ.get(PINGFED_ENV_VAR):
        return
    try:
        token = _get_config_value("marketplace_token")
    except Exception:  # noqa: BLE001
        token = None
    if token:
        os.environ[PINGFED_ENV_VAR] = token


def _rebuild_catalog_singleton() -> None:
    """Force the global MCP server catalog to rebuild now that all plugins
    have registered, then prune to ONLY the Walmart MCP Marketplace.

    Walmart-only policy: ``/mcp install`` should surface internal servers,
    nothing else. Uninstalling this plugin restores the full catalog.
    """
    try:
        from code_puppy.mcp_ import server_registry_catalog as cat_mod

        # 1. Drop the built-in community templates entirely.
        cat_mod.MCP_SERVER_REGISTRY.clear()

        # 2. Rebuild so plugin hooks get a fresh chance to contribute.
        cat_mod.catalog = cat_mod.MCPServerCatalog()

        # 3. Prune anything contributed by other plugins (e.g. github_enterprise)
        #    so the user only sees the Walmart Marketplace category.
        cat_mod.catalog.servers = [
            s for s in cat_mod.catalog.servers
            if s.category == "Walmart MCP Marketplace"
        ]
        cat_mod.catalog._build_index()

        count = len(cat_mod.catalog.servers)
        logger.info(
            "Catalog locked to Walmart MCP Marketplace only; %d entries available",
            count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not rebuild catalog singleton at startup: %s", exc)


def _on_startup() -> None:
    # Re-seed in case the user ran /marketplace_auth between import and startup
    # (also belt-and-braces in case import-time seeding was skipped for any reason).
    _seed_pingfed_env()
    _rebuild_catalog_singleton()


def _handle_refresh_command(command: str, name: str) -> Optional[bool]:
    """Custom command: ``/refresh-mcp-marketplace``."""
    if name not in REFRESH_COMMAND_NAMES:
        return None

    cleared = clear_cache()
    emit_info("🔄 Refreshing Walmart MCP marketplace from registry...")
    entries = fetch_marketplace(force_refresh=True)
    if not entries:
        emit_warning(
            "Marketplace fetch returned no entries. "
            "Check Walmart VPN/Eagle WiFi connectivity."
        )
        return True

    templates = build_templates(entries)
    suffix = " (old cache cleared)" if cleared else ""
    _rebuild_catalog_singleton()
    emit_success(
        f"✓ Loaded {len(templates)} Walmart MCP servers{suffix}. "
        "Run /mcp install to browse."
    )
    return True


def _refresh_help() -> List[tuple]:
    return [
        (
            "/refresh-mcp-marketplace",
            "Re-fetch Walmart MCP server registry (busts 24h cache)",
        )
    ]


# --- registration ---
# Patch MCP streamable HTTP transport to follow redirects (Walmart gateways
# love their 307s). Applied at import time so it's live before any MCP server
# spins up during the normal startup sequence.
apply_streamable_http_redirect_patch()

# Divert noisy MCP lifecycle tracebacks from the console to per-server log
# files (visible via ``/mcp logs <server>``).
install_mcp_log_silencer()

# Seed PUPPY_MARKETPLACE_TOKEN from saved config NOW — not at startup.
# Why: ManagedMCPServer expands $ENV_VARS in headers ONCE at construction
# time, and MCPManager() can be instantiated before the startup callback
# fires (anyone touching get_mcp_manager() triggers it). If we wait, the
# env var gets baked into headers as the literal string "$PUPPY_MARKETPLACE_TOKEN".
_seed_pingfed_env()

register_callback("startup", _on_startup)
register_callback("register_mcp_catalog_servers", _provide_catalog_servers)
register_callback("custom_command", _handle_refresh_command)
register_callback("custom_command_help", _refresh_help)
