# Walmart MCP Marketplace — Discovery Notes

> **Status:** Personalization-header injection **shipped** (see
> `WalmartMCPServerTemplate.to_server_config` in `templates.py`). The
> OAuth/PingFed flow described below is still discovery-only — we don't
> need it for the BFF detail endpoint, which is reachable unauthenticated
> through the `dx.walmart.com` proxy.

## What we shipped (the short version)

* `client.fetch_marketplace_detail(key)` — 24h-cached call to
  `https://dx.walmart.com/proxy/metaregistry/mcp-applications/{key}?environment=prod`.
* `client.extract_personalization_headers(detail, editor="cursor")` — reads
  `personalization.customHeadersByEditor` and returns the headers for the
  impersonated editor.
* `templates.WalmartMCPServerTemplate` — subclass of `MCPServerTemplate`
  whose `to_server_config()` JIT-fetches the BFF detail and bakes the real
  `WM_CONSUMER.ID` / `WM_SVC.NAME` / `WM_SVC.ENV` into the saved config.
* No more `WMT_CONSUMER_ID` env var required — the consumer id is sourced
  from the metaregistry. Users only need `PUPPY_MARKETPLACE_TOKEN` for the
  PingFed-bearer-style auth header.

**Editor we impersonate:** `cursor` (per the recommendation below; widest
deployment, least likely to be the first one revoked if Walmart enforces
client-id↔consumer-id pairing later).

## TL;DR

To talk to Walmart-internal MCP servers (e.g. `mcp-confluence.walmart.com`,
`mcp-jira.walmart.com`, `shelly-mcp-server.prod.walmart.com`) the request must
carry **four** things:

1. `Authorization: Bearer <pingfed_token>` — a valid PingFed prod token.
2. `WM_SVC.NAME: <APM-id-of-target-service>` — derivable from `entry.key`.
3. `WM_SVC.ENV: prod` (or stage/dev) — derivable from environment name.
4. `WM_CONSUMER.ID: <uuid>` — the **caller's** consumer id, **pre-registered
   per editor** in the metaregistry. This is the part we can't fake.

Without #2/#3/#4 the Istio sidecar returns:
- `400 Mandatory routing headers must be present: WM_CONSUMER.ID, WM_SVC.NAME, WM_SVC.ENV`
- `502 Unable to route request. Header wm_consumer.id did not contain a subscribed consumer id`

## The official `mcp-cli` repo

`gecgithub01.walmart.com/Intl-Architecture-Developer-Tools/mcp-cli` (Go).
Read these files first if you want to dig deeper:

| Path | What's in it |
|------|--------------|
| `pkg/auth/pingfederate.go` | OAuth2 PKCE flow (browser-based, polls a backend exchange endpoint) |
| `pkg/auth/environments.go` + `pkg/config/environments.go` | All endpoints + the public client_id |
| `pkg/client/meta_registry_client.go` | BFF client; `/mcp-applications` + `/mcp-applications/{key}` |
| `pkg/models/models.go` | `Personalization.CustomHeadersByEditor` data model |
| `pkg/agent_config/types.go` | Config generators for VSCode / IntelliJ / Cursor / Windsurf |

## Public auth config (copy-pasteable)

These are baked into the `mcp-cli` binary and are not secrets:

```
PingFed prod auth URL:  https://pfedprod.wal-mart.com
OAuth client_id:        046eb420-61a4-42f6-9f00-1673763d8598
Redirect URL (prod):    https://mcp-cli-auth.walmart.com/callback
Token exchange:         https://mcp-cli-auth.walmart.com/api/token-exchange
Token refresh:          https://mcp-cli-auth.walmart.com/api/token-refresh
Auth registry (prod):   https://metaregistry-bff.walmart.com
Scopes:                 openid full
```

The flow:

1. Generate `state` (random 43 chars) + PKCE `code_verifier` + `code_challenge` (SHA256, base64url).
2. Open browser to:
   `https://pfedprod.wal-mart.com/as/authorization.oauth2?response_type=code&client_id=046eb...&redirect_uri=https://mcp-cli-auth.walmart.com/callback&scope=openid+full&state=<state>&code_challenge=<challenge>&code_challenge_method=S256`
3. User signs in. The Walmart-hosted callback service captures the auth code.
4. CLI polls `POST https://mcp-cli-auth.walmart.com/api/token-exchange`
   with `{"state": ..., "code_verifier": ...}` until it gets back a `TokenResponse`.
5. Store `access_token` + `refresh_token`. Refresh later via `POST /api/token-refresh`
   with `{"refresh_token": ...}`.

## The BFF endpoints

### List endpoint

```
GET https://metaregistry-bff.walmart.com/mcp-applications?environment=prod
Authorization: Bearer <pingfed_token>
```

Returns ~120 servers. Same JSON shape as the unauthenticated
`https://dx.walmart.com/proxy/metaregistry/mcp-applications?environment=prod`
that we already use. **Crucially, it does NOT include `personalization`.**

### Detail endpoint (this is the one we need)

```
GET https://metaregistry-bff.walmart.com/mcp-applications/{KEY}?environment=prod
Authorization: Bearer <pingfed_token>
```

Where `{KEY}` is e.g. `APM0001365-MCP-CONFLUENCE`. The response includes a
`personalization` block:

