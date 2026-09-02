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
| ~1.0s per text part | `SmoothTermflowWriter` drains `ceil(remaining/42)` per 12ms tick (exponential decay: the last ~42 chars always crawl at 1 char/tick). Ran even when stdout was a pipe. | Smoothing is gated on `isatty()` (`agents/smooth_stream.py`). Interactive feel is unchanged. |
| 75–170ms good wifi, up to **5s** bad | `httpx.get(pypi.org)` on the startup critical path, 5s timeout, headless too. | Fetch runs on a daemon thread; result lands on the message bus when it arrives (`version_checker.py`). |
| ~170ms (anthropic) + ~200ms (openai) | `model_factory.py` and `provider_identity.py` imported both vendor SDKs at module scope. `agents/_runtime.py` imported both for `isinstance` checks. | Function-local imports per provider branch; `_sdk_exception()` peeks `sys.modules` (an SDK exception can only exist if the SDK is loaded). `ZaiChatModel` moved to `zai_model.py`. |
| ~54ms pre-request, then 10–20 reads per streamed chunk | `config.get_value()` re-read and re-parsed `puppy.cfg` on every call — 388 times for one "hi". | Parser cached on `(path, inode, mtime_ns, size)`; `mutate_config`'s atomic replace rolls the key (`config.py`). |

## Still on the table

* **`openai` still loads on Claude runs (~200ms)** — the `ollama` core
  plugin does `from pydantic_ai.models.openai import OpenAIChatModel` at
  module scope, and plugins load during `cli_runner` import. One-line lazy
  import in `code_puppy_core_plugins/ollama/register_callbacks.py`.
* **Upstream: `pydantic_ai.capabilities.mcp` eagerly imports
  `pydantic_ai.mcp`** → fastmcp → key_value → beartype → `mcp.types`
  (~186ms on every `import pydantic_ai`, MCP servers or not). A lazy import
  inside the `MCP` capability would fix it. Needs a Notes proposal.
* **Typewriter tail in interactive mode** — the exponential drain means
  every text part (including the preamble before each tool call) pays a
  fixed ~0.5–1s tail regardless of length. A linear drain that actually
  finishes within `catch_up_seconds` is a termflow change and a UX
  decision, not made here.
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
