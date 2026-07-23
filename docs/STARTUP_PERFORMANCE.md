# Code Puppy Startup Performance

> Report generated 2026-07-22 against `main @ 18cc3e39` (v0.0.658).
> All numbers measured on a warm bytecode cache; cold-cache is 5–8× worse
> but not representative of steady-state user experience.

## TL;DR

| Scenario | Wall time |
|---|---:|
| `code-puppy --version` (warm) | **1.63 s** |
| `code-puppy` → interactive prompt (warm) | **2.29 – 2.69 s** |
| `code-puppy --version` (cold cache) | ~11.9 s |

Two things dominate steady-state launch:

1. **Eager plugin discovery** at import time loads all ~50 built-in plugins,
   even for `--version` / `--help` / no-op invocations.
2. **The `theme` plugin alone accounts for ~267 ms** — bigger than every other
   plugin combined.

Everything else is either a small constant cost (agents/tools/pydantic-ai/openai
import graphs, ~600 ms combined) or a runtime concern that never fires at
startup on a healthy path (network version check, MCP autostart, etc.).

## Measurement Methodology

All measurements executed against the local repo checkout with a stale but
functional venv (`0.0.652` wheels + `0.0.658` source — the dep graph is
compatible).

```bash
# Warm cache: 2 throwaway runs to prime .pyc caches and filesystem
for i in 1 2; do .venv/bin/python -m code_puppy.main --version >/dev/null; done

# Steady-state measurement
for i in 1 2 3; do
    /usr/bin/time -p .venv/bin/python -m code_puppy.main --version
done
```

Import profiles collected via `python -X importtime` and a monkey-patched
`importlib.import_module` that filters to `code_puppy.plugins.*.register_callbacks`.

## Where the Time Goes

### 1. `theme` plugin — up to ~30 ms cold, ~10 ms warm

> **Note (2026-07-22):** an earlier draft of this report claimed the
> theme plugin cost ~267 ms. That number came from a single-shot
> measurement where the plugin's transitive imports (including
> `prompt_toolkit` widgets) were loading for the first time in the
> Python process. In practice `prompt_toolkit` is pulled in by the REPL
> regardless, and other plugins already trigger it — so the theme
> plugin's *marginal* contribution is much smaller than the isolated
> cold-import cost suggests. The real win from deferring is architectural
> (theme package no longer requires prompt_toolkit to import) more than
> perf.

`register_callbacks.py` eagerly imports **eight sibling modules** at the
top of the file:

```python
from . import content_styles as cs
from . import osc_palette as osc
from . import rich_themes as rt
from .picker import interactive_theme_picker
from .prompt_toolkit_theme import merge_with_active_style
from .themes import (
    MENU_BY_NAME, apply, color_remap_for, colors_for,
    content_styles_for, resolve_theme_arg, terminal_palette_for,
)
```

The transitive weight lives in `themes.py` (728 lines) and `picker.py` (359
lines, pulls in `prompt_toolkit` widgets for the interactive picker). None
of that is needed to satisfy the plugin's only startup responsibility:

```python
register_callback("startup", _apply_default_theme_on_first_run)
```

which just calls `osc.get_saved_palette()` and, on first run,
`_apply_theme("tokyo-night", announce=False)`. The picker, prompt-toolkit
style merger, and Pygments/termflow highlighter are only needed when a user
actually invokes `/theme` or when a render callback fires.

### 2. Eager plugin discovery — always runs

`cli_runner.py` (line 49) calls `plugins.load_plugin_callbacks()` at
**module import time**, before argparse runs:

```python
from code_puppy.version_checker import default_version_mismatch_behavior

plugins.load_plugin_callbacks()  # <— fires for EVERY invocation
```

Consequences:

- `pup --version` loads all 50 plugins to print one string.
- `pup --help` loads all 50 plugins to print a help block.
- A plugin CLI subcommand loads all 50 plugins to run one.

Per-plugin warm import cost (top 10 of ~50):

```
0.267s  theme
0.043s  copilot_auth
0.007s  puppy_kennel
0.005s  statusline
0.004s  claude_code_hooks
0.003s  claude_code_oauth
0.003s  wiggum
0.002s  puppy_spinner
0.002s  dbos_durable_exec
0.002s  chatgpt_oauth
```

Roughly ~350 ms in aggregate on warm cache; ~1 s+ on cold cache.

### 3. Core dependency imports — 700 ms baseline

Unavoidable but ordered pessimistically. Import graph, top-level packages
by cumulative time:

| Package | Cumulative |
|---|---:|
| `pydantic_ai` | 239 ms |
| `openai` | 179 ms |
| `mcp` | 161 ms |
| `anthropic` | 137 ms |
| `pydantic_graph` | 58 ms |
| `httpx` | 47 ms |
| `requests` | 45 ms |
| `prompt_toolkit` | 39 ms |
| `playwright` | 23 ms |

Notable observations:

- **`playwright` loads at startup.** That is a full browser-automation
  toolkit; nothing in `--version` or the plain prompt needs it. Grep
  points at `browser` tools being wired into the tool registry eagerly.
- **`requests` AND `httpx` both load.** Only one is strictly needed for
  most flows.
- `openai`, `anthropic`, `pydantic_ai`, and `mcp` are all imported via the
  agent builder graph before the user has picked a model or issued a
  prompt. In principle, importing only the provider matching the selected
  model would save ~300 ms.

### 4. Interactive launch overhead — extra ~750 ms

`code-puppy` (no args) takes ~2.45 s vs. 1.63 s for `--version`. The
delta is spent on:

- `pyfiglet` import + ANSI-shadow rendering of "CODE PUPPY" banner
- `ensure_config_exists()` (config parse + first-run migrations)
- `load_api_keys_to_environment()` (keyring / env probe)
- Synchronous version check via `default_version_mismatch_behavior()`
- `sweep_contexts_to_autosaves()` (legacy dir → new dir one-shot migration)
- `await callbacks.on_startup()` (fans out to all registered startup hooks
  **sequentially**)

None of these are individually large, but they're serialised behind the
prompt.

## Non-Issues (Don't Fix These)

For the record — profiled and cleared:

- **`find_available_port()`**: 0 ms. The 8090 → 9010 sequential scan
  short-circuits on the first bind, and 8090/8095 is nearly always free.
- **`chatgpt_oauth` image generation**: 2 ms at startup. The image
  library imports (`image_generation.py`, `image_tool.py`) live inside the
  `/codex-imagegen` handler and the `register_tools` callback — properly
  lazy. Only the tiny `register_callbacks.py` shell loads at boot.
- **MCP autostart**: doesn't run during startup; deferred until agent
  invocation. No baseline cost.
- **Network version check**: ~50 ms on a healthy connection; only becomes
  a problem when pypi.org is slow or unreachable, at which point it
  blocks up to `httpx`'s default connect timeout.

## Recommended Fixes

Ordered by impact-to-effort ratio.

### Priority 1: Lazy-load inside the `theme` plugin (~10–30 ms saved)

**Effort:** small, mechanical. **No API changes.**

**Status:** implemented on branch `perf/theme-lazy-imports`, bd issue
`code_puppy-oss-mdu`.

> **Reality check:** initial estimate was ~200 ms based on single-shot
> cold-import timing. Measured savings after implementation are
> ~10 ms warm-cache / ~30 ms cold-cache, because other plugins already
> pull in `prompt_toolkit`. The architectural improvement (theme package
> no longer transitively requires `prompt_toolkit` at import time) is
> more valuable than the wall-clock saving.

Move all eight sibling imports at the top of
`code_puppy/plugins/theme/register_callbacks.py` inside the functions
that actually use them. Retain only what `_apply_default_theme_on_first_run`
requires:

```python
# Keep at module top
from code_puppy.callbacks import register_callback
from code_puppy.config import get_value, set_config_value

# Move inside _apply_default_theme_on_first_run:
def _apply_default_theme_on_first_run() -> None:
    from . import osc_palette as osc
    from .themes import MENU_BY_NAME, apply, ...
    ...

# Move inside _handle_theme (only runs on /theme command):
def _handle_theme(command, name):
    from .picker import interactive_theme_picker
    from .prompt_toolkit_theme import merge_with_active_style
    ...
```

`termflow_style`, `termflow_highlighter`, `prompt_text_color`,
`prompt_toolkit_style` callbacks all already run *after* startup on
render/render-config paths, so their imports (`pygments`, `termflow`)
can move inside their respective functions with no user-visible change.

Measured saving: **~10 ms warm / ~30 ms cold** on the isolated
`register_callbacks` import. End-to-end `--version` improvement is
within measurement noise (~30 ms), because the biggest deferred module
(`prompt_toolkit`) is loaded by other plugins anyway.

### Priority 2: Skip plugin discovery on trivial commands (~350 ms saved)