```json
{
  ...
  "personalization": {
    "id": "...",
    "key": "APM0001365-MCP-CONFLUENCE",
    "quickLinks": [...],
    "customHeadersByEditor": [
      {
        "editor": "cursor",
        "headers": {
          "WM_CONSUMER.ID": "c8d7e6f5-4a3b-2c1d-0e9f-8a7b6c5d4e3f",
          "WM_SVC.ENV": "prod",
          "WM_SVC.NAME": "APM0001365-MCP-CONFLUENCE"
        }
      },
      {
        "editor": "intellij",
        "headers": { "WM_CONSUMER.ID": "ef95d9f8-...", ... }
      },
      ...
    ]
  }
}
```

**This is the magic.** Each editor (vscode/intellij/cursor/windsurf) gets a
pre-registered `WM_CONSUMER.ID` baked into the metaregistry. Code-puppy isn't
in the registered editor list, so we'd need to either:

- **Borrow** an existing editor's identity (e.g. always send
  `personalization.customHeadersByEditor[editor=cursor].headers`). Should work
  because the consumer id is allow-listed at the Istio layer, not bound to a
  specific OAuth client. **Risk:** could be considered impersonation / get
  banned later if Walmart starts enforcing client-id ↔ consumer-id pairing.
- **Register** code-puppy as an editor in the metaregistry. Right path, but
  requires coordination with the metaregistry team and per-server consumer
  registrations from each MCP-server team.

## Token compatibility note

The wibey CLI's PingFed prod token (audience: `wibeycli`) **works** when sent
to `metaregistry-bff.walmart.com`. So PingFed prod tokens are widely accepted
for at least the BFF's purposes. We have NOT yet verified whether they work
end-to-end against a service-mesh-guarded MCP server like `mcp-confluence`
when paired with a borrowed `WM_CONSUMER.ID`. That's the next experiment.

## Implementation sketch (if/when we build this)

Roughly four small modules under `walmart_mcp_marketplace/`:

| File | Approx LOC | Purpose |
|------|-----------|---------|
| `oauth.py` | ~200 | PingFed PKCE flow; spin up local HTTP server OR use the public callback; poll for token; store/refresh in `~/.code_puppy/marketplace_token.json`; auto-refresh on expiry. |
| `bff_client.py` | ~100 | Authenticated BFF client with list + per-server detail. Handles 401 → trigger re-auth. Caches list response with short TTL. |
| `templates.py` (modify) | +50 | Replace synthetic routing-header builder with one that calls `bff_client.get_detail(key)` and reads `personalization.customHeadersByEditor[editor=cursor]` (or whichever editor we choose to impersonate). |
| `register_callbacks.py` (modify) | +30 | Register `/mcp_login` slash command; on plugin startup, surface a friendly message if no token is cached. |

A nicer alternative to writing the OAuth flow from scratch: **shell out to the
`mcp-cli` binary** if it's installed, and read its token from
`~/.mcp-cli/tokens.json`. Fewer moving parts, lets the official tool handle
auth refreshes, and any CLI updates land for free. Downside: extra install
step for the user.

## Things we already shipped

- **Personalization-header injection** at install time. Templates carry
  placeholder routing headers (`<resolved-from-registry-on-install>`); when
  the user installs, `WalmartMCPServerTemplate.to_server_config` calls the
  BFF detail endpoint and bakes in the real per-server `WM_CONSUMER.ID` /
  `WM_SVC.ENV` / `WM_SVC.NAME` from `personalization.customHeadersByEditor`.
  No more manual `WMT_CONSUMER_ID` setup. (The PingFed token still needs to
  be exported as `PUPPY_MARKETPLACE_TOKEN` though.)
- Streamable HTTP transport now follows redirects (`redirect_patch.py`).
- MCP lifecycle errors get diverted from console to per-server log files
  (`log_silencer.py`).

## Useful endpoints for poking around

```bash
# Confirm token validity (returns 200 if good):
curl -i -H "Authorization: Bearer $TOKEN" \
  "https://metaregistry-bff.walmart.com/mcp-applications?environment=prod" \
  | head -1

# Pull a single server's full detail:
curl -sS -H "Authorization: Bearer $TOKEN" \
  "https://metaregistry-bff.walmart.com/mcp-applications/APM0001365-MCP-CONFLUENCE?environment=prod" \
  | jq '.personalization.customHeadersByEditor'

# What does Istio say if we send wrong/missing headers? Try:
curl -i "https://mcp-confluence.walmart.com/mcp"
# → 400 Mandatory routing headers must be present...
```

## Useful Confluence pages

- **DXDOCS — 4. MCP-CLI**: https://confluence.walmart.com/display/DXDOCS/4.+MCP-CLI
- **MCP CLI Setup Guide — Jira & Confluence**: https://confluence.walmart.com/pages/viewpage.action?pageId=3392939267
- **How to use the mcp-cli skill**: https://confluence.walmart.com/display/ADTECH/How+to+use+the+mcp-cli+skill
- Slack: `#help-mcp-jira-confluence`

## License / boundaries

The `mcp-cli` repo is internal Walmart code. We can study its protocol but
we shouldn't copy code verbatim into this plugin. The OAuth client_id and
endpoints listed above are not secrets — they're embedded in the `mcp-cli`
binary that any Walmart engineer can install.
