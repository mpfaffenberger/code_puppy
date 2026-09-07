# MCP Server Capabilities

Code Puppy has historically consumed one MCP capability: **tools**. The MCP
protocol defines several more, and `MCPToolset` (pydantic-ai) already speaks
them — they just weren't switched on.

This adds an optional per-server `capabilities` block to each entry in
`~/.code_puppy/mcp_servers.json`.

## Config

Every key is optional; omitting the block keeps current behavior.

```jsonc
{
  "platform-tools": {
    "type": "stdio",
    "command": "my-platform-mcp",
    "args": ["--stdio"],

    "capabilities": {
      "logging": true,          // route server logs into /mcp logs
      "min_log_level": "info",  // debug|info|notice|warning|error|critical|alert|emergency
      "progress": true,         // record progress notifications
      "instructions": false,    // inject server instructions into the prompt
      "roots": ["${PWD}"],      // workspace dirs advertised to the server
      "cache_prompts": true,
      "cache_resources": true
    }
  }
}
```

| Key | Default | Effect |
|---|---|---|
| `logging` | `true` | Server `notifications/message` are written to the server's log file. |
| `min_log_level` | `info` | Client-side severity filter (see note below). |
| `progress` | `true` | Progress notifications logged at `DEBUG` — answers "is this slow tool hung?" |
| `instructions` | `false` | Off by default: instructions are injected into the prompt and cost tokens. |
| `roots` | `[]` | Paths or URIs. Plain paths are converted to `file://`; `${PWD}` resolves to the launch directory. |
| `cache_prompts` / `cache_resources` | `true` | Cache listings between calls. |

Logging and progress default **on** because they only write to the existing
rotated log file that `/mcp logs` already reads — no new UI, no prompt-token
cost. Anything that changes what the model sees (`instructions`) is opt-in.

Unknown keys and out-of-range values are ignored rather than rejected;
`mcp_servers.json` is hand-edited, and a typo shouldn't take a working server
offline.

## Reading it back

`code_puppy/mcp_/toolset_utils.py` exposes `toolset_capabilities()`,
`toolset_instructions()`, and `toolset_server_info()`. These read what the
server advertised during the handshake.

They return `None` before the server has been started — the underlying
pydantic-ai properties raise `AttributeError` ("only available after
initialization"), so callers rendering a mix of running and stopped servers
don't need a `try`/`except` at every site.

## Why no `sampling` or `elicitation`

Both work on the currently pinned stack (`fastmcp` 3.x, `mcp` 1.x), where
every session is a legacy-protocol session. They are excluded here for
forward compatibility.

SEP-2575 made MCP stateless. Under `fastmcp` 4 with MCP SDK v2, the client
probes `server/discover` and may negotiate a **modern session**, which holds
no connection for the server to issue requests back over. Sampling and
elicitation are server-initiated *requests*, so pydantic-ai refuses them and
warns at connect time:

```
`elicitation_handler` will never be called: ... negotiated a modern MCP
session, which holds no connection for the server to issue sampling or
elicitation requests over.
```

Logging and progress survive that negotiation because they are one-way
*notifications* that ride the response stream. Every capability documented
above therefore works on both protocol eras.

Supporting sampling or elicitation on a modern session means pinning the
connection back to the legacy era via a pre-built
`fastmcp.Client(mode="legacy")` — a protocol downgrade rather than a feature
flag, and better handled as an explicit per-server opt-in if it's wanted.

## Why `log_level` is never sent

The modern protocol has no `logging/setLevel`; the server sends every level
and leaves filtering to the client. Sending it makes pydantic-ai warn that it
"was not applied". `min_log_level` is therefore applied client-side in the
log handler, which behaves identically on both eras.
