# Contributing to Code Puppy

> **Golden rule:** nearly all new functionality should be a **plugin** under `code_puppy/plugins/`
> that hooks into core via `code_puppy/callbacks.py`. Don't edit `code_puppy/command_line/`.

## How Plugins Work

Plugins are discovered from three tiers, loaded in order:

| Tier | Location | When to use |
|------|----------|-------------|
| **Builtin** | `code_puppy/plugins/<name>/register_callbacks.py` | Core functionality shipped with Code Puppy |
| **User** | `~/.code_puppy/plugins/<name>/register_callbacks.py` | Personal plugins, applied to every project |
| **Project** | `<CWD>/.code_puppy/plugins/<name>/register_callbacks.py` | Repo-specific plugins, shared with your team via git |

All three tiers use the same pattern — drop a `register_callbacks.py` in a named subdirectory:

```python
from code_puppy.callbacks import register_callback

def _on_startup():
    print("my_feature loaded!")

register_callback("startup", _on_startup)
```

That's it. The plugin loader auto-discovers `register_callbacks.py` in subdirs.

### Project Plugins

Project plugins live at `<CWD>/.code_puppy/plugins/<name>/register_callbacks.py`.
This mirrors the project-level discovery already used by agents (`<CWD>/.code_puppy/agents/`)
and skills (`<CWD>/.code_puppy/skills/`).

**Key details:**

- **Directory must be created intentionally.** Code Puppy will never auto-create
  `.code_puppy/plugins/` — your team opts in by creating it.
- **Disabled by default (trust gate).** Project plugins run arbitrary repo
  code at import time, so none load until the user accepts them in the
  `/plugins` TUI ceremony (select → Enter → type `trust`); accepted plugins
  hot-load with no restart. Trust is a SHA-256 of the plugin dir, stored
  user-side in `~/.code_puppy/trusted_plugins.json` and scoped to the project
  path — any file change reverts the plugin to untrusted, and everything else
  fails closed. `/plugins revoke <name>` removes trust. Full security model:
  `code_puppy/plugins/trust.py`.
- **Keep runtime state out of the plugin dir** — writing state (SQLite,
  caches, logs) next to the code self-tampers the hash and demands
  re-acceptance every boot. Use `~/.code_puppy/` like builtin plugins do, or
  a dot-path (e.g. `.state/`), which is excluded from hashing.
- **Load order is builtin → user → project.** Project plugins load last, giving
  them highest precedence for override-style hooks.
- **Project wins on name collision.** If a project plugin shares a name with a
  user plugin, only the project copy loads (the user plugin is skipped). This
  matches how agents deduplicate — `discover_json_agents()` overwrites user
  agents with project agents of the same name. A warning is logged when a
  project plugin shadows a builtin.
- **Module namespace isolation.** Project plugins use `project_plugins.<name>.register_callbacks`
  in `sys.modules`, so they never collide with user plugins at the import level.

## Available Hooks

`register_callback("<hook>", func)` — deduplicated, async hooks accept sync or async functions.

| Hook | When | Signature |
|------|------|-----------|
| `startup` | App boot | `() -> None` |
| `shutdown` | Graceful exit | `() -> None` |
| `invoke_agent` | Sub-agent invoked | `(*args, **kwargs) -> None` |
| `agent_exception` | Unhandled agent error | `(exception, *args, **kwargs) -> None` |
| `agent_run_start` | Before agent task | `(agent_name, model_name, session_id=None) -> None` |
| `agent_run_end` | After agent run | `(agent_name, model_name, session_id=None, success=True, error=None, response_text=None, metadata=None) -> None` |
| `load_prompt` | System prompt assembly | `() -> str \| None` |
| `run_shell_command` | Before shell exec | `(context, command, cwd=None, timeout=60) -> dict \| None` (return `{"blocked": True}` to block, `{"rewrite": "<new cmd>"}` to transparently transform) |
| `file_permission` | Before file op | `(context, file_path, operation, ...) -> bool` |
| `pre_tool_call` | Before tool executes | `(tool_name, tool_args, context=None) -> Any` |
| `post_tool_call` | After tool finishes | `(tool_name, tool_args, result, duration_ms, context=None) -> Any` |
| `custom_command` | Unknown `/slash` cmd | `(command, name) -> True \| str \| None` |
| `custom_command_help` | `/help` menu | `() -> list[tuple[str, str]]` |
| `register_tools` | Tool registration | `() -> list[dict]` with `{"name": str, "register_func": callable}` |
| `register_agent_tools` | Advertise tools to an agent's available list | `(agent_name: str \| None) -> list[str]` — tool names from `TOOL_REGISTRY` to merge into the agent's hardcoded `get_available_tools()` |
| `register_agents` | Agent catalogue | `() -> list[dict]` with `{"name": str, "class": type}` |
| `register_model_type` | Custom model type | `() -> list[dict]` with `{"type": str, "handler": callable}` |
| `register_skills` | Skill catalogue | `() -> list[dict]` with `{"name": str, "skill_md" \| "skill_md_path" \| "frontmatter"+"body"}` |
| `register_cli_args` | Before CLI `parse_args()` | `(parser) -> list` — plugins call `parser.add_argument(...)`; namespace flags (e.g. `--myplugin-foo`) to avoid argparse collisions |
| `handle_cli_args` | After CLI `parse_args()` | `(args) -> dict \| None` — return `{"handled": True, "exit_code": int}` to terminate the CLI cleanly; return `None` to let startup proceed |
| `register_screen` | Textual TUI menu/screen | `() -> list[dict]` with `{"command": str, "open": callable(app)}` (opt. `"aliases": list[str]`). Bare `/command` opens the screen in the Textual UI; no-op in classic. |
| `load_model_config` | Patch model config | `(*args, **kwargs) -> Any` |
| `load_models_config` | Inject models | `() -> dict` |
| `load_model_descriptions` | Inject description overlays | `() -> dict[str, str]` |
| `get_model_system_prompt` | Per-model prompt | `(model_name, default_prompt, user_prompt) -> dict \| None` |
| `stream_event` | Response streaming | `(event_type, event_data, agent_session_id=None) -> None` |
| `pre_mcp_autostart` | Before bound MCP servers auto-start | `(agent_name, server_names) -> None` (refresh tokens / mint creds here) |

