# Plugin & Callback System

> Part of the `code-puppy-agent` skill. Read this before writing a new
> plugin, or when debugging why a hook isn't firing / is being
> overwritten. See `SKILL.md` for the overview and the full reference map.

---

## Plugin discovery (three tiers)

| Tier | Location | Load order |
|------|----------|------------|
| **Builtin** | `code_puppy/plugins/<name>/register_callbacks.py` | 1st |
| **User** | `~/.code_puppy/plugins/<name>/register_callbacks.py` | 2nd |
| **Project** | `<CWD>/.code_puppy/plugins/<name>/register_callbacks.py` | 3rd (highest precedence) |

Each plugin is a directory containing `register_callbacks.py`. The loader
auto-discovers it. Project plugins shadow user plugins on name collision.

## The callback hook system

`register_callback(phase, func)` at module scope. The callback engine
(`callbacks.py`) stores functions per phase and fires them at the right
time. All hooks accept sync or async functions.

**Most important hooks for extending Code Puppy:**

| Hook | When | Return value |
|------|------|-------------|
| `startup` | Once, at process start | (no return value used) — do one-time setup/migrations here, NOT at module import time (see below) |
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

## Minimal plugin example

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

## Two gotchas that will bite you, both discovered building `namespace_skill_search`

`namespace_skill_search` (`code_puppy/plugins/namespace_skill_search/`)
groups skills into namespaces and replaces the flat per-skill list in the
system prompt with a compact directory + a `browse_skill_namespace` tool
(see `SKILLS_SYSTEM.md` for what it does from a user's perspective). It's
also a good reference implementation for two hook-system pitfalls that
are easy to hit and don't fail loudly when you do:

### 1. `get_model_system_prompt` is last-write-wins, not additive

If two plugins register a `get_model_system_prompt` callback, the second
one processed can silently overwrite the first one's `instructions` —
`model_utils.prepare_prompt_for_model` threads augmenter results through
sequentially, and whichever callback runs last on a given key wins. This
is *not* a merge; the built-in `agent_skills` plugin's own contribution
(the flat skill list) can be clobbered by a badly-timed second callback
on the same phase.

**If you need to add content to the system prompt, use `load_prompt`
instead whenever possible.** `load_prompt` fragments from every plugin
are simply newline-joined by `base_agent.py::get_full_system_prompt` —
there's no merge conflict possible, by construction. This is exactly why
`namespace_skill_search` injects its namespace directory via
`load_prompt` and explicitly avoids `get_model_system_prompt`, even
though the content it's replacing (the flat skill list) is itself
injected through `get_model_system_prompt`.

### 2. Don't mutate config (or do any other real work) at import time

A plugin's `register_callbacks.py` module body runs once, at import —
which happens during every plugin scan, including in test collection.
Anything at module scope that does real work (writes to
`~/.code_puppy/puppy.cfg`, hits the filesystem, calls out to a network)
is:

- **Hard to test** — you'd need `importlib.reload()` gymnastics to
  exercise it in isolation, and reloading re-runs *every* top-level
  statement in the module, not just the one you wanted to test.
- **Not observable** — it just happens silently whenever the module
  happens to get imported, with no log line tied to a specific lifecycle
  event.
- **A pattern already solved by the `startup` callback.** See
  `code_puppy/plugins/theme/register_callbacks.py`'s
  `_apply_default_theme_on_first_run`, registered via
  `register_callback("startup", _apply_default_theme_on_first_run)`.

`namespace_skill_search` follows this pattern for its one piece of real
setup work (turning off the built-in flat skill list the first time it
ever runs): the config mutation lives in a plain function,
`_maybe_disable_frontmatter()`, registered on `startup` — not executed
as a bare statement in the module body. That function is directly
callable and testable with mocked config, exactly like the theme
plugin's equivalent.

If you're doing a **one-time migration** (config flip, cache rebuild,
etc.), also consider a dedicated marker config key to record "this
plugin already ran its migration," independent of whatever value the
thing you migrated currently holds — otherwise you can't distinguish
"never ran yet" from "user changed it back after we ran." See
`_MIGRATION_MARKER_KEY` in `namespace_skill_search/register_callbacks.py`
for a worked example.

---

## Plugin structure convention

```
my_plugin/
├── __init__.py              # docstring (can be minimal)
├── register_callbacks.py    # entry point: register_callback() calls
├── helpers.py               # optional: logic split out
└── README.md                # optional: documentation
```

For a plugin that also ships a builtin skill via `register_skills`
(rather than, or in addition to, tools/prompt fragments), see
`code_puppy/plugins/code_puppy_agent/` (this skill's own plugin) or
`namespace_skill_search`'s README for a fuller worked example of
justifying design decisions in-repo rather than only in a PR
description.
