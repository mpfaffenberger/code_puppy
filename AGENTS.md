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
| `run_shell_command` | Before shell exec | `(context, command, cwd=None, timeout=60) -> dict \| None` (return `{"blocked": True}` to block) |
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
| `load_model_config` | Patch model config | `(*args, **kwargs) -> Any` |
| `load_models_config` | Inject models | `() -> dict` |
| `load_model_descriptions` | Inject description overlays | `() -> dict[str, str]` |
| `get_model_system_prompt` | Per-model prompt | `(model_name, default_prompt, user_prompt) -> dict \| None` |
| `stream_event` | Response streaming | `(event_type, event_data, agent_session_id=None) -> None` |
| `pre_mcp_autostart` | Before bound MCP servers auto-start | `(agent_name, server_names) -> None` (refresh tokens / mint creds here) |

Full list + rarely-used hooks: see `code_puppy/callbacks.py` source.

## Rules

1. **Plugins over core** — if a hook exists for it, use it
2. **One `register_callbacks.py` per plugin** — register at module scope
3. **600-line hard cap** — split into submodules
4. **Fail gracefully** — never crash the app
5. **Return `None` from commands you don't own**
6. **Always run linters - `ruff check --fix`, `ruff format .`
7. **NEVER ALLOW A CLAUDE CO-AUTHOR COMMIT**