Full list + rarely-used hooks: see `code_puppy/callbacks.py` source.

## Ctrl+X Chords

`Ctrl+X` is a **chord prefix** (readline-style), never a standalone hotkey. The
line editor arms a pending state on `Ctrl+X`, paints a hint of the currently
registered bindings on the bottom bar, and resolves the NEXT key against the
chord registry in `code_puppy/messaging/chords.py`. `Esc` (or any unbound key)
cancels the chord; unbound keys are then processed normally.

| Chord | Action | Registered by | Active when |
|-------|--------|---------------|-------------|
| `Ctrl+X Ctrl+E` | Edit the prompt buffer in `$VISUAL`/`$EDITOR` | `run_ui` | Always (UI lifetime) |
| `Ctrl+X Ctrl+X` | Kill all running shell commands | `command_runner` | While shell commands run |
| `Ctrl+X Ctrl+B` | Background all running shell commands | `command_runner` | While shell commands run |

**Design notes:**

- **No modes.** This replaced a modal design where a bare `Ctrl+X` meant
  "kill shells if a handler happened to be armed, editor chord otherwise" --
  the arm/disarm lifecycle raced against keystrokes. Now `Ctrl+X` always
  flows into the editor; the registry decides what the follow-up key does.
- **Backgrounding is mid-flight detach.** `Ctrl+X Ctrl+B` makes every
  streaming shell tool call return immediately with `background=True`,
  `log_file`, and `pid`; the process keeps running and its remaining output
  diverts to the log file (readers keep the pipes drained).
- **Headless fallback.** With no line editor installed (piped stdin, embeds),
  a bare `Ctrl+X` keeps its historical kill-all-shells meaning via the
  listener's spawn-time `on_escape` callback.

**Plugins can register their own chords:**

```python
from code_puppy.messaging.chords import register_chord, unregister_chord

register_chord("\x14", my_callback, "Ctrl+T do the thing")  # Ctrl+X Ctrl+T
```

Rules for chord callbacks: they run on the key-listener thread, so **never
block** (hop to the asyncio loop's executor like the `$EDITOR` handler in
`messaging/external_editor.py`); never raise (failures are swallowed and
logged); register only while the binding is meaningful so the armed-chord
hint stays honest. Keys are single raw control characters -- prefer
`Ctrl+<letter>` bytes; digits and F-keys are deliberately unsupported.

## Internationalization (i18n)

User-facing CLI/TUI strings are localizable via `code_puppy/i18n/`. See
**`docs/I18N.md`** for the full guide (architecture, decisions, translator
quickstart). Rules for new user-facing output (PUP-473):

- **Wrap display strings** in `t("key", **params)` / `ngettext("key", n)`
  (`from code_puppy.i18n import t, ngettext`). Keys are dotted IDs; catalogs
  live in `code_puppy/i18n/locales/<locale>.json`. A missing key echoes the
  key (never crashes).
- **Interpolate with `{name}`** placeholders — do NOT build strings with
  f-strings/concatenation, and do NOT rely on `str.format` semantics on
  catalog text (attribute/index access and format specs are intentionally
  unsupported; catalogs are untrusted input).
- The single emit choke point (`messaging/message_queue.py::emit_message`)
  resolves `i18n.lazy(...)` values; plain strings pass through unchanged.
- **Model-facing system prompts are OUT of scope** — translating them changes
  LLM behavior. Don't run them through the i18n seam.
- Add extraction behind the pseudolocale/coverage CI gate
  (`tests/i18n/test_i18n_coverage.py`): every translated key must exist in the
  `en-US` source, and a pseudolocale run must emit only bracketed text.

## Rules

1. **Plugins over core** — if a hook exists for it, use it
2. **One `register_callbacks.py` per plugin** — register at module scope
3. **600-line hard cap** — split into submodules
4. **Fail gracefully** — never crash the app
5. **Return `None` from commands you don't own**
6. **Always run linters - `ruff check --fix`, `ruff format .`
7. **NEVER ALLOW A CLAUDE CO-AUTHOR COMMIT**

