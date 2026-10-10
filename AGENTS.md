# Contributing to Code Puppy

> **Golden rule:** nearly all new functionality should be a **plugin** in the
> `code_puppy_core_plugins` repository that hooks into core via
> `code_puppy/callbacks.py`. Don't edit `code_puppy/command_line/`.

## Rules

1. **Plugins over core** — if a hook exists for it, use it
2. **One `register_callbacks.py` per plugin** — register at module scope
3. **600-line hard cap** — split into submodules
4. **Fail gracefully** — never crash the app
5. **Return `None` from commands you don't own**
6. **Always run linters** — `ruff check --fix`, `ruff format .`
7. **NEVER ALLOW A CLAUDE CO-AUTHOR COMMIT**
8. **Keep this file under 10,000 characters** — Code Puppy drops everything
   past that. Put reference material in `docs/`; `tests/test_agents_md_size.py`
   enforces the cap.

## How Plugins Work

Plugins are discovered from three tiers, loaded in order:

| Tier | Location | When to use |
|------|----------|-------------|
| **Builtin** | `code_puppy_core_plugins/<name>/register_callbacks.py` | Official package discovered via Python entry points |
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

`<CWD>/.code_puppy/plugins/<name>/register_callbacks.py`, mirroring project
agents (`.code_puppy/agents/`) and skills (`.code_puppy/skills/`).

- **Opt-in directory.** Code Puppy never auto-creates `.code_puppy/plugins/`.
- **Untrusted by default.** Project plugins run repo code at import, so none
  load until accepted in the `/plugins` TUI (select → Enter → type `trust`);
  they then hot-load. Trust is a SHA-256 of the plugin dir, scoped to the
  project path in `~/.code_puppy/trusted_plugins.json`; any file change
  revokes it and everything else fails closed. `/plugins revoke <name>`
  removes trust. Security model: `code_puppy/plugins/trust.py`.
- **Keep runtime state out of the plugin dir** — it changes the hash. Use
  `~/.code_puppy/` or a dot-path (e.g. `.state/`), which hashing skips.
- **Load order is builtin → user → project**, so project plugins win
  override-style hooks. On a name clash the project copy replaces the user
  plugin (as with agents); shadowing a builtin logs a warning.
- **Namespaced imports:** `project_plugins.<name>.register_callbacks` in
  `sys.modules`, so they never collide with user plugins.

## Available Hooks

`register_callback("<hook>", func)` — deduplicated, async hooks accept sync or async functions.

`register_callback("<hook>", func, fail_closed=True)` — security guards on `pre_tool_call` /
`run_shell_command` only. A crashed callback normally reports `None`, which those hooks read as
approval; with `fail_closed=True` the crash blocks instead. Defaults to `False`; rejected on
other hooks.

