# System Prompt Assembly, Configuration, Messaging & i18n

> Part of the `code-puppy-agent` skill. Read this when debugging what
> ends up in the system prompt (and in what order), working with
> `puppy.cfg`, emitting UI messages from a plugin, or wrapping
> user-facing strings for i18n. See `SKILL.md` for the overview and the
> full reference map.

---

## System Prompt Assembly

Assembled in two stages: `get_full_system_prompt()` builds the base
(`base_agent.py`), then `_assemble_instructions()` (`_builder.py`)
appends rules and runs the per-model patcher.

`get_full_system_prompt()` layers:

```
1. Authored prompt   (agent.get_system_prompt())
2. load_prompt fragments (plugin-injected: kennel memory, permission
   rules, namespace_skill_search's namespace directory, …)
3. Identity ID        (agent name + UUID prefix)
```

`_assemble_instructions()` then appends:

```
4. AGENTS.md puppy_rules  (global ~/.code_puppy/AGENTS.md, then project
   <CWD>/.code_puppy/AGENTS.md, then ./AGENTS.md fallback — concatenated,
   not first-wins)
5. Extended-thinking note  (only if active for the resolved model)
6. Per-model patches       (get_model_system_prompt callbacks, via
   prepare_prompt_for_model) — this is where the **skills block**
   (available-skills summary) is appended, by the agent_skills plugin
```

> The skills summary is **not** a `load_prompt` fragment — it's injected
> through `get_model_system_prompt`, so it lands *after* identity and
> rules. **This is exactly the phase `namespace_skill_search` avoids
> registering a second callback on** — see `PLUGINS_AND_CALLBACKS.md`
> for why (`get_model_system_prompt` is last-write-wins across plugins,
> not additive like `load_prompt`).

Layers 2–6 are **runtime-only** — recomputed every run, never persisted
into static agent definitions. This prevents stale timestamps, dead file
paths, and baked-in session IDs from leaking into cloned agents.

---

## Configuration System (`config.py`)

All settings live in `~/.code_puppy/puppy.cfg` (INI format) managed via:
- `get_value(key)` / `set_value(key, value)`
- `/set <key> <value>` slash command

Key directories:
- **Config root**: `~/.code_puppy/`
- **State/sessions**: `~/.code_puppy/state/` (or platform cache dir)
- **Cache**: `~/.code_puppy/cache/`
- **Agents**: `~/.code_puppy/agents/`
- **Skills**: `~/.code_puppy/skills/`
- **Plugins**: `~/.code_puppy/plugins/`
- **Extra models**: `~/.code_puppy/extra_models.json`

AGENTS.md rules files are loaded from `~/.code_puppy/AGENTS.md` (global),
`<CWD>/.code_puppy/AGENTS.md` (project), and `./AGENTS.md` (fallback).

### Disabling a plugin

`/plugins disable <name>` writes to the `disabled_plugins` config key
(JSON list) via `code_puppy/plugins/config.py`. A disabled plugin's
callbacks are skipped entirely — but any *persisted config change* the
plugin already made before being disabled (e.g. `namespace_skill_search`
turning off `frontmatter_in_system_prompt` on its first run) does **not**
automatically revert. Disabling the plugin and undoing what it already
did to your config are two separate actions.

---

## Messaging & UI

### Message bus (`messaging/`)

Plugins emit UI messages through the message bus rather than printing
directly:

```python
from code_puppy.messaging import emit_info, emit_success, emit_warning, emit_error
emit_info("Something happened")
```

These are rendered by the TUI's event handler, so they work in both
interactive and streaming contexts.

### Event streaming (`agents/event_stream_handler.py`)

The agent's streaming response is handled by `event_stream_handler`,
which processes pydantic-ai streaming events (text deltas, tool calls,
tool returns) and emits UI messages. The `stream_event` callback lets
plugins observe these events.

---

## Internationalization (i18n)

User-facing CLI/TUI text is localizable via the `code_puppy/i18n/` package
(stdlib-only; no Babel). **Full guide: `docs/I18N.md`.** Epic: PUP-473.
This section is a quick-reference cheat sheet, not a replacement for that
doc.

### Call sites

```python
from code_puppy.i18n import t, ngettext, lazy
emit_info(t("startup.welcome", name=owner))     # simple, interpolated
emit_info(ngettext("files.deleted", count=n))   # plural-aware
emit_info(lazy("startup.ready"))                 # resolved at render time
```

- Keys are dotted IDs; **interpolation uses `{name}` only** — no f-strings,
  no `str.format` on catalog text (attribute/index access and format specs are
  deliberately unsupported; catalogs are untrusted input).
- A missing key echoes the key back — resolution **never raises**.

### Catalogs & locales

- JSON per locale: `i18n/locales/<locale>.json` (dotted-key → string, or a
  plural dict `{"one": ..., "other": ...}`).
- Shipped: `en-US` (source), `es` (Latin American `es-419` folded in), and
  `fr-CA`. Regional catalogs are added only when reviewed translations exist.
- **Fallback chain**: plain BCP-47 truncation, `es-AR → es → en-US` (see
  `i18n.locale.fallback_chain`). `i18n.locale.PARENT_LOCALES` is a currently-
  empty CLDR override seam for non-truncation parents. Plugins / the private
  fork can register extra catalog dirs via `i18n.catalog.add_catalog_dir()`.

### How it wires in

- **Choke point**: `messaging/message_queue.py::emit_message` resolves a
  `LazyTranslation` to a string; plain strings pass through unchanged.
- **Locale**: `config.get_locale()` is the single source of truth (delegates
  to the i18n translator), seeded `CODE_PUPPY_LOCALE` › `locale` config key ›
  POSIX env › `en-US`. `/set locale <tag>` persists it.
- **Formatting**: `i18n.format_number` / `i18n.format_datetime` (locale-aware).

### Rules

- **Model-facing system prompts are OUT of scope** — translating them changes
  LLM behavior. Don't run them through the seam. (This is why
  `namespace_skill_search`'s namespace-directory prompt fragment is plain,
  un-wrapped English — it's model-facing content, not user-facing UI text.)
- Extraction goes behind the coverage/pseudolocale CI gate
  (`tests/i18n/test_i18n_coverage.py`): every translated key must exist in the
  `en-US` source, and a pseudolocale (`en-XA`) run must emit only bracketed
  text (catches un-externalized strings).
- **Find what's left to extract** with the static audit:
  `python -m code_puppy.i18n.audit --top 15` lists the worst files;
  `--list` shows every raw `emit_*`/`console.print` site, `--json` is
  machine-readable, and `--fail-under PCT` is a CI gate. Use it to pick the
  next module, then the pseudolocale test above to prove it's fully migrated.
