# Agent & Tool System

> Part of the `code-puppy-agent` skill. Read this when you need to
> understand how agents are structured/discovered, or how tools get
> registered and wired to an agent. See `SKILL.md` for the overview and
> the full reference map.

---

## Agent System

### BaseAgent (`agents/base_agent.py`)

All agents inherit from `BaseAgent` (ABC). Key interface:

| Member | Purpose |
|--------|---------|
| `name` (abstract property) | Stable machine identifier, e.g. `"code-puppy"` |
| `display_name` (abstract property) | Human name with emoji |
| `description` (abstract property) | One-line summary |
| `get_system_prompt()` (abstract) | The authored system prompt (identity is appended separately at runtime) |
| `get_available_tools()` (abstract) | List of tool-name strings from `TOOL_REGISTRY` |
| `get_model_name()` | Effective model: runtime override > pinned > global |
| `get_full_system_prompt()` | Authored prompt + `load_prompt` plugin fragments + identity ID |

`BaseAgent` is a **thin conductor**. Real logic lives in sibling modules:
- `_builder.py` — builds the pydantic-ai `Agent`, wires MCP toolsets
- `_runtime.py` — `run_with_mcp()` orchestration, cancellation, retries
- `_history.py` — token estimation, hashing, orphan pruning
- `_compaction.py` — summarization/truncation when context overflows

### Agent Types

**Python agents** — classes in `agents/` discovered automatically by
`agent_manager._discover_agents()` via `pkgutil.iter_modules`. Any
`BaseAgent` subclass (excluding `JSONAgent` itself) in a non-underscore
module gets registered.

**JSON agents** — `JSONAgent` loads from `~/.code_puppy/agents/*.json`
(user) and `<CWD>/.code_puppy/agents/*.json` (project). Project overrides
user on name collision. Required fields: `name`, `description`,
`system_prompt`, `tools`. Optional: `display_name`, `user_prompt`,
`tools_config`, `model`, `mcp_servers`.

**Plugin agents** — registered via the `register_agents` callback, which
returns `[{"name": "...", "class": SomeAgentClass}]` (or
`{"name": ..., "json_path": ".../agent.json"}`).

**Discovery & precedence** — `_discover_agents()` runs three phases:

1. Builtin Python classes (`pkgutil` scan of `agents/`).
2. JSON agents via `discover_json_agents()`: the **user** dir is scanned
   first, then the **project** dir overwrites it on collision, so **project
   wins over user**. Both are skipped if a builtin Python agent already owns
   the name (builtin beats JSON).
3. Plugin-registered agents via `on_register_agents()` — these overwrite
   `_AGENT_REGISTRY` **unconditionally**, so a plugin agent can shadow a
   builtin. Register under a unique name.

Net precedence: **builtin Python > JSON project > JSON user**; plugin
agents are last-writer-wins (handled after the others, no collision guard).

### Agent Manager (`agents/agent_manager.py`)

- `get_current_agent()` — returns the active `BaseAgent` instance
- `set_current_agent(name)` — switches agent, preserves history
- `get_available_agents()` — dict of `name → display_name`
- `clone_agent()` — creates a copy of the current agent

Agent selection persists per **terminal session** (keyed by PPID) in
`terminal_sessions.json` so different terminals can run different agents.

---

## Tool System

### TOOL_REGISTRY (`tools/__init__.py`)

A flat dict mapping tool-name strings to registration functions:

```python
TOOL_REGISTRY = {
    "read_file": register_read_file,
    "create_file": register_create_file,
    "replace_in_file": register_replace_in_file,
    # ... 60+ tools
}
```

Each `register_*` function takes a pydantic-ai `agent` and calls
`@agent.tool` to wire the tool's JSON schema.

### How tools are assigned

`register_tools_for_agent(agent, tool_names, agent_name=...)` is called
during agent build. It:

1. Loads plugin-registered tools via `on_register_tools()` → merges into `TOOL_REGISTRY`
2. Merges plugin-advertised tools via `on_register_agent_tools(agent_name)` → unions into the requested list
3. Expands compound tools (e.g. `"edit_file"` → `["create_file", "replace_in_file", "delete_snippet"]`)
4. Registers each tool by calling its `register_func(agent)`

### Built-in tool categories

| Category | Tools |
|----------|-------|
| **File ops** | `list_files`, `read_file`, `grep` |
| **File mods** | `create_file`, `replace_in_file`, `delete_snippet`, `delete_file` |
| **Shell** | `agent_run_shell_command`, `agent_share_your_reasoning` |
| **Sub-agents** | `list_agents`, `invoke_agent`, `invoke_agent_with_model` |
| **Skills** | `activate_skill`, `list_or_search_skills` |
| **User** | `ask_user_question`, `load_image_for_analysis` |
| **Browser** | 30+ `browser_*` tools (Playwright-backed) |
| **Models** | `list_available_models` |
| **UC** | `universal_constructor` (dynamic tool factory) |

### Plugin tools: two hooks, both required

```python
# 1. Define the tool (adds to TOOL_REGISTRY)
def _register_tools():
    return [{"name": "my_tool", "register_func": register_my_tool}]
register_callback("register_tools", _register_tools)

# 2. Advertise it to agents (adds to agent's tool list)
def _advertise(agent_name=None):
    return ["my_tool"]
register_callback("register_agent_tools", _advertise)
```

Step 1 makes the tool *exist*; step 2 makes agents *see* it. Both are
needed. `namespace_skill_search` (`code_puppy/plugins/namespace_skill_search/`)
is a small, complete example of this pattern for a single tool
(`browse_skill_namespace`) — see `SKILLS_SYSTEM.md` for what it does and
`PLUGINS_AND_CALLBACKS.md` for the callback-safety reasoning behind how
it's wired.

### Async tool functions and blocking I/O

Tool functions taking a `RunContext` (`activate_skill`,
`list_or_search_skills`, `browse_skill_namespace`) are conventionally
`async def` in this codebase. That matters for one non-obvious reason:
pydantic-ai only auto-offloads **synchronous** tool functions to a worker
thread (via `anyio.to_thread`); an `async def` tool runs directly on the
event loop. If your async tool does blocking filesystem/network I/O
(e.g. scanning a large directory tree), wrap the blocking call
explicitly:

```python
result = await asyncio.to_thread(blocking_function, *args)
```

`namespace_skill_search/search_tool.py` does exactly this around its
`build_namespaces()` call — a good reference implementation if you're
writing a new async tool with real I/O in it.
