---
name: mist-agent
description: Deep reference on Mist's internal architecture — agents, tools, plugins, models, MCP, sessions, and how to extend it correctly.
version: "1.0"
author: mist
tags:
  - mist
  - architecture
  - internals
  - plugins
  - reference
---

# Mist — Architecture & Internals

This skill is a **self-awareness document**. When activated it teaches the
LLM how Mist is structured under the hood so it can navigate the
codebase, debug issues, and extend the product without guessing.

> **Philosophy:** Mist is plugin-first. Nearly all new functionality
> should be a plugin under `code_puppy/plugins/` that hooks into core via
> `code_puppy/callbacks.py`. Don't edit `code_puppy/command_line/` or core
> agent files unless a hook genuinely doesn't exist.

---

## 1. Layered Architecture

```
┌──────────────────────────────────────────────────┐
│  TUI / CLI  (command_line/, tui/)                 │
│    user input → slash commands → agent dispatch   │
├──────────────────────────────────────────────────┤
│  Agent Layer  (agents/)                           │
│    BaseAgent → system prompt, tools, history      │
│    _builder, _runtime, _compaction, _history      │
├──────────────────────────────────────────────────┤
│  Tool Layer  (tools/)                             │
│    TOOL_REGISTRY → register_tools_for_agent()     │
├──────────────────────────────────────────────────┤
│  Plugin Layer  (plugins/, callbacks.py)           │
│    register_callback("hook", fn) at import time   │
├──────────────────────────────────────────────────┤
│  Model Layer  (model_factory.py, config.py)       │
│    ModelFactory → pydantic-ai Model objects       │
├──────────────────────────────────────────────────┤
│  pydantic-ai  (external)                          │
│    Agent.run(), streaming, tool schemas           │
└──────────────────────────────────────────────────┘
```

The TUI collects user input. It delegates to the **agent manager** which
loads the current agent. The agent builds a pydantic-ai `Agent` with a
system prompt + tool set, then `run_with_mcp()` streams the LLM response.
Plugins hook into every stage via callbacks.

---

## 2. Agent System

### 2.1 BaseAgent (`agents/base_agent.py`)

All agents inherit from `BaseAgent` (ABC). Key interface:

| Member | Purpose |
|--------|---------|
| `name` (abstract property) | Stable machine identifier, e.g. `"mist"` |
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

### 2.2 Agent Types

**Python agents** — classes in `agents/` discovered automatically by
`agent_manager._discover_agents()` via `pkgutil.iter_modules`. Any
`BaseAgent` subclass (excluding `JSONAgent` itself) in a non-underscore
module gets registered.

**JSON agents** — `JSONAgent` loads from `~/.mist/agents/*.json`
(user) and `<CWD>/.mist/agents/*.json` (project). Project overrides
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

### 2.3 Agent Manager (`agents/agent_manager.py`)

- `get_current_agent()` — returns the active `BaseAgent` instance
- `set_current_agent(name)` — switches agent, preserves history
- `get_available_agents()` — dict of `name → display_name`
- `clone_agent()` — creates a copy of the current agent

Agent selection persists per **terminal session** (keyed by PPID) in
`terminal_sessions.json` so different terminals can run different agents.

---

## 3. Tool System

### 3.1 TOOL_REGISTRY (`tools/__init__.py`)

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

### 3.2 How tools are assigned

`register_tools_for_agent(agent, tool_names, agent_name=...)` is called
during agent build. It:

1. Loads plugin-registered tools via `on_register_tools()` → merges into `TOOL_REGISTRY`
2. Merges plugin-advertised tools via `on_register_agent_tools(agent_name)` → unions into the requested list
3. Expands compound tools (e.g. `"edit_file"` → `["create_file", "replace_in_file", "delete_snippet"]`)
4. Registers each tool by calling its `register_func(agent)`

### 3.3 Built-in tool categories

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

### 3.4 Plugin tools

Plugins register tools via two complementary hooks:

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
needed.

---

## 4. Plugin & Callback System

### 4.1 Plugin discovery (three tiers)

