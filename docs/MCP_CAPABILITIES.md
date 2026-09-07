# MCP Server Capabilities

Optional `capabilities` block per server in `~/.code_puppy/mcp_servers.json`.
All keys optional; omitting the block keeps current behavior.

```jsonc
"platform-tools": {
  "type": "stdio",
  "command": "my-platform-mcp",
  "capabilities": {
    "logging": true,
    "min_log_level": "info",
    "progress": true,
    "instructions": false,
    "roots": ["${PWD}"],
    "cache_prompts": true,
    "cache_resources": true
  }
}
```

| Key | Default | Effect |
|---|---|---|
| `logging` | `true` | Server logs written to the file `/mcp logs` reads. |
| `min_log_level` | `info` | `debug`\|`info`\|`notice`\|`warning`\|`error`\|`critical`\|`alert`\|`emergency` |
| `progress` | `true` | Progress logged at `DEBUG` — tells a slow tool call from a hung one. |
| `instructions` | `false` | Off by default: costs prompt tokens. |
| `roots` | `[]` | Paths or URIs. Plain paths become `file://`; `${PWD}` is the launch dir. |
| `cache_prompts` / `cache_resources` | `true` | Cache listings between calls. |

Bad keys and values fall back to defaults rather than failing startup.

`toolset_capabilities()`, `toolset_instructions()`, and `toolset_server_info()`
in `mcp_/toolset_utils.py` return what the server advertised, or `None` before
it starts.

Sampling and elicitation are out of scope — they are server-initiated requests
with a consent and UI surface beyond this change.
