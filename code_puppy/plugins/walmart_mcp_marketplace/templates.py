"""Convert Walmart metaregistry entries → MCPServerTemplate objects.

The metaregistry entry schema (relevant bits)::

    {
      "id": "...uuid...",
      "key": "ARK-MCP-SERVER",
      "name": "ark-mcp-server",
      "description": "...",
      "githubUrl": "...",
      "teamName": "ComputeMgmt",
      "tags": "ark,packages,cves",
      "environments": [
        {
          "name": "prod",
          "mcpCapability": {
            "displayName": "Ark MCP Server",
            "url": "https://ark-mcp-server.walmart.com",
            "endpoint": "/mcp/",
            "auth": {"type": "PingFed Token"},
            "protocol": {"transport": "Streamable-HTTP", "version": "2025-03-26"}
          }
        }
      ]
    }
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Iterable, List, Optional, Tuple

from code_puppy.mcp_.server_registry_catalog import (
    MCPServerRequirements,
    MCPServerTemplate,
)

from .client import extract_personalization_headers, fetch_marketplace_detail

logger = logging.getLogger(__name__)

# Single category so the listing is tidy in the existing TUI.
WALMART_CATEGORY = "Walmart MCP Marketplace"

# Env var users set (or that the plugin auto-populates from puppy.cfg) so the
# Authorization header has something to expand. Matches the token saved by
# /marketplace_auth.
PINGFED_ENV_VAR = "PUPPY_MARKETPLACE_TOKEN"

# Walmart Istio service mesh requires three routing headers on every request:
#   * WM_SVC.NAME  — the upstream service id
#   * WM_SVC.ENV   — environment name (e.g. "prod")
#   * WM_CONSUMER.ID — the *caller's* registered consumer id
#
# Per DISCOVERY_NOTES.md, the metaregistry BFF stores all three of these
# headers per-server, pre-registered for editors (cursor/intellij/vscode/
# windsurf). Code-puppy isn't a registered editor, so we impersonate one
# whose consumer id is allow-listed at the Istio layer. ``cursor`` is the
# default — widest deployment, least likely to be the first one revoked.
IMPERSONATED_EDITOR = "cursor"

# Sentinel header values written into the template at build time. They get
# swapped for the real per-server values at install time by
# ``WalmartMCPServerTemplate.to_server_config``. The placeholder strings make
# the install confirmation screen + ``/mcp logs`` output readable when the
# BFF detail call fails (you can see exactly which header didn't resolve).
_PLACEHOLDER_CONSUMER_ID = "<resolved-from-registry-on-install>"


def _normalize_url(url: str, endpoint: str) -> str:
    """Stitch base url + endpoint, fixing schemeless URLs from the registry.

    We deliberately strip any trailing slash from the final URL. Why:
    several Walmart MCP servers (notably ``shelly-mcp-server``) issue a
    307 redirect from ``/mcp/`` to ``/mcp`` *AND* downgrade the scheme
    from HTTPS to HTTP. httpx then strips the ``Authorization`` header on
    the cross-scheme redirect, producing a confusing 401 "Missing or
    invalid Authorization header". Hitting the canonical (no-slash) URL
    directly skips the redirect and the auth header sticks. FastAPI /
    Starlette MCP servers route ``/mcp`` and ``/mcp/`` equivalently, so
    this is safe in practice.
    """
    base = (url or "").strip()
    ep = (endpoint or "").strip()
    if base and not re.match(r"^https?://", base):
        base = "https://" + base
    if ep and not ep.startswith("/"):
        ep = "/" + ep
    full = base + ep
    # Trim trailing slash, but only on the path — never collapse the
    # bare scheme/host (e.g. "https://host/" stays as "https://host").
    if full.endswith("/") and full.count("/") > 3:
        full = full.rstrip("/")
    return full


def _transport_to_type(transport: str) -> Optional[str]:
    """Map metaregistry transport string → ManagedMCPServer type."""
    if not transport:
        return None
    t = transport.strip().lower()
    if t in ("streamable-http", "streamable_http", "streamablehttp", "http"):
        return "http"
    if t == "sse":
        return "sse"
    return None


def _routing_headers(entry: dict, env_name: str) -> Tuple[dict, List[str]]:
    """Build the placeholder Walmart Istio routing headers for an MCP server.

    These are sentinels — the real per-server values come from the BFF detail
    endpoint at install time (see ``WalmartMCPServerTemplate.to_server_config``).
    Returning placeholders here means: (a) the install confirmation screen
    still shows the user that routing headers will be sent, and (b) if the
    detail fetch fails we degrade to obviously-broken values that produce
    actionable error messages instead of silent 502s.
    """
    svc_name = (entry.get("key") or "").strip()
    if not svc_name:
        return ({}, [])
    return (
        {
            "WM_SVC.NAME": svc_name,
            "WM_SVC.ENV": (env_name or "prod").lower(),
            "WM_CONSUMER.ID": _PLACEHOLDER_CONSUMER_ID,
        },
        [],  # No env var dependency — we resolve from the BFF instead.
    )


def _auth_headers(auth_type: str) -> Tuple[dict, List[str]]:
    """Return (headers_dict, env_var_names) for a given auth type.

    Most Walmart MCP servers want a PingFed bearer token. Anything we don't
    recognize gets no auth headers — user can edit the saved server later.
    """
    a = (auth_type or "").strip().lower()
    if a in ("pingfed token", "pfed", "pingfed", "pingfed bearer"):
        return (
            {"Authorization": f"Bearer ${PINGFED_ENV_VAR}"},
            [PINGFED_ENV_VAR],
        )
    if a == "github pat":
        return (
            {"Authorization": "Bearer $GITHUB_PERSONAL_ACCESS_TOKEN"},
            ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        )
    if a == "api key":
        return (
            {"Authorization": "Bearer $WALMART_MCP_API_KEY"},
            ["WALMART_MCP_API_KEY"],
        )
    # "none", "app2app", "" → no headers; anything app2app-y will need
    # the user's network/identity to handle it natively.
    return ({}, [])


def _safe_id(key: str, name: str) -> str:
    """Build a short, deterministic id that won't clash with existing catalog."""
    raw = (key or name or "walmart-mcp").lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "walmart-mcp"
    return f"wmt-{raw}"


