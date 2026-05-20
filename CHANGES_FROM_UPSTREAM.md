# Changes from upstream code-puppy

Base: `code-puppy@0.0.472` — https://github.com/mpfaffenberger/code_puppy

## Fix 1: MCP servers auto-enable on startup

**File**: `code_puppy/mcp_/manager.py` — `_initialize_servers()`

**Problem**: `ManagedMCPServer._enabled` is hardcoded to `False` in `__init__`.
`ServerConfig.enabled` (which defaults to `True` for all servers in
`mcp_servers.json`) was read but never applied. Every server required an
explicit `/mcp start <name>` command before tools were available.

**Fix**: After constructing `ManagedMCPServer`, call `managed_server.enable()`
if `config.enabled` is `True`. Set status tracker to `RUNNING` accordingly.

## Fix 2: Local `.code-puppy.json` project config loading

**Files**: `code_puppy/config.py`, `code_puppy/mcp_/manager.py`

**Problem**: code-puppy only loaded MCP server config from the global
`~/.code_puppy/mcp_servers.json`. Project-local config files were ignored,
requiring every new project to manually register servers in the global config.

**Fix**: `load_local_mcp_config()` walks up from CWD to find `.code-puppy.json`.
`MCPManager.sync_from_local_config()` registers those servers after global config
sync (local wins on name collision). Supports both `mcpServers` array format and
`mcp_servers` object format. Expands `${PROJECT_ROOT}`, maps `autoStart`→`enabled`
and `workingDirectory`→`cwd`.

## Fix 3: ask_user_question JSON-string coercion

**File**: `code_puppy/tools/ask_user_question/registration.py`

**Problem**: When the foreman LLM passes the `questions` parameter as a JSON
string `"[{...}]"` (which it does when reading a text content block and
re-serialising it as a tool call argument), pydantic_ai validates the argument
against the `list[dict[str, Any]]` type annotation and rejects it:
`expected list, received str`.

This caused the theme-phase `ask_user_question` call to fail with a validation
error on every retry, looping indefinitely.

**Fix**: Added `BeforeValidator(_coerce_questions_json_string)` to the
`questions` parameter annotation. The validator calls `json.loads()` when the
input is a string, then passes the result to pydantic for normal type
validation. Invalid JSON strings pass through unchanged so pydantic produces a
clear error. The JSON Schema exposed to the LLM is unchanged — pydantic's
`BeforeValidator` is transparent to schema generation.

## Fix 4: Project workspace with `.code-puppy/` directory and `projectOnly` isolation

**Files**: `code_puppy/config.py`, `code_puppy/mcp_/manager.py`,
`code_puppy/agents/json_agent.py`, `code_puppy/agents/agent_manager.py`,
`code_puppy/plugins/__init__.py`

**Problem**: code-puppy had no unified project-local configuration directory.
Project-level config was scattered across:
- `.code-puppy.json` (MCP servers only, walk-up discovery)
- `.code_puppy/agents/` (JSON agents, CWD only, no walk-up)
- No project-local plugin loading at all
- No way to isolate a project from global `~/.code_puppy/` config

This prevented reproducible project-scoped AI agent environments and made
it impossible for scaffolding tools to ship a self-contained agent config
that wouldn't be contaminated by the developer's global settings.

**Fix**: Unified `.code-puppy/` workspace directory with `projectOnly` flag:

```
.code-puppy/
  config.json       # { "projectOnly": true }
  mcp_servers.json  # Project MCP servers
  agents/           # JSON agent definitions
  plugins/          # Project-scoped plugins
```

**`get_project_workspace()`** walks up from CWD to git root looking for
`.code-puppy/` directory. Returns a frozen `ProjectWorkspace` dataclass
with `root_path`, `workspace_path`, `project_only`, and `config` fields.
Result is cached per-process, invalidated on CWD change.

**`projectOnly` mode** (`config.json` → `"projectOnly": true`):
- `MCPManager.sync_from_config()` skips global `mcp_servers.json`
- `discover_json_agents()` skips user-level `~/.code_puppy/agents/`
- `_discover_agents()` skips all builtin Python agents except base `code-puppy`
- `load_plugin_callbacks()` skips user plugins in `~/.code_puppy/plugins/`
- Builtin plugins always load (they are code-puppy internals)

**Default mode** (`projectOnly: false`): additive merge, local wins on collision.
Existing behavior for users without a `.code-puppy/` directory is unchanged.

**Backward compat**: Legacy `.code-puppy.json` files and `.code_puppy/agents/`
directories still work when no `.code-puppy/` workspace is found.

**Naming**: Uses `PROJECT_WORKSPACE_DIR_NAME = ".code-puppy"` constant — single
place to change after upstream naming discussion.

Subsumes Fix 2 (local `.code-puppy.json`) which is now a legacy fallback path.

## Pending upstream PRs

Fixes 1, 3, and 4 are documented and tested. Cherry-pick PRs will be filed
against https://github.com/mpfaffenberger/code_puppy — Fix 4 as an incremental
series (workspace discovery → MCP → agents → plugins).
