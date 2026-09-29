# Phase B.2.5 — MCP subsystem migration to MCPToolset (report)

Repo: code_puppy @ pydantic-ai 1.107.5. Commits: `8732872f` (mcp_ core + tests),
`56591821` (consumers). Verified against installed 1.107.5 sources and
`git show v2.31.0:...` in the local pydantic-ai checkout.

## Design note — old -> new API mapping

| Old (deprecated, removed in v2) | New (stable in 1.107.5 AND 2.31.0) |
|---|---|
| `MCPServerStdio(command, args, env, cwd, timeout, read_timeout, ...)` | `MCPToolset(fastmcp.StdioTransport(command, args, env, cwd, keep_alive=False, log_file=Path), init_timeout=..., read_timeout=...)` |
| `MCPServerSSE(url, http_client=..., ...)` | `MCPToolset(fastmcp.SSETransport(url, sse_read_timeout=..., httpx_client_factory=...), ...)` |
| `MCPServerStreamableHTTP(url, headers=..., ...)` | `MCPToolset(fastmcp.StreamableHttpTransport(url, headers=...), ...)` |
| `tool_prefix=` kwarg (prefix + strip on call) | `.prefixed(prefix)` -> `PrefixedToolset` (identical `f"{prefix}_{name}"` rendering + strip-on-call) |
| `client_streams()` override for stderr capture | `StdioTransport(log_file=Path)` — public seam; fastmcp appends subprocess stderr to the file per connection |
| `timeout=` (init handshake) | `init_timeout=` (same default 5s; we keep our 60s stdio default) |
| `process_tool_call(ctx, call_tool, name, args)` -> `call_tool(name, args, metadata_positional)` | same callback signature; `metadata` is now **keyword-only**; `call_tool` arrives as `functools.partial(direct_call_tool)` (unwrap `.func` for introspection) |
| bare `ToolSet()` + `._tools[name] = fn` writes | `AbstractToolset.filtered(lambda ctx, tool_def: ...)` -> `FilteredToolset` |
| `server.is_running` / `_running_count` on the object handed to Agent | leaf access via public `WrapperToolset.wrapped` traversal (`mcp_/toolset_utils.py`) |

Explicit transports (not URL strings) are used on purpose: fastmcp's URL
inference picks SSE vs streamable-HTTP from the URL shape, but our user config
declares the type authoritatively. Constructor surface checked in v2.31.0:
`MCPToolset.__init__` there is a strict superset (adds `prefer_tasks`,
`tool_error_behavior='failed'`), so everything used here is in the intersection.

## Architecture

- `ManagedMCPServer` holds `_toolset` (the `MCPToolset` / `BlockingStdioToolset`
  leaf) and `_pydantic_server` (= `_toolset.prefixed(tool_prefix)`), returned by
  `get_pydantic_server()`. Agent and lifecycle manager both enter wrappers over
  the *same* leaf, so fastmcp/pydantic-ai refcounting keeps the single-session
  fast-path (no cross-task cancel-scope regression).
- `BlockingStdioToolset(MCPToolset)` keeps `wait_until_ready` / `ensure_ready` /
  `is_ready` / `get_captured_stderr` and the "/mcp logs" failure hint;
  `StderrFileCapture` is now a pure log-tailer (rotate + markers + in-memory
  deque) since fastmcp writes the stderr.
- `code_puppy/mcp_/captured_stdio_server.py` deleted (zero prod consumers).
- New `code_puppy/mcp_/toolset_utils.py`: `unwrap_toolset`, `toolset_prefix`,
  `toolset_is_running`, `iter_cached_tool_defs` — shared by async_lifecycle,
  _history, token_usage, base_agent (removed duplicated extraction loops).

## Feature-parity checklist

| Requirement | Status |
|---|---|
| 1. All three transports from unchanged user JSON config | DONE — same config keys (`type`, `url`, `command`, `args`, `env`, `cwd`, `headers`, `timeout`, `read_timeout`, `tool_prefix`, `http_client`); mapped internally |
| 2a. stderr capture for stdio | DONE — public `StdioTransport(log_file=...)`; same log files, rotation, session markers, in-memory capture; e2e smoke-verified |
| 2b. blocking startup with timeout | DONE — `_ready_event`/`_init_error` around `MCPToolset.__aenter__`; ExceptionGroup unwrap kept |
| 2c. health monitoring / lifecycle | DONE — async_lifecycle unchanged in behavior, typed on `AbstractToolset`, leaf state via helpers |
| 2d. tool_prefix behavior | DONE — `PrefixedToolset` renders identical names; log filename still keyed by prefix |
| 2e. custom CA bundle / http client injection | DONE — `create_async_client` (bundle/proxy/retry) injected via `httpx_client_factory`; stdio child-env CA inheritance untouched |
| 2f. process_tool_call deps forwarding | DONE — same hook point exists on `MCPToolset`; `metadata={"deps": ctx.deps}` (kw-only); arg-coercion schema lookup unwraps the partial |
| 3. filter_conflicting_mcp_tools on public APIs | DONE — `.filtered()`; zero private writes; filtering now actually works for MCP toolsets (old code only filtered objects with a `.tools` dict, i.e. never real servers, and would have raised ImportError on 1.107.5) |
| 4. Feature gaps | None dropped. One quarantined private *read* remains: `MCPToolset._cached_tools` in `iter_cached_tool_defs` (defensive getattr) because pydantic-ai has no sync tool-listing API in either version — flagged for hop 2 review, attr exists unchanged in v2.31.0 |
| 5. Zero deprecated imports | DONE — `grep MCPServer(Stdio|SSE|StreamableHTTP|HTTP)` in code_puppy/ and tests/: zero (docstring mentions only) |
| 6. Deprecation gate, no exclusions | DONE — full suite with `-W error::pydantic_ai._warnings.PydanticAIDeprecationWarning`: **7203 passed, 26 skipped, 0 failed, 1 xpassed** (xpass = pre-existing non-strict prompt_toolkit xfail, unrelated). Baseline was 7220/26; delta −17 = deleted captured_stdio tests + consolidated rewrites |

## Behavior deltas (intentional, small)

- `filter_conflicting_mcp_tools` returns same-length list (lazy filtering);
  the "Filtered N conflicting MCP tools" console line was removed (no sync count).
- Stdio transports pass `keep_alive=False` (fastmcp default is True) to keep
  old stop-kills-subprocess semantics.
- SSE default-read-timeout of 300s is now set on the transport explicitly
  (matches old `MCPServerSSE` default).

## Residual v2.31.0 deltas deferred to hop 2

- `MCPToolset` gains `prefer_tasks=True` default in v2 (task-augmented
  execution SEP-1686) — review when hopping; no action needed at 1.107.5.
- `tool_error_behavior='failed'` (new option) — optional adoption later.
- `_cached_tools` private read (see checklist item 4) — re-check for a public
  sync surface at hop time.

## Files changed

Core: mcp_/{managed_server,manager,blocking_startup,async_lifecycle}.py,
mcp_/toolset_utils.py (new), mcp_/captured_stdio_server.py (deleted).
Consumers: agents/{_builder,_history,base_agent}.py, token_usage.py.
Tests: tests/mcp/test_blocking_startup.py (rewritten, 40 tests),
tests/mcp/test_managed_server.py (rewritten, 73 tests),
tests/mcp/test_captured_stdio_full_coverage.py (deleted).