| Tier | Location | Load order |
|------|----------|------------|
| **Builtin** | `code_puppy/plugins/<name>/register_callbacks.py` | 1st |
| **User** | `~/.mist/plugins/<name>/register_callbacks.py` | 2nd |
| **Project** | `<CWD>/.mist/plugins/<name>/register_callbacks.py` | 3rd (highest precedence) |

Each plugin is a directory containing `register_callbacks.py`. The loader
auto-discovers it. Project plugins shadow user plugins on name collision.

### 4.2 The callback hook system

`register_callback(phase, func)` at module scope. The callback engine
(`callbacks.py`) stores functions per phase and fires them at the right
time. All hooks accept sync or async functions.

**Most important hooks for extending Mist:**

| Hook | When | Return value |
|------|------|-------------|
| `register_tools` | Tool registration | `list[dict]` with `name`, `register_func` |
| `register_agent_tools` | Per-agent tool advertisement | `list[str]` of tool names |
| `register_skills` | Skill catalogue | `list[dict]` with `name` + `skill_md`/`skill_md_path`/`frontmatter`+`body` |
| `register_agents` | Agent catalogue | `list[dict]` with `name`, `class` |
| `load_prompt` | System prompt assembly | `str` fragment or `None` |
| `get_model_system_prompt` | Per-model prompt patch | `dict` with `instructions`/`handled` or `None` |
| `custom_command` | Unknown `/slash` command | `True` (handled), `str` (message), or `None` (not mine) |
| `pre_tool_call` | Before tool executes | Can modify args |
| `post_tool_call` | After tool finishes | Observes result + duration |
| `run_shell_command` | Before shell exec | Return `{"blocked": True}` to block |
| `file_permission` | Before file op | `bool` — allow/deny |
| `agent_run_start` / `agent_run_end` | Agent lifecycle | Observes name, model, session |

The full list is in `callbacks.py` — `PhaseType` has ~45 phases.

### 4.3 Minimal plugin example

```
my_plugin/
  __init__.py          # (can be empty)
  register_callbacks.py
```

```python
from code_puppy.callbacks import register_callback

def _on_load_prompt():
    return "\n## Project Rules\nAlways use type hints."

register_callback("load_prompt", _on_load_prompt)
```

That's it. The loader handles discovery, import, and registration.

---

## 5. Model System

### 5.1 ModelFactory (`model_factory.py`)

Resolves a model-name string into a pydantic-ai `Model` object.
Supports providers: OpenAI, Anthropic, Gemini, Cerebras, OpenRouter,
Azure, and custom OpenAI/Anthropic/Gemini-compatible endpoints.

### 5.2 Model configuration

Models are defined in three places (merged at runtime):

1. **Built-in defaults** — hardcoded in the factory
2. **`~/.mist/extra_models.json`** — user-defined custom models
3. **Plugin injection** — `load_models_config` callback returns a dict

Example `extra_models.json`:
```json
{
  "my-model": {
    "type": "custom_openai",
    "name": "gpt-4o",
    "custom_endpoint": {
      "url": "https://api.example.com/v1",
      "api_key": "$MY_API_KEY"
    },
    "context_length": 128000
  }
}
```

### 5.3 Model types

| Type | Provider |
|------|----------|
| `openai` / `openai_responses` | OpenAI |
| `anthropic` | Anthropic (Claude) |
| `gemini` | Google Gemini |
| `cerebras` | Cerebras (via CerebrasProvider) |
| `custom_openai` | Any OpenAI-compatible endpoint |
| `custom_anthropic` | Anthropic-compatible endpoint |
| `round_robin` | Cycle through N models (rate-limit mitigation) |
| Plugin types | Registered via `register_model_type` callback |

### 5.4 Model selection precedence

For any agent: **runtime override > agent-pinned model > agent's `model`
field (JSON agents) > global model name**.

The global model is set via `/model` and stored in config.

---

## 6. MCP Integration

### 6.1 MCP Manager (`mcp_/manager.py`)

Mist manages external MCP (Model Context Protocol) servers that
provide additional tools to agents. Key components:

- **Registry** (`mcp_/registry.py`) — server definitions (stdio/SSE/streamable-http)
- **Manager** (`mcp_/manager.py`) — lifecycle: start, stop, health checks
- **Agent bindings** (`mcp_/agent_bindings.py`) — which agents get which servers
- **Circuit breaker** (`mcp_/circuit_breaker.py`) — auto-disables flaky servers

