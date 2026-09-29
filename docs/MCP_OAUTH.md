# OAuth for HTTP MCP servers

In `/mcp`'s custom server add/edit form, set the JSON configuration to:

```json
{
  "type": "http",
  "url": "https://your-server.example/mcp",
  "auth": "oauth",
  "timeout": 330
}
```

The HTTP configuration wizard also offers browser-based OAuth. Start the server
normally. On connection, FastMCP handles OAuth discovery, browser authorization,
PKCE, callback state validation and token refresh. Approve the server's requested
permissions in your browser. A loopback callback listener receives the result.

- The endpoint must support the MCP OAuth flow and dynamic client registration
  supported by FastMCP. Servers requiring pre-registered client credentials are
  not covered by this initial configuration option.
- HTTPS is required except for local loopback HTTP servers.
- Do not combine `auth: "oauth"` with an `Authorization` header. Other headers
  remain supported. Omit `auth` to retain existing API-key/header authentication.
- Allow time for browser login: OAuth connections default to a 330-second
  initialization timeout when no explicit `timeout` is configured. Existing
  explicit timeouts are respected; increase a short timeout when enabling OAuth.
- Tokens are kept in memory, not written into the MCP config. Refresh is handled
  during the connection's lifetime; restarting Puppy may require signing in again.
- Headless machines need access to the browser and loopback callback; there is
  no device-code or paste-back flow in this initial implementation.

## Bindings and stopping

After installing a custom server, the agent-selection menu lets you choose which
agents may use it. Space toggles a binding; A toggles auto-start; Enter finishes.
Skipping the menu leaves the server unbound. Change bindings later in `/agents`
using the MCP binding menu.

Unbinding invalidates the current agent's cached tools and cancels an outstanding
start for the server. A local unbind also overrides a JSON agent's declared
binding. Already-running shared connections are not stopped by unbinding alone;
use `/mcp stop <name>` to stop the server globally.

Stop cancels pending startup, including browser authorization waits, as well as
established connections. Stops and startup failures suppress automatic restart
for this Puppy session. Use `/mcp start <name>` to explicitly retry; a new Puppy
process again follows the saved auto-start settings. Closing the local callback
listener does not close an already-open browser tab.