class WalmartMCPServerTemplate(MCPServerTemplate):
    """MCPServerTemplate that resolves routing headers at install time.

    The base template ships with placeholder values for the three Walmart
    Istio routing headers (``WM_SVC.NAME`` / ``WM_SVC.ENV`` / ``WM_CONSUMER.ID``).
    When the user installs the server, ``to_server_config`` calls the BFF
    detail endpoint, pulls ``personalization.customHeadersByEditor`` for the
    impersonated editor (default: cursor), and bakes the real values into
    the saved config. End result: zero manual env-var setup.

    We deliberately fetch only at install time — not at catalog-build time —
    to avoid spamming the BFF with 120 detail calls every time someone runs
    ``/mcp install``.
    """

    # Plain attribute (not a dataclass field). Avoids a clash with the parent
    # dataclass's ``__init__`` ordering rules; we set it via the keyword arg
    # in ``_entry_to_template`` and ``__init__`` below.
    registry_key: str = ""

    def __init__(self, *args, registry_key: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self.registry_key = registry_key

    def to_server_config(
        self, custom_name: Optional[str] = None, **cmd_args
    ) -> dict:
        config = super().to_server_config(custom_name=custom_name, **cmd_args)
        self._inject_personalization_headers(config)
        return config

    def _inject_personalization_headers(self, config: dict) -> None:
        """Replace placeholder routing headers with real BFF-sourced values.

        Mutates ``config`` in place. Silently no-ops when the BFF is
        unreachable AND no cached detail exists — in that case the saved
        config keeps the placeholder values, which produce a clear
        ``WM_CONSUMER.ID`` error from Istio at runtime instead of a silent
        misconfiguration.
        """
        if not self.registry_key:
            return
        headers = config.get("headers")
        if not isinstance(headers, dict):
            return

        try:
            detail = fetch_marketplace_detail(self.registry_key)
        except Exception as exc:  # noqa: BLE001 — install must never crash
            logger.warning(
                "Failed to fetch BFF detail for %s: %s", self.registry_key, exc
            )
            return

        resolved = extract_personalization_headers(
            detail, editor=IMPERSONATED_EDITOR
        )
        if not resolved:
            logger.info(
                "No personalization headers in BFF detail for %s; keeping "
                "placeholder values — server will likely 502 until headers "
                "are configured manually.",
                self.registry_key,
            )
            return

        # Merge: prefer the BFF-resolved values for any header it provides,
        # but keep anything the template added that the BFF doesn't know
        # about (e.g. Authorization).
        merged = copy.deepcopy(headers)
        merged.update(resolved)
        config["headers"] = merged
        logger.info(
            "Injected %d personalization header(s) for %s (editor=%s)",
            len(resolved),
            self.registry_key,
            IMPERSONATED_EDITOR,
        )


def _split_tags(tags_field) -> List[str]:
    """The registry sometimes returns tags as a CSV string, sometimes a list."""
    if not tags_field:
        return []
    if isinstance(tags_field, list):
        return [str(t).strip() for t in tags_field if str(t).strip()]
    if isinstance(tags_field, str):
        return [t.strip() for t in tags_field.split(",") if t.strip()]
    return []


def _entry_to_template(entry: dict) -> Optional[MCPServerTemplate]:
    """Best-effort conversion. Returns None if the entry isn't installable."""
    envs = entry.get("environments") or []
    # Prefer the env literally named/typed PROD; fall back to first.
    chosen = None
    for env in envs:
        if (
            (env.get("type") or "").upper() == "PROD"
            or (env.get("name") or "").lower() == "prod"
        ):
            chosen = env
            break
    if chosen is None and envs:
        chosen = envs[0]
    if chosen is None:
        return None

    cap = chosen.get("mcpCapability") or {}
    url = cap.get("url")
    endpoint = cap.get("endpoint", "")
    if not url:
        return None

    transport = (cap.get("protocol") or {}).get("transport")
    server_type = _transport_to_type(transport)
    if not server_type:
        logger.debug("Skipping %s: unknown transport %r", entry.get("name"), transport)
        return None

    full_url = _normalize_url(url, endpoint)
    auth_type = (cap.get("auth") or {}).get("type", "")
    headers, env_vars = _auth_headers(auth_type)

    # Stack the Walmart routing headers on top — these are required by the
    # Istio sidecar guarding every internal MCP server.
    routing_headers, routing_env_vars = _routing_headers(
        entry, (chosen.get("name") or "prod")
    )
    if routing_headers:
        headers = {**routing_headers, **headers}
        env_vars = list(dict.fromkeys(env_vars + routing_env_vars))

    name = entry.get("name") or entry.get("key") or "walmart-mcp"
    display = cap.get("displayName") or entry.get("key") or name
    desc = (
        entry.get("description")
        or (cap.get("dynamicMetadata") or {}).get("description")
        or "Walmart MCP server (no description provided)"
    )

    tags = _split_tags(entry.get("tags"))
    team = entry.get("teamName")
    if team and team not in tags:
        tags.append(team)
    tags.append("walmart")

    config: dict = {"url": full_url, "timeout": 30}
    if headers:
        config["headers"] = headers

    requires = MCPServerRequirements(
        environment_vars=env_vars,
        system_requirements=(
            ["Walmart VPN or Eagle WiFi", f"Auth: {auth_type or 'none'}"]
        ),
    )

    github_url = entry.get("githubUrl") or ""
    example = f"Source: {github_url}" if github_url else ""

    return WalmartMCPServerTemplate(
        id=_safe_id(entry.get("key") or "", name),
        name=name,
        display_name=display,
        description=desc,
        category=WALMART_CATEGORY,
        tags=tags,
        type=server_type,
        config=config,
        author=team or "Walmart",
        verified=True,
        popular=False,
        requires=requires,
        example_usage=example,
        registry_key=(entry.get("key") or "").strip(),
    )


def build_templates(entries: Iterable[dict]) -> List[MCPServerTemplate]:
    """Convert a list of metaregistry entries into catalog templates."""
    templates: List[MCPServerTemplate] = []
    seen_ids: set[str] = set()
    for entry in entries:
        try:
            tpl = _entry_to_template(entry)
        except Exception as exc:  # noqa: BLE001 — don't blow up the whole catalog
            logger.debug("Skipping bad entry %r: %s", entry.get("name"), exc)
            continue
        if tpl is None:
            continue
        if tpl.id in seen_ids:
            continue
        seen_ids.add(tpl.id)
        templates.append(tpl)
    templates.sort(key=lambda t: t.display_name.lower())
    return templates