### 6.2 How MCP servers attach to agents

Servers can be:
1. **Globally started** — available to all agents
2. **Agent-bound** — declared in a JSON agent's `mcp_servers` field, or
   bound via the `/mcp bind` menu
3. **Auto-started** — bound servers with `auto_start: true` start when the
   agent runs

The `pre_mcp_autostart` hook fires before auto-start, letting plugins
refresh tokens or mint credentials.

### 6.3 Managing MCP servers

Use `/mcp` in the TUI:
- `/mcp list` — show configured servers
- `/mcp start <name>` / `/mcp stop <name>`
- `/mcp status` — health dashboard
- `/mcp bind` — attach servers to agents

---

## 7. Session & History System

### 7.1 Message history

Each `BaseAgent` maintains `_message_history` — a list of pydantic-ai
`ModelMessage` objects (alternating `ModelRequest`/`ModelResponse`).
History is the conversation context sent to the LLM on each turn.

### 7.2 Context window management

When the conversation grows too large:
1. **Token estimation** (`_history.py`) — estimates tokens per message
2. **Compaction** (`_compaction.py`) — summarizes older messages using a
   dedicated summarization agent, preserving recent messages
3. **Protected tokens** — the most recent N tokens are never compacted
   (configurable via `protected_token_count`)

### 7.3 Session persistence

Sessions are saved as pickle files in the state directory:
- `session_storage.py` handles serialization
- `/save <name>` and `/load <name>` commands
- Auto-save on exit

### 7.4 Useful history commands

| Command | Effect |
|---------|--------|
| `/save <name>` | Save current session |
| `/load <name>` | Load a saved session |
| `/pop [N]` | Remove N most recent messages |
| `/truncate <N>` | Keep only N most recent messages |
| `/prune` | Interactive context pruning UI |

---

## 8. Skills System

### 8.1 How skills work

A skill is a directory containing a `SKILL.md` with YAML frontmatter
(`name`, `description`, optional `version`, `author`, `tags`) and
markdown body. The body is the instruction set loaded into context when
the skill is activated.

### 8.2 Skill discovery (`plugins/agent_skills/discovery.py`)

Scans these directories (first-discovered wins on name collision):
1. `~/.mist/skills/`
2. `<CWD>/.mist/skills/`
3. `<CWD>/skills/`
4. Plugin-registered skills (via `register_skills` callback)

### 8.3 Skill activation flow

1. The model calls `activate_skill("skill-name")` or the user types
   `/<skill-name>`
2. The tool reads the full `SKILL.md` from disk
3. Content is injected into the model's context as a tool result
4. The model follows the instructions in its next response

Skills are **opt-in** — the model sees a one-line summary in its system
prompt (name + description) and must explicitly activate to get full
instructions.

### 8.4 Managing skills

| Command | Effect |
|---------|--------|
| `/skills` | Interactive TUI menu |
| `/skills list` | Text list of all skills |
| `/skills enable` / `disable` | Toggle skills globally |
| `/skills frontmatter on/off` | Toggle skill summaries in system prompt |
| `/skills install` | Browse & install from remote catalog |

---

## 9. System Prompt Assembly

Assembled in two stages: `get_full_system_prompt()` builds the base
(`base_agent.py`), then `_assemble_instructions()` (`_builder.py`)
appends rules and runs the per-model patcher.

`get_full_system_prompt()` layers:

```
1. Authored prompt   (agent.get_system_prompt())
2. load_prompt fragments (plugin-injected: kennel memory, permission
   rules, …)
3. Identity ID        (agent name + UUID prefix)
```

`_assemble_instructions()` then appends:

```
4. AGENTS.md puppy_rules  (global ~/.mist/AGENTS.md, then project
   <CWD>/.mist/AGENTS.md, then ./AGENTS.md fallback — concatenated,
   not first-wins)
5. Extended-thinking note  (only if active for the resolved model)
6. Per-model patches       (get_model_system_prompt callbacks, via
   prepare_prompt_for_model) — this is where the **skills block**
   (available-skills summary) is appended, by the agent_skills plugin
```

