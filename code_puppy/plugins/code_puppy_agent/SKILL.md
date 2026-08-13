---
name: code-puppy-agent
description: How Code Puppy itself is built — its internal architecture, structure, codebase layout, and source modules. Explains agents, tools, the plugin/callback hook system, models, MCP, sessions and history/context windows, skills (including skill namespaces for large catalogs), slash commands, config, messaging/UI, system-prompt assembly, and i18n. Activate for ANY question about how Code Puppy works internally, why it behaves a certain way, where something lives in the code, how a feature is implemented, or how to navigate, debug, or extend the codebase (add a tool, agent, plugin, command, skill, model, or MCP server).
version: "2.0"
author: code-puppy
tags:
  - code-puppy
  - architecture
  - structure
  - internals
  - codebase
  - source
  - how-it-works
  - self-awareness
  - agents
  - tools
  - plugins
  - hooks
  - callbacks
  - models
  - mcp
  - sessions
  - history
  - skills
  - namespaces
  - commands
  - config
  - messaging
  - i18n
  - extend
  - debug
  - reference
---

# Code Puppy — Architecture & Internals

This skill is a **self-awareness document**. When activated it teaches the
LLM how Code Puppy is structured under the hood so it can navigate the
codebase, debug issues, and extend the product without guessing.

> **Philosophy:** Code Puppy is plugin-first. Nearly all new functionality
> should be a plugin under `code_puppy/plugins/` that hooks into core via
> `code_puppy/callbacks.py`. Don't edit `code_puppy/command_line/` or core
> agent files unless a hook genuinely doesn't exist.

This skill is split across multiple files so activating it doesn't force
the full ~30KB of internals into context on every use — this SKILL.md is
the index. **Read the reference file for the topic you actually need**;
each one is self-contained and cites real file paths so you can jump
straight to source. All reference files are plain repo paths under
`code_puppy/plugins/code_puppy_agent/` — read them with `read_file`.

---

## Layered Architecture

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

## Reference Map

| File | Read this for |
|------|----------------|
| `AGENTS_AND_TOOLS.md` | How agents are structured/discovered (Python, JSON, plugin agents, precedence). How tools get registered and wired to an agent. Async-tool blocking-I/O gotcha. |
| `PLUGINS_AND_CALLBACKS.md` | Plugin discovery tiers, the full callback hook table, a minimal plugin example, and **two hook-system gotchas** (`get_model_system_prompt` last-write-wins; don't do real work at import time) worth reading before writing any new plugin. |
| `MODELS_AND_MCP.md` | ModelFactory, model config precedence, model types. MCP server lifecycle, agent bindings, and a known gap (MCP servers can't yet provide skills). |
| `SESSIONS_AND_HISTORY.md` | Message history, context-window compaction, session save/load commands. |
| `SKILLS_SYSTEM.md` | Skill discovery/activation, bundled-resource-file gotcha for plugin-registered skills, and **skill namespaces** — how `namespace_skill_search` groups large skill catalogs and replaces the flat prompt list. |
| `SYSTEM_PROMPT_CONFIG_AND_I18N.md` | Exact system-prompt assembly order (which layer skills/rules/patches land in), `puppy.cfg` + key directories, the messaging bus, and an i18n quick-reference (full guide: `docs/I18N.md`). |

Don't guess which file has what you need — the table above is exhaustive
for this skill's scope. If a question doesn't map cleanly to one row, it's
probably answered by combining two (e.g. "why did my plugin's prompt
addition get silently dropped" is a `PLUGINS_AND_CALLBACKS.md` +
`SYSTEM_PROMPT_CONFIG_AND_I18N.md` question).

---

## Development Conventions

### Golden rules

1. **Plugins over core** — if a callback hook exists, use it. Don't edit
   `command_line/` or core agent files.
2. **One `register_callbacks.py` per plugin** — register at module scope.
3. **600-line hard cap** per file — split into submodules. (This very
   skill was split for exactly this reason — it was 632 lines as one file.)
4. **Fail gracefully** — plugins must never crash the app. Wrap external
   calls in try/except.
5. **Return `None`** from hooks/commands you don't own.
6. **Always run linters** — `ruff check --fix`, `ruff format .`
7. **Wrap user-facing strings** in `t()`/`ngettext` (see
   `SYSTEM_PROMPT_CONFIG_AND_I18N.md`) — don't hardcode English display
   text. Model-facing system prompt content is explicitly exempt.
8. **Never allow a Claude co-author commit.**

### Plugin structure

```
my_plugin/
├── __init__.py              # docstring (can be minimal)
├── register_callbacks.py    # entry point: register_callback() calls
├── helpers.py               # optional: logic split out
└── README.md                # optional: documentation
```

### Zen of Code Puppy

- Simple is better than complex.
- Flat is better than nested.
- If a hook exists for it, use it.
- Files should be readable in one sitting.
- The plugin system is the API surface; the core is the engine.

---

## Quick Reference: Key File Map

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
| `plugins/namespace_skill_search/` | Namespace grouping + on-demand browse tool for large skill catalogs |
| `i18n/` | Internationalization: catalogs, `t()`/`ngettext`, locale detection, formatting |
| `i18n/locales/*.json` | Message catalogs (source of truth: `en-US.json`) |
| `pydantic_patches.py` | Startup monkey-patches (clipboard fix, etc.) |

---

## When to use this skill

Activate this skill when you need to:
- Understand **how a feature works internally** before modifying it
- **Create a new plugin** and need to know which hooks to use
- **Debug** an agent, tool, model, skill, or MCP issue
- **Navigate the codebase** and need to find the right file
- **Extend Code Puppy** with custom tools, agents, skills, or commands

Then read the specific reference file(s) from the map above — don't try
to hold all six in context at once unless the question is genuinely
that broad.