| Hook | When | Signature |
|------|------|-----------|
| `startup` | App boot | `() -> None` |
| `shutdown` | Graceful exit | `() -> None` |
| `invoke_agent` | Sub-agent invoked | `(*args, **kwargs) -> None` |
| `agent_exception` | Unhandled agent error | `(exception, *args, **kwargs) -> None` |
| `error_logged` | After `log_error()` writes to the local log | `(error, *, context=None, include_traceback=True) -> None` — sync observer; must return promptly |
| `agent_run_start` | Before agent task | `(agent_name, model_name, session_id=None) -> None` |
| `model_select` | Select a model for one run | `(*, agent_name, current_model, prompt, messages, session_id=None) -> str \| None` — first non-empty result wins |
| `agent_run_end` | After agent run | `(agent_name, model_name, session_id=None, success=True, error=None, response_text=None, metadata=None) -> None` |
| `load_prompt` | System prompt assembly | `() -> str \| None` |
| `run_shell_command` | Before shell exec | `(context, command, cwd=None, timeout=60) -> dict \| None` (return `{"blocked": True}` to block, `{"rewrite": "<new cmd>"}` to transparently transform) |
| `file_permission` | Before file op | `(context, file_path, operation, ...) -> bool` |
| `pre_tool_call` | Before tool executes | `(tool_name, tool_args, context=None) -> Any` (return `{"blocked": True}` to deny; add `"tool_result": str` when the hook handled the call itself and that text is the tool's result) |
| `post_tool_call` | After tool finishes | `(tool_name, tool_args, result, duration_ms, context=None) -> Any` |
| `custom_command` | Unknown `/slash` cmd | `(command, name) -> True \| str \| None` |
| `custom_command_help` | `/help` menu | `() -> list[tuple[str, str]]` |
| `register_tools` | Tool registration | `() -> list[dict]` with `{"name": str, "register_func": callable}` |
| `register_agent_tools` | Advertise tools to an agent's available list | `(agent_name: str \| None) -> list[str]` — tool names from `TOOL_REGISTRY` to merge into the agent's hardcoded `get_available_tools()` |
| `register_agents` | Agent catalogue | `() -> list[dict]` with `{"name": str, "class": type}` |
| `register_model_type` | Custom model type | `() -> list[dict]` with `{"type": str, "handler": callable}` |
| `register_skills` | Skill catalogue | `() -> list[dict]` with `{"name": str, "skill_md" \| "skill_md_path" \| "frontmatter"+"body"}` |
| `register_settings` | `/set` keys (autocomplete + `/set` menu) | `() -> SettingsCategory \| list[SettingsCategory]` from `code_puppy.command_line.set_menu_schema` — same-named categories merge; core keys win; `sensitive=True` masks the value. Guard with `try/except ValueError` for older cores |
| `register_cli_args` | Before CLI `parse_args()` | `(parser) -> list` — plugins call `parser.add_argument(...)`; namespace flags (e.g. `--myplugin-foo`) to avoid argparse collisions |
| `handle_cli_args` | After CLI `parse_args()` | `(args) -> dict \| None` — return `{"handled": True, "exit_code": int}` to terminate the CLI cleanly; return `None` to let startup proceed |
| `load_model_config` | Patch model config | `(*args, **kwargs) -> Any` |
| `load_models_config` | Inject models | `() -> dict` |
| `load_model_descriptions` | Inject description overlays | `() -> dict[str, str]` |
| `get_model_system_prompt` | Per-model prompt | `(model_name, default_prompt, user_prompt) -> dict \| None` |
| `provider_credential_flow` | `/add_model` hit a missing credential | `(*, provider_id, env_var) -> bool \| None` — save the credential (config + env) and return `True` to skip manual entry; short-circuits on first `True` |
| `stream_event` | Response streaming | `(event_type, event_data, agent_session_id=None) -> None` |
| `transform_model_messages` | Before each model request, after history processing | `(agent_name, messages) -> None` — mutate the final `list[ModelMessage]` in place |
| `pre_mcp_autostart` | Before bound MCP servers auto-start | `(agent_name, server_names) -> None` (refresh tokens / mint creds here) |

Full list + rarely-used hooks: see `code_puppy/callbacks.py` source.

## Speculative Execution

With speculative execution on (`enable_speculative_code_mode`, `Ctrl+X Ctrl+S`),
an all-literal tool call may launch while the model is still writing the
snippet. Tools opt in themselves (core or plugin, no core edit):

```python
@agent.tool(metadata={"speculatable": True})
async def my_lookup(context: RunContext, query: str) -> Result: ...
```

Only a literal `True` counts. Opt in only for side-effect-free reads (an early
launch can run a call the snippet never reaches; unclaimed results are
discarded), and re-check opt-in settings inside the tool body. Resolved at each
run start by `DeclaredSpeculation` in `code_puppy/agents/_code_mode.py`.

## Ctrl+X Chords

`Ctrl+X` is a **chord prefix**, never a standalone hotkey: the next key resolves
against the registry in `code_puppy/messaging/chords.py`. Plugins add chords via
`register_chord(...)`. Chord callbacks run on the key-listener thread, so they
must **never block** and **never raise**; register them only while the binding
is meaningful. Bindings, design notes, and examples: **`docs/CHORDS.md`**.

## Internationalization (i18n)

Full guide: **`docs/I18N.md`**. Rules for new user-facing CLI/TUI output (PUP-473):

- **Wrap display strings** in `t("key", **params)` / `ngettext("key", n)` from
  `code_puppy.i18n`; catalogs live in `code_puppy/i18n/locales/<locale>.json`.
- **Interpolate with `{name}` placeholders** — never f-strings or concatenation.
  Catalogs are untrusted: no `str.format` attribute/index access or format specs.
- **Never translate model-facing system prompts** — it changes LLM behavior.
- New extractions must pass `tests/i18n/test_i18n_audit.py` (keys exist in
  `en-US`; a pseudolocale run emits only bracketed text).
