# Contributing to Code Puppy 1.x

> **Golden rule:** Code Puppy 1.0 is a *distribution* of
> [`pydantic-ai-pax`](https://github.com/pydantic/pydantic-ai/tree/main/src/pydantic_ai_pax)
> ("pax"; named `pydantic-clai2` until 2026-11-19).
> The runtime owns the agent loop, terminal UI, sessions, models, MCP and
> plugins. Do not reimplement any of that here. New behaviour is a pax
> `Plugin`, a `pydantic-ai-harness` capability, or an upstream change.

Plan and status: `docs/upgrade/code_puppy_1_0_rewrite_plan.md`.

## Layout

| Path | Holds |
|---|---|
| `code_puppy/main.py` | Entry point for `pup` / `code-puppy`; import-light until the splash is up |
| `code_puppy/identity.py` | Names and directories. Stdlib-only |
| `code_puppy/distribution.py` | **Every** replacement of a pax name. Nowhere else |
| `code_puppy/update.py` | `/update`, `pup update`: PyPI lookup, version rules, wording |
| `code_puppy/branding.py`, `_art.py` | Banner, welcome lines, splash art |
| `code_puppy/splash/` | Startup animation, stdlib-only. Preview: `python -m code_puppy.splash` |
| `code_puppy/migrate/` | One-time carry-over of a 0.0.x setup |
| `code_puppy/legacy_store.py` | `puppy.db`: Code Puppy's own SQLite file |
| `code_puppy/api_keys.py` | Exports saved API keys for model providers |
| `code_puppy/legacy_sessions.py` | 0.0.x sessions as an import source for `/resume` |
| `code_puppy/builtin_plugins.py` | Plugin declarations Code Puppy ships |
| `code_puppy/personality.py` | The `personality` plugin: the main agent's name, tone and opinions |
| `code_puppy/first_run.py` | First interactive launch: asks the puppy's and owner's names, once |
| `code_puppy/compat/` | Bridge that runs 0.0.x plugins |
| `code_puppy/callbacks.py`, `config.py`, `messaging/`, `i18n/`, `plugins/` | 0.0.x import paths, kept as thin facades |

## Rules

1. **One pin.** `pydantic-ai-pax` is pinned exactly and carries the harness and
   `pydantic-ai-slim` pins. Never add a direct pin for either.
   It is required with every extra it offers (the `/sandbox` providers,
   `typesafe`), so nothing answers "support is not installed";
   `tests/test_optional_support.py` fails when pax adds one.
   `pydantic-clai2` is now only an alias package, and we no longer depend on
   it: through it every import was a *second* copy of pax's files, so
   `pydantic-claude-code` 0.7.x (which still imports the old name) registered a
   `Plugin` pax had never seen. `code_puppy/former_name.py` answers
   `pydantic_clai2.commands` and `.plugins` with pax's own modules instead. Keep
   it until that plugin imports `pydantic_ai_pax`.
   Claude Code models come from **`pydantic-claude-code`**. Do not "fix" that
   to `pydantic-ai-claude-code`: that PyPI name is someone else's project.
2. **Replacements live in `distribution.py`.** If you must replace another
   pax name, add it there with `_replace`, add a row to the table in its
   docstring, and add it to `REPLACED` in
   `tests/test_distribution_contract.py`. Each one is debt: prefer an upstream
   seam.
3. **The 0.0.x plugin API is frozen.** `callbacks.py`, `config.py`,
   `messaging/`, `i18n/` and `plugins/` exist so old plugins import. Do not add
   hooks or helpers to them, and do not import them from new code.
4. **Optional tools load on demand.** Anything a plugin adds for the model
   (tools, MCP servers, capabilities) is created with `defer_loading=True`.
5. **Legacy files are read-only.** The migration never modifies, renames or
   deletes a 0.0.x file, and never overrides a value already set in 1.0.
6. **Startup stays light.** `identity.py` and the top of `main.py` import
   nothing from the runtime. Heavy imports happen under the splash.
7. **Fail gracefully.** A broken plugin or a bad legacy file is reported and
   skipped. It never stops `pup` from starting.
8. **Tests never touch the user's machine.** `tests/conftest.py` redirects the
   home directory and disables the OS keyring for every test. Keep it that way.
9. **600-line cap per file.** Split by responsibility, not to hit the number.
10. **Always run linters:** `uv run ruff check --fix`, `uv run ruff format .`,
    then `uv run pytest`.
11. **NEVER ALLOW A CLAUDE CO-AUTHOR COMMIT.**
12. **Keep this file under 10,000 characters.** It is sent to the model with
    every request. `tests/test_agents_md_size.py` enforces the budget.

## Releasing

- Only `main` publishes, and only stable 1.x: what `uvx code-puppy` gets.
  CI bumps the version: `--bump patch`, or `--bump stable` when git holds a
  pre-release (`1.0.0rc1` becomes `1.0.0`, not `1.0.1`). The `v1` RC branch
  is retired. `scripts/check_release_version.py` refuses anything else.
- A release can only depend on packages released to PyPI. Between runtime
  releases a branch may build against a commit of pydantic-ai `main`:
  `[tool.uv.sources]` in `pyproject.toml`, every package at one `rev`. The
  release guard refuses to publish in that state. Restore
  `pydantic-ai-pax==X.Y.Z` and delete the sources before merging.
- Pushing to `main` publishes. Do not push without being asked.

## Writing a plugin

Use the pax `Plugin` API (`pydantic_ai_pax/_docs/PLUGINS.md` in the installed
package). A plugin Code Puppy ships gets a declaration in
`code_puppy/builtin_plugins.py`. A user drops a file or package into
`~/.code_puppy/plugins/`.

## 0.0.x plugins

A folder with a `register_callbacks.py` is a 0.0.x plugin. The bridge loads
three tiers: the `code_puppy.plugins` entry-point group, the user's plugins
folder, and `<repo>/.code_puppy/plugins/` once trusted with
`/puppy-plugins trust NAME`. Trust is a SHA-256 of the plugin folder; any edit
revokes it.

`code_puppy/callbacks.py` lists all 77 hook names in three tiers:

- **Supported (15):** fire at the equivalent runtime moment.
- **Accepted and removed (62):** register without error, never fire.
  `/puppy-plugins` shows which plugins rely on them.

Tool hooks receive 0.0.x tool names (`agent_run_shell_command`, `create_file`);
the mapping is in `code_puppy/compat/tools.py`. Update it when the runtime
renames a tool, or guards written against the old names stop matching.

## Known gaps

- **Windows:** the agent's commands run in PowerShell, not `sh` (the runtime's
  `WindowsWorkspace`). No interactive session with a real model has been run yet.
- JSON agents, the `/agent` command and ports of the retired core plugins are
  not built yet. See the plan.
