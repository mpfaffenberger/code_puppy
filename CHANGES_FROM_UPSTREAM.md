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

## Pending upstream PRs

Both fixes are documented and tested. Cherry-pick PRs will be filed against
https://github.com/mpfaffenberger/code_puppy once the hackathon window closes.

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
