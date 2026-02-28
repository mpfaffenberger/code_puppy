# Contributing to Code Puppy

> **The golden rule:** nearly all new functionality should live in a **plugin**
> under `code_puppy/plugins/` and hook into core via the lifecycle callbacks in
> `code_puppy/callbacks.py`. If you find yourself editing files inside
> `code_puppy/command_line/` or touching the core agent loop, stop and ask
> yourself whether a plugin hook already exists for what you need.

---

## Table of Contents

1. [Architecture at a Glance](#architecture-at-a-glance)
2. [Plugin Anatomy](#plugin-anatomy)
3. [Lifecycle Hooks Reference](#lifecycle-hooks-reference)
   - [startup](#startup)
   - [shutdown](#shutdown)
   - [invoke_agent](#invoke_agent)
   - [agent_exception](#agent_exception)
   - [agent_run_start](#agent_run_start)
   - [agent_run_end](#agent_run_end)
   - [version_check](#version_check)
   - [load_model_config](#load_model_config)
   - [load_models_config](#load_models_config)
   - [load_prompt](#load_prompt)
   - [agent_reload](#agent_reload)
   - [edit_file](#edit_file)
   - [delete_file](#delete_file)
   - [run_shell_command](#run_shell_command)
   - [file_permission](#file_permission)
   - [pre_tool_call](#pre_tool_call)
   - [post_tool_call](#post_tool_call)
   - [stream_event](#stream_event)
   - [custom_command](#custom_command)
   - [custom_command_help](#custom_command_help)
   - [register_tools](#register_tools)
   - [register_agents](#register_agents)
   - [register_model_type](#register_model_type)
   - [register_model_providers](#register_model_providers)
   - [get_model_system_prompt](#get_model_system_prompt)
   - [register_mcp_catalog_servers](#register_mcp_catalog_servers)
   - [register_browser_types](#register_browser_types)
   - [get_motd](#get_motd)
   - [message_history_processor_start](#message_history_processor_start)
   - [message_history_processor_end](#message_history_processor_end)
4. [User Plugins](#user-plugins)
5. [Testing Your Plugin](#testing-your-plugin)
6. [Style Guide & Principles](#style-guide--principles)

---

## Architecture at a Glance

```
code_puppy/
├── callbacks.py               ← lifecycle hook registry (THE contract)
├── plugins/
│   ├── __init__.py            ← plugin loader (builtin + user)
│   ├── scheduler/             ← example: TUI + slash commands
│   ├── shell_safety/          ← example: intercepts shell commands
│   ├── agent_skills/          ← example: injects tools + prompt
│   ├── frontend_emitter/      ← example: websocket event bridge
│   ├── file_permission_handler/
│   ├── antigravity_oauth/
│   ├── chatgpt_oauth/
│   ├── claude_code_oauth/
│   ├── customizable_commands/
│   ├── universal_constructor/
│   └── example_custom_command/
├── command_line/              ← core UI (keep your hands off)
└── ...
```

The plugin loader (`code_puppy/plugins/__init__.py`) auto-discovers every
subdirectory that contains a `register_callbacks.py` file and imports it.
Callbacks are registered at import time — no configuration files, no entry
points, no magic.

---

## Plugin Anatomy

Every plugin is a directory under `code_puppy/plugins/` (builtin) or
`~/.code_puppy/plugins/` (user). The only required file is
**`register_callbacks.py`**.

```
code_puppy/plugins/my_feature/
├── __init__.py               # Can be empty
├── register_callbacks.py     # REQUIRED — hooks into lifecycle
├── some_module.py            # Your logic (keep files < 600 lines)
└── tests/                    # (optional, or put in top-level tests/)
```

Minimal skeleton:

```python
# code_puppy/plugins/my_feature/register_callbacks.py

from code_puppy.callbacks import register_callback

def _on_startup():
    print("my_feature loaded!")

register_callback("startup", _on_startup)
```

That's it. Restart Code Puppy and your plugin is live.

---

## Lifecycle Hooks Reference

Every hook is registered the same way:

```python
from code_puppy.callbacks import register_callback

register_callback("<phase_name>", my_callback_function)
```

Callbacks are deduplicated — registering the same function twice for the same
phase is a safe no-op. Hooks are triggered either **synchronously**
(`_trigger_callbacks_sync`) or **asynchronously** (`_trigger_callbacks`).
Async hooks accept both sync and async callback functions; the dispatcher
`await`s coroutines transparently.

> **Async vs Sync:** hooks that fire inside the agent event loop
> (`pre_tool_call`, `post_tool_call`, `stream_event`, `agent_run_start`,
> `agent_run_end`, `invoke_agent`, `agent_exception`, `startup`, `shutdown`,
> `version_check`, `run_shell_command`) are **async**. Everything else is sync.
> You can still register a plain `def` for an async hook — it will be called
> normally. If you register an `async def` for a *sync* hook, it will be run
> via `asyncio.run()` in an isolated context.

---

### `startup`

**When:** Application boot, after the plugin loader runs.  
**Signature:** `() -> None`  
**Async:** Yes  
**Use for:** One-time initialisation, creating directories, loading caches.

```python
from code_puppy.callbacks import register_callback

async def _on_startup():
    """Create workspace directories on first launch."""
    from pathlib import Path
    data_dir = Path.home() / ".my_plugin_data"
    data_dir.mkdir(parents=True, exist_ok=True)

register_callback("startup", _on_startup)
```

*Real-world:* `universal_constructor` uses this to initialise its tool
registry and scan the user tools directory.

---

### `shutdown`

**When:** Application is exiting gracefully.  
**Signature:** `() -> None`  
**Async:** Yes  
**Use for:** Flushing buffers, closing connections, cleanup.

```python
from code_puppy.callbacks import register_callback

_db_conn = None

async def _on_shutdown():
    """Close the analytics database connection."""
    global _db_conn
    if _db_conn:
        _db_conn.close()
        _db_conn = None

register_callback("shutdown", _on_shutdown)
```

---

### `invoke_agent`

**When:** An agent is invoked (sub-agent calls, etc.).  
**Signature:** `(*args, **kwargs) -> None`  
**Async:** Yes  
**Use for:** Logging, analytics, auditing agent invocations.

```python
from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

async def _on_invoke_agent(*args, **kwargs):
    """Log every agent invocation for audit trail."""
    agent_name = kwargs.get("agent_name") or (args[0] if args else "unknown")
    logger.info("Agent invoked: %s", agent_name)

register_callback("invoke_agent", _on_invoke_agent)
```

*Real-world:* `frontend_emitter` uses this to push `agent_invoked` events
over WebSocket to a browser UI.

---

### `agent_exception`

**When:** An agent run throws an unhandled exception.  
**Signature:** `(exception: Exception, *args, **kwargs) -> None`  
**Async:** Yes  
**Use for:** Error reporting, crash telemetry, Sentry integration.

```python
from code_puppy.callbacks import register_callback

async def _on_agent_exception(exception, *args, **kwargs):
    """Report agent crashes to an external error tracker."""
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exception)
    except ImportError:
        pass

register_callback("agent_exception", _on_agent_exception)
```

---

### `agent_run_start`

**When:** At the top of `run_with_mcp`, before the agent task is created.  
**Signature:** `(agent_name: str, model_name: str, session_id: str | None) -> None`  
**Async:** Yes  
**Use for:** Starting background tasks, resource allocation, heartbeats.

```python
from code_puppy.callbacks import register_callback
import time

_run_timers = {}

async def _on_agent_run_start(agent_name, model_name, session_id=None):
    """Start a wall-clock timer for the run."""
    key = session_id or "default"
    _run_timers[key] = time.monotonic()

register_callback("agent_run_start", _on_agent_run_start)
```

*Real-world:* `claude_code_oauth` starts a token-refresh heartbeat here so
long-running agent sessions don't expire mid-flight.

---

### `agent_run_end`

**When:** At the end of `run_with_mcp` (in `finally` — always fires).  
**Signature:**
```python
(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None
```
**Async:** Yes  
**Use for:** Stopping heartbeats, logging duration, workflow orchestration.

```python
from code_puppy.callbacks import register_callback
import time, logging

logger = logging.getLogger(__name__)

async def _on_agent_run_end(
    agent_name, model_name, session_id=None,
    success=True, error=None, response_text=None, metadata=None,
):
    """Log run duration and success/failure."""
    key = session_id or "default"
    start = _run_timers.pop(key, None)
    if start:
        elapsed = time.monotonic() - start
        status = "✓" if success else "✗"
        logger.info("%s %s finished in %.1fs [%s]", status, agent_name, elapsed, model_name)

register_callback("agent_run_end", _on_agent_run_end)
```

*Real-world:* `claude_code_oauth` stops its token-refresh heartbeat here.

---

### `version_check`

**When:** Periodic or on-demand version check.  
**Signature:** `(*args, **kwargs) -> None`  
**Async:** Yes  
**Use for:** Custom update channels, enterprise version pinning.

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info

async def _on_version_check(*args, **kwargs):
    """Notify if an internal fork has updates."""
    # Check your private registry
    latest = await fetch_internal_latest_version()
    if latest and latest != __version__:
        emit_info(f"Internal update available: {latest}")

register_callback("version_check", _on_version_check)
```

---

### `load_model_config`

**When:** A single model's configuration is loaded.  
**Signature:** `(*args, **kwargs) -> Any`  
**Async:** No (sync)  
**Use for:** Patching individual model configs at load time.

```python
from code_puppy.callbacks import register_callback

def _patch_model_config(*args, **kwargs):
    """Force all models to use a corporate proxy."""
    config = args[0] if args else kwargs.get("config", {})
    if isinstance(config, dict) and "custom_endpoint" in config:
        endpoint = config["custom_endpoint"]
        if isinstance(endpoint, dict) and "url" not in endpoint:
            endpoint["url"] = "https://llm-proxy.corp.internal/v1"
    return config

register_callback("load_model_config", _patch_model_config)
```

---

### `load_models_config`

**When:** The full model catalogue is loaded (merged with `models.json`).  
**Signature:** `() -> dict`  
**Async:** No (sync)  
**Use for:** Injecting additional model definitions from an external source.

```python
from code_puppy.callbacks import register_callback

def _load_extra_models():
    """Add models from an internal model registry."""
    return {
        "internal-llama-70b": {
            "name": "llama-70b",
            "context_length": 131072,
            "custom_endpoint": {
                "url": "https://llm.corp.internal/v1",
                "api_key_env": "INTERNAL_LLM_KEY",
            },
        }
    }

register_callback("load_models_config", _load_extra_models)
```

*Real-world:* The OAuth plugins (`antigravity_oauth`, `chatgpt_oauth`,
`claude_code_oauth`) all inject their authenticated models this way.

---

### `load_prompt`

**When:** The system prompt is being assembled.  
**Signature:** `() -> str | None`  
**Async:** No (sync)  
**Use for:** Appending extra instructions, injecting context.

```python
from code_puppy.callbacks import register_callback

def _inject_project_rules():
    """Append project-specific coding rules to every prompt."""
    from pathlib import Path
    rules_file = Path(".puppy-rules.md")
    if rules_file.exists():
        return rules_file.read_text()
    return None

register_callback("load_prompt", _inject_project_rules)
```

---

### `agent_reload`

**When:** The current agent is being reloaded (e.g. after model switch).  
**Signature:** `(*args, **kwargs) -> None`  
**Async:** No (sync)  
**Use for:** Clearing caches, re-initialising state that depends on the model.

```python
from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

def _on_agent_reload(*args, **kwargs):
    """Flush prompt cache when agent reloads."""
    _prompt_cache.clear()
    logger.debug("Prompt cache cleared on agent reload")

register_callback("agent_reload", _on_agent_reload)
```

---

### `edit_file`

**When:** A file edit operation is about to be performed.  
**Signature:** `(*args, **kwargs) -> Any`  
**Async:** No (sync)  
**Use for:** Logging edits, enforcing policies, triggering side-effects.

```python
from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

def _on_edit_file(*args, **kwargs):
    """Log every file edit for an audit trail."""
    file_path = args[0] if args else kwargs.get("file_path", "unknown")
    logger.info("File edited: %s", file_path)

register_callback("edit_file", _on_edit_file)
```

---

### `delete_file`

**When:** A file deletion is about to be performed.  
**Signature:** `(*args, **kwargs) -> Any`  
**Async:** No (sync)  
**Use for:** Blocking deletions of protected files, audit logging.

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error

def _on_delete_file(*args, **kwargs):
    """Prevent deletion of lock files."""
    file_path = str(args[0]) if args else kwargs.get("file_path", "")
    if file_path.endswith(".lock"):
        emit_error(f"Blocked deletion of lock file: {file_path}")
        return {"blocked": True}
    return None

register_callback("delete_file", _on_delete_file)
```

---

### `run_shell_command`

**When:** Before a shell command is executed.  
**Signature:** `(context: Any, command: str, cwd: str | None, timeout: int) -> dict | None`  
**Async:** Yes  
**Use for:** Safety checks, command rewriting, blocking dangerous commands.

Return `None` to allow the command. Return a dict with `{"blocked": True, ...}`
to prevent execution.

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error

async def _check_shell_command(context, command, cwd=None, timeout=60):
    """Block any command that tries to push to main."""
    if "git push" in command and "main" in command:
        emit_error("🛑 Blocked: direct push to main is not allowed")
        return {"blocked": True, "error_message": "Push to main blocked by policy"}
    return None

register_callback("run_shell_command", _check_shell_command)
```

*Real-world:* `shell_safety` uses an LLM-based risk assessment agent to
block high-risk commands when yolo mode is enabled.

---

### `file_permission`

**When:** Before a file operation, to ask the user for permission.  
**Signature:**
```python
(
    context: Any,
    file_path: str,
    operation: str,
    preview: str | None = None,
    message_group: str | None = None,
    operation_data: Any = None,
) -> bool
```
**Async:** No (sync)  
**Use for:** Interactive approval prompts, diff previews, auto-approve rules.

Return `True` to grant permission, `False` to deny.

```python
from code_puppy.callbacks import register_callback

def _auto_approve_test_files(context, file_path, operation, preview=None,
                              message_group=None, operation_data=None):
    """Auto-approve edits to test files."""
    if "/tests/" in file_path or file_path.startswith("tests/"):
        return True  # Always allow test file edits
    return None  # Fall through to default handler

register_callback("file_permission", _auto_approve_test_files)
```

*Real-world:* `file_permission_handler` renders rich diffs and prompts the
user for confirmation with keybindings.

---

### `pre_tool_call`

**When:** Immediately before any tool is executed by the agent.  
**Signature:** `(tool_name: str, tool_args: dict, context: Any = None) -> Any`  
**Async:** Yes  
**Use for:** Logging, argument validation, metrics, modifying args.

```python
from code_puppy.callbacks import register_callback
import time, logging

logger = logging.getLogger(__name__)
_tool_starts = {}

async def _on_pre_tool_call(tool_name, tool_args, context=None):
    """Record tool call start time for performance monitoring."""
    call_id = id(tool_args)  # unique per invocation
    _tool_starts[call_id] = time.monotonic()
    logger.debug("Tool starting: %s", tool_name)

register_callback("pre_tool_call", _on_pre_tool_call)
```

*Real-world:* `frontend_emitter` pushes `tool_call_start` events to the
browser over WebSocket.

---

### `post_tool_call`

**When:** Immediately after a tool finishes executing.  
**Signature:**
```python
(
    tool_name: str,
    tool_args: dict,
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> Any
```
**Async:** Yes  
**Use for:** Metrics collection, result logging, post-processing.

```python
from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

async def _on_post_tool_call(tool_name, tool_args, result, duration_ms, context=None):
    """Log slow tool calls."""
    if duration_ms > 5000:
        logger.warning("Slow tool: %s took %.1fs", tool_name, duration_ms / 1000)

register_callback("post_tool_call", _on_post_tool_call)
```

*Real-world:* `frontend_emitter` pushes `tool_call_complete` events with
sanitised args, duration, and success status.

---

### `stream_event`

**When:** During agent response streaming (tokens generated, tool calls, etc.).  
**Signature:** `(event_type: str, event_data: Any, agent_session_id: str | None) -> None`  
**Async:** Yes  
**Use for:** Real-time UIs, progress indicators, streaming to external systems.

```python
from code_puppy.callbacks import register_callback

async def _on_stream_event(event_type, event_data, agent_session_id=None):
    """Forward token stream to a WebSocket for a live preview."""
    if event_type == "text_delta":
        await websocket_broadcast({
            "type": "token",
            "text": event_data,
            "session": agent_session_id,
        })

register_callback("stream_event", _on_stream_event)
```

*Real-world:* `frontend_emitter` bridges all stream events to subscribed
WebSocket clients.

---

### `custom_command`

**When:** A user types a `/slash` command that isn't a built-in.  
**Signature:** `(command: str, name: str) -> True | str | None`  
**Async:** No (sync)  
**Use for:** Adding new slash commands from plugins.

Return values:
- `None` — not handled, try next plugin
- `True` — handled, no model invocation
- `str` — handled, string sent to model as user input

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_success

def _handle_custom_command(command, name):
    """Handle /ping command."""
    if name != "ping":
        return None
    emit_success("🏓 Pong!")
    return True

register_callback("custom_command", _handle_custom_command)
```

*Real-world:* `scheduler` registers `/scheduler`, `/sched`, and `/cron`
through this hook. All three OAuth plugins register their auth/status/logout
commands the same way.

---

### `custom_command_help`

**When:** The `/help` menu is being built.  
**Signature:** `() -> list[tuple[str, str]]`  
**Async:** No (sync)  
**Use for:** Advertising your plugin's slash commands in `/help`.

Return a list of `(command_name, description)` tuples.

```python
from code_puppy.callbacks import register_callback

def _custom_help():
    return [
        ("ping", "Check if Code Puppy is alive"),
        ("stats", "Show session statistics"),
    ]

register_callback("custom_command_help", _custom_help)
```

---

### `register_tools`

**When:** The agent is being constructed and tool registration is collected.  
**Signature:** `() -> list[dict]`  
**Async:** No (sync)  
**Use for:** Adding new tools the LLM can call.

Each dict must have `"name"` (str) and `"register_func"` (callable that takes
an agent instance).

```python
from code_puppy.callbacks import register_callback

def _register_my_tool(agent):
    """Register a custom tool on the agent."""
    @agent.tool_plain
    async def query_database(sql: str) -> str:
        """Run a read-only SQL query against the project database."""
        # ... implementation ...
        return result

def _register_tools():
    return [{"name": "query_database", "register_func": _register_my_tool}]

register_callback("register_tools", _register_tools)
```

*Real-world:* `agent_skills` registers `activate_skill` and
`list_or_search_skills` tools this way.

---

### `register_agents`

**When:** The agent catalogue is being built.  
**Signature:** `() -> list[dict]`  
**Async:** No (sync)  
**Use for:** Registering entirely new agents (Python classes or JSON defs).

```python
from code_puppy.callbacks import register_callback

def _register_agents():
    from my_plugin.code_review_agent import CodeReviewAgent
    return [
        {"name": "code-reviewer", "class": CodeReviewAgent},
        {"name": "sql-helper", "json_path": "/path/to/sql_agent.json"},
    ]

register_callback("register_agents", _register_agents)
```

---

### `register_model_type`

**When:** Model factory is resolving a model config with a custom `type` field.  
**Signature:** `() -> list[dict]`  
**Async:** No (sync)  
**Use for:** Teaching Code Puppy how to instantiate a new kind of model.

Each dict has `"type"` (str) and `"handler"` (callable receiving
`model_name, model_config, config`).

```python
from code_puppy.callbacks import register_callback

def _create_ollama_model(model_name, model_config, config):
    """Create an Ollama model instance."""
    from pydantic_ai.models.openai import OpenAIModel
    return OpenAIModel(
        model_name=model_config["name"],
        base_url=model_config.get("base_url", "http://localhost:11434/v1"),
        api_key="ollama",  # Ollama doesn't need a real key
    )

def _register_model_types():
    return [{"type": "ollama", "handler": _create_ollama_model}]

register_callback("register_model_type", _register_model_types)
```

*Real-world:* `antigravity_oauth` registers the `"antigravity"` type and
`claude_code_oauth` registers the `"claude_code"` type.

---

### `register_model_providers`

**When:** Model providers are being collected during model factory init.  
**Signature:** `() -> dict[str, type]`  
**Async:** No (sync)  
**Use for:** Registering an entirely new model provider class.

```python
from code_puppy.callbacks import register_callback

def _register_providers():
    """Register a custom Groq provider."""
    from my_plugin.groq_model import GroqModel
    return {"groq": GroqModel}

register_callback("register_model_providers", _register_providers)
```

---

### `get_model_system_prompt`

**When:** The system prompt is being resolved for a specific model.  
**Signature:** `(model_name: str, default_system_prompt: str, user_prompt: str) -> dict | None`  
**Async:** No (sync)  
**Use for:** Overriding or augmenting the system prompt per model.

Return a dict with `"instructions"`, `"user_prompt"`, and `"handled"` keys,
or `None` to pass through.

```python
from code_puppy.callbacks import register_callback

def _custom_system_prompt(model_name, default_system_prompt, user_prompt):
    """Inject safety guidelines for production models."""
    if not model_name.startswith("prod-"):
        return None  # Not our model
    return {
        "instructions": f"{default_system_prompt}\n\nSAFETY: Never suggest deleting production data.",
        "user_prompt": user_prompt,
        "handled": False,  # Let other handlers also process
    }

register_callback("get_model_system_prompt", _custom_system_prompt)
```

*Real-world:* `agent_skills` uses this to inject the available-skills XML
section into every system prompt.

---

### `register_mcp_catalog_servers`

**When:** The MCP server catalogue/marketplace is being built.  
**Signature:** `() -> list[MCPServerTemplate]`  
**Async:** No (sync)  
**Use for:** Adding custom MCP servers to the install catalogue.

```python
from code_puppy.callbacks import register_callback

def _register_mcp_servers():
    """Add our internal MCP servers to the catalogue."""
    from code_puppy.command_line.mcp.base import MCPServerTemplate
    return [
        MCPServerTemplate(
            name="internal-jira",
            description="Query JIRA issues via MCP",
            command="npx",
            args=["-y", "@corp/mcp-jira"],
            env={"JIRA_URL": "https://jira.corp.internal"},
        ),
    ]

register_callback("register_mcp_catalog_servers", _register_mcp_servers)
```

---

### `register_browser_types`

**When:** Browser manager is collecting available browser providers.  
**Signature:** `() -> dict[str, callable]`  
**Async:** No (sync)  
**Use for:** Adding custom browser backends (stealth, headless, etc.).

Each value is an async init function: `async (manager, **kwargs) -> None`.

```python
from code_puppy.callbacks import register_callback

async def _init_camoufox(manager, **kwargs):
    """Launch a Camoufox stealth browser."""
    from camoufox.async_api import AsyncCamoufox
    cm = AsyncCamoufox(headless=True)
    browser = await cm.__aenter__()
    manager._browser = browser
    manager._context = await browser.new_context()
    manager._page = await manager._context.new_page()

def _register_browser_types():
    return {"camoufox": _init_camoufox}

register_callback("register_browser_types", _register_browser_types)
```

---

### `get_motd`

**When:** The message-of-the-day banner is being rendered.  
**Signature:** `() -> tuple[str, str] | None`  
**Async:** No (sync)  
**Use for:** Custom banners, team announcements, tip of the day.

Return `(message, version_string)` or `None`.

```python
from code_puppy.callbacks import register_callback
import random

_TIPS = [
    "💡 Tip: Use /set yolo_mode true to skip confirmations",
    "💡 Tip: Use /agent to switch between agents",
    "💡 Tip: Use /mcp install to add MCP servers",
]

def _get_motd():
    return (random.choice(_TIPS), "")

register_callback("get_motd", _get_motd)
```

---

### `message_history_processor_start`

**When:** At the start of `message_history_accumulator`, before dedup.  
**Signature:**
```python
(
    agent_name: str,
    session_id: str | None,
    message_history: list,
    incoming_messages: list,
) -> None
```
**Async:** No (sync)  
**Use for:** Observing raw incoming messages, analytics, debugging.

```python
from code_puppy.callbacks import register_callback
import logging

logger = logging.getLogger(__name__)

def _on_history_start(agent_name, session_id, message_history, incoming_messages):
    """Log message history growth for context-window analytics."""
    logger.debug(
        "[%s] History: %d existing, %d incoming",
        agent_name, len(message_history), len(incoming_messages),
    )

register_callback("message_history_processor_start", _on_history_start)
```

---

### `message_history_processor_end`

**When:** After dedup and filtering in `message_history_accumulator`.  
**Signature:**
```python
(
    agent_name: str,
    session_id: str | None,
    message_history: list,
    messages_added: int,
    messages_filtered: int,
) -> None
```
**Async:** No (sync)  
**Use for:** Dedup analytics, context-window monitoring, alerting.

```python
from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_warning

def _on_history_end(agent_name, session_id, message_history, messages_added, messages_filtered):
    """Warn when context is getting large."""
    total = len(message_history)
    if total > 200:
        emit_warning(f"⚠️ Context growing large ({total} messages). Consider /clear.")

register_callback("message_history_processor_end", _on_history_end)
```

---

## User Plugins

Users can install plugins without modifying the Code Puppy source.
Drop a plugin directory into `~/.code_puppy/plugins/`:

```
~/.code_puppy/plugins/
└── my_company_tools/
    ├── __init__.py
    └── register_callbacks.py
```

User plugins are loaded **after** builtin plugins and follow the exact same
API. They can register callbacks for any phase.

---

## Testing Your Plugin

Plugins should be tested like any other Python module. The callback system
is fully importable and testable in isolation:

```python
# tests/plugins/test_my_feature.py

def test_my_command_handler():
    from code_puppy.plugins.my_feature.register_callbacks import _handle_custom_command

    assert _handle_custom_command("/ping", "ping") is True
    assert _handle_custom_command("/unknown", "unknown") is None


def test_my_help():
    from code_puppy.plugins.my_feature.register_callbacks import _custom_help

    entries = _custom_help()
    names = [name for name, _ in entries]
    assert "ping" in names
```

For integration tests that need the full callback chain, use
`clear_callbacks()` in your fixtures to avoid pollution:

```python
import pytest
from code_puppy.callbacks import clear_callbacks

@pytest.fixture(autouse=True)
def _clean_callbacks():
    clear_callbacks()
    yield
    clear_callbacks()
```

---

## Style Guide & Principles

1. **Plugins over core.** If a lifecycle hook exists for it, it belongs in
   `plugins/`. Don't touch `command_line/` unless you're adding a new
   *built-in* command that truly belongs in the core product.

2. **Small files.** Hard cap of 600 lines per file. Break large plugins into
   submodules (`register_callbacks.py` + `my_logic.py` + `models.py`, etc.).

3. **DRY / YAGNI / SOLID.** Don't build what you don't need. Don't repeat
   what's already in `code_puppy.messaging`, `code_puppy.config`, etc.

4. **Zen of Python.** Explicit is better than implicit. Simple is better
   than complex. If the implementation is hard to explain, it's a bad idea.

5. **One `register_callbacks.py` per plugin.** This is the only file the
   loader looks for. Put logic in sibling modules and import them from here.

6. **Register at module scope.** Call `register_callback()` at the bottom
   of `register_callbacks.py` (not inside a function that might not be
   called). The loader imports the module; registration happens on import.

7. **Fail gracefully.** Wrap risky operations in `try/except`. A broken
   plugin should never crash the entire application.

8. **No circular imports.** Use lazy imports inside callback functions when
   you need something from core that might import plugins.

9. **Return `None` from commands you don't own.** Custom command handlers
   are called in sequence. Return `None` to let the next plugin try.

10. **Test in isolation.** Your callback functions should be directly
    importable and testable without starting the full application.
