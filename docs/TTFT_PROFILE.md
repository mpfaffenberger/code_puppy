# TTFT profile: where a cold `code-puppy -p hi` spends its time

Measured on macOS / Python 3.14 / pydantic-ai 2.35 against
`claude-code-claude-fable-5-1`, stdout piped. Numbers are typical of ~10
runs; treat them as ±15%.

## Is the byte stream itself slow?

No. The run goes through `pydantic_agent.run(event_stream_handler=...)`,
and the hop from the first HTTP body chunk (`httpx2`, via
`ClaudeCacheAsyncClient`) to the first `stream_event` callback is ~30ms.
The overhead is everything *around* the stream.

## Timeline before the fixes

```
 0.00  process start
 1.25  cli_runner imported            <- imports
 1.37  startup callback               <- blocking PyPI version check in here
 1.48  agent_run_start                <- agent build (tool schemas, config reads)
 1.51  POST /v1/messages              <- ~1.5s of our overhead before the request leaves
 2.38  response headers               <- Anthropic TTFB (TLS to them is ~23ms; not ours)
 3.2   first text delta               <- model-side
 4.45  last byte
 5.53  agent_run_end                  <- 1.08s typewriter drain, into a pipe
 5.7   atexit, then ~0.5s interpreter teardown
```

## What we owned, and what was done

| Cost | Cause | Fix |
|---|---|---|
| ~1.0s per text part | `SmoothTermflowWriter` drains `ceil(remaining/42)` per 12ms tick (exponential decay: the last ~42 chars always crawl at 1 char/tick). Ran even when stdout was a pipe. | Smoothing is gated on `isatty()` (`agents/smooth_stream.py`). Upstream, termflow's drain quota is now pinned to the burst's high-water mark, so the drain is linear and really finishes inside `catch_up_seconds` (~0.5s) instead of decaying past it. Still smooth. |
| 75–170ms good wifi, up to **5s** bad | `httpx.get(pypi.org)` on the startup critical path, 5s timeout, headless too. | Fetch runs on a daemon thread; result lands on the message bus when it arrives (`version_checker.py`). |
| **~1.2s on every exit** | `reset_unix_terminal()` shelled out to `reset(1)`; `tset` sleeps one second by design (a settling delay for hardware terminals), and with `capture_output=True` its escape codes never reached the terminal anyway — a one-second no-op in `main_entry`'s `finally`. | `stty sane` + targeted escape codes (soft reset, attrs off, cursor visible, alt-screen off, mouse tracking off), skipped entirely off-tty (`terminal_utils.py`). Deliberately not RIS: `reset(1)`'s full init clears the screen. |
| ~170ms (anthropic) + ~200ms (openai) | `model_factory.py` and `provider_identity.py` imported both vendor SDKs at module scope. `agents/_runtime.py` imported both for `isinstance` checks. | Function-local imports per provider branch; `_sdk_exception()` peeks `sys.modules` (an SDK exception can only exist if the SDK is loaded). `ZaiChatModel` moved to `zai_model.py`. |
| ~54ms pre-request, then 10–20 reads per streamed chunk | `config.get_value()` re-read and re-parsed `puppy.cfg` on every call — 388 times for one "hi". | Parser cached on `(path, inode, mtime_ns, size)`; `mutate_config`'s atomic replace rolls the key (`config.py`). |

## Result

Cold `-p hi` on a TTY: **~4.5s wall, of which ~3s is Anthropic**
(TTFB + generation). Code-puppy overhead went from ~3.3s to ~1.1s:
~0.9s to get the request out, ~0.5s of *intended* typewriter catch-up,
~0.2s exit. `openai`/`anthropic` no longer load at startup at all
(fixed in `code_puppy_core_plugins` ollama + here; needs the plugin
release ≥0.0.40 and a termflow-md release with the linear drain).

## Still on the table

* **Upstream: `pydantic_ai.capabilities.mcp` eagerly imports
  `pydantic_ai.mcp`** → fastmcp → key_value → beartype → `mcp.types`
  (~186ms on every `import pydantic_ai`, MCP servers or not). A lazy import
  inside the `MCP` capability would fix it. Needs an upstream proposal.
* `anthropic` SDK 1.0 imports every `types.beta.*` module eagerly (~100ms).
  Anthropic's problem.
* `messaging.rich_renderer` → `tools.common` → `tools` → `browser` →
  playwright at import (~30ms). Layering smell more than a perf bug.

## Reproducing

The throwaway tracer used for this lives outside the repo
(`/tmp/ttft_trace.py`): it stamps phases from process start via the
`startup` / `agent_run_start` / `stream_event` / `agent_run_end` hooks,
wraps `httpx.AsyncClient.send` and `httpx2.AsyncClient.send` to time
headers and body chunks, and samples the main thread's stack every 10ms
from a daemon thread (`sys._current_frames()`) — py-spy needs root on
macOS. Import costs came from `python -X importtime` rolled up by top-level
package.