> The skills summary is **not** a `load_prompt` fragment — it's injected
> through `get_model_system_prompt`, so it lands *after* identity and rules.

Layers 2–6 are **runtime-only** — recomputed every run, never persisted
into static agent definitions. This prevents stale timestamps, dead file
paths, and baked-in session IDs from leaking into cloned agents.

---

## 10. Configuration System (`config.py`)

All settings live in `~/.mist/mist.cfg` (INI format) managed via:
- `get_value(key)` / `set_value(key, value)`
- `/set <key> <value>` slash command

Key directories:
- **Config root**: `~/.mist/`
- **State/sessions**: `~/.mist/state/` (or platform cache dir)
- **Cache**: `~/.mist/cache/`
- **Agents**: `~/.mist/agents/`
- **Skills**: `~/.mist/skills/`
- **Plugins**: `~/.mist/plugins/`
- **Extra models**: `~/.mist/extra_models.json`

AGENTS.md rules files are loaded from `~/.mist/AGENTS.md` (global),
`<CWD>/.mist/AGENTS.md` (project), and `./AGENTS.md` (fallback).

---

## 11. Messaging & UI

### 11.1 Message bus (`messaging/`)

Plugins emit UI messages through the message bus rather than printing
directly:

```python
from code_puppy.messaging import emit_info, emit_success, emit_warning, emit_error
emit_info("Something happened")
```

These are rendered by the TUI's event handler, so they work in both
interactive and streaming contexts.

### 11.2 Event streaming (`agents/event_stream_handler.py`)

The agent's streaming response is handled by `event_stream_handler`,
which processes pydantic-ai streaming events (text deltas, tool calls,
tool returns) and emits UI messages. The `stream_event` callback lets
plugins observe these events.

---

## 12. Development Conventions

### 12.1 Golden rules

1. **Plugins over core** — if a callback hook exists, use it. Don't edit
   `command_line/` or core agent files.
2. **One `register_callbacks.py` per plugin** — register at module scope.
3. **600-line hard cap** per file — split into submodules.
4. **Fail gracefully** — plugins must never crash the app. Wrap external
   calls in try/except.
5. **Return `None`** from hooks/commands you don't own.
6. **Always run linters** — `ruff check --fix`, `ruff format .`
7. **Never allow a Claude co-author commit.**

### 12.2 Plugin structure

```
my_plugin/
├── __init__.py              # docstring (can be minimal)
├── register_callbacks.py    # entry point: register_callback() calls
├── helpers.py               # optional: logic split out
└── README.md                # optional: documentation
```

### 12.3 Zen of Mist

- Simple is better than complex.
- Flat is better than nested.
- If a hook exists for it, use it.
- Files should be readable in one sitting.
- The plugin system is the API surface; the core is the engine.

---

## 13. Quick Reference: Key File Map

| File | Responsibility |
|------|---------------|
| `agents/base_agent.py` | Abstract agent base — thin conductor |
| `agents/_builder.py` | Builds pydantic-ai Agent + MCP wiring |
| `agents/_runtime.py` | `run_with_mcp()` — streaming, retries, cancellation |
| `agents/_compaction.py` | Context summarization |
| `agents/agent_manager.py` | Agent registry, switching, discovery |
| `agents/json_agent.py` | JSON-config agent loader |
| `tools/__init__.py` | `TOOL_REGISTRY`, `register_tools_for_agent()` |
| `plugins/__init__.py` | Plugin loader (builtin → user → project) |
| `callbacks.py` | Hook engine — 45+ phases |
| `config.py` | Config read/write, directories, model settings |
| `model_factory.py` | Model-name → pydantic-ai Model |
| `mcp_/manager.py` | MCP server lifecycle |
| `session_storage.py` | Session pickle save/load |
| `plugins/agent_skills/` | Skills discovery, activation, UI |
| `pydantic_patches.py` | Startup monkey-patches (clipboard fix, etc.) |

---

## When to use this skill

Activate this skill when you need to:
- Understand **how a feature works internally** before modifying it
- **Create a new plugin** and need to know which hooks to use
- **Debug** an agent, tool, model, or MCP issue
- **Navigate the codebase** and need to find the right file
- **Extend Mist** with custom tools, agents, skills, or commands