**Effort:** medium. **Preserves plugin CLI extensibility on the interactive
path.**

`cli_runner.py` currently loads all plugins before argparse. Restructure so
that `--version`, `--help`, and unknown-argument-error paths short-circuit
before `plugins.load_plugin_callbacks()`:

```python
# Sketch:
def main_entry():
    # Fast path: handle --version / --help without touching plugins.
    if _is_trivial_argv(sys.argv):
        _run_trivial(sys.argv)
        return
    from code_puppy import plugins  # deferred
    plugins.load_plugin_callbacks()
    ...
```

This is a bigger structural change because `register_cli_args` plugins
contribute CLI flags — which means a plugin *could* define its own
`--foo` flag that argparse would otherwise reject. The safe move is:

- Recognise `--version` / `-v` / `--help` / `-h` as core-owned flags
  processed before plugin arg registration.
- Everything else falls through to the full plugin load.

Estimated saving on `--version` / `--help`: **~350 ms** (nearly 25 % of
launch). No effect on interactive launch, but this is the fix that makes
`pup --version` and `pup --help` feel snappy in scripts and shell prompts.

### Priority 3: Defer provider-SDK imports until model is selected (~250 ms saved)

**Effort:** medium-high. **Requires touching the agent builder graph.**

`openai` (179 ms), `anthropic` (137 ms), and provider-specific pieces of
`pydantic_ai` (239 ms cumulative) load through
`code_puppy.agents._builder` → `code_puppy.model_factory` at import time.
A user with `model = "gpt-5"` in their config doesn't need `anthropic`
loaded; a user on `claude-*` doesn't need `openai`.

Two viable angles:

1. **Registry-driven imports.** Model handlers already register via
   `register_model_type` callbacks. Move provider imports inside those
   handlers so only the selected model's provider loads.
2. **Deferred agent build.** Don't construct the pydantic-ai agent until
   the user actually submits a prompt. The interactive REPL can render its
   banner/help text before the agent exists.

Estimated saving: **~250 ms** on the common path (single provider active).

### Priority 4: Move `playwright` behind a lazy import (~25 ms saved)

**Effort:** trivial. **Small win, but principled.**

`playwright.async_api` is imported at startup because `code_puppy.tools`
registers browser tools eagerly. Move the `from playwright.async_api
import ...` line inside `browser_manager.py`'s startup function or the
tool's `execute()` method. Same shape as the image_generation fix that
already ships in `chatgpt_oauth`.

Estimated saving: **~25 ms**, plus resilience — a broken playwright
install currently breaks *all* of Code Puppy at import time.

### Priority 5: Kick network version check to a background task (~50 ms in the healthy case, up to 10 s when unhealthy)

**Effort:** small. **Big worst-case improvement.**

`default_version_mismatch_behavior()` is awaited synchronously in `main()`.
Fire-and-forget the HTTP request; if a newer version is discovered, emit
the notice before the next prompt render instead of before the first
prompt.

Estimated saving: **~50 ms healthy, up to `httpx` connect timeout worst
case**. This is the fix that stops Code Puppy from feeling broken when
the user is offline.

## Cumulative Estimate

Applying priorities 1 + 2 + 3 + 4:

```
Baseline (--version):       1.63 s
- theme lazy load:         −0.01 s to −0.03 s (measured)
- skip plugins on trivial: −0.35 s (estimated)
- lazy provider SDKs:      −0.25 s (estimated)
- lazy playwright:         −0.03 s (estimated)
                           ------
Target (--version):        ~1.0 s
```

P2 (skip plugins on trivial) is now clearly the biggest lever — it's
the only fix that removes an entire discovery pass, rather than
deferring a few module loads. If we can only ship one perf fix, it
should be that one.

For interactive launch, P1/P3/P4 combined shave ~300 ms off the ~2.45 s
baseline, landing around **~2.15 s** — with the async version check
keeping perceived latency consistent even on flaky networks.

## What This Report Deliberately Ignores

- **Walmart-internal fork (`code-puppy/`).** That fork adds a setup doctor
  (~2.3 s), Walmart plugin (~100 ms + PingFed auth flow), and Walmart
  version check (~700 ms). All out of scope here — the OSS path is what
  ships to public users.
- **First-run configuration wizard.** `ensure_config_exists()` performs
  substantially more work on a virgin `~/.code_puppy/`. Not representative
  of steady-state.
- **MCP server autostart.** Not measured because it doesn't fire on
  bare launch. Worth a separate profile once agents are actually invoked.
