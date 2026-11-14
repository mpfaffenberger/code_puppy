# Code Puppy 1.0 rewrite plan

Status: direction agreed (section 11). Nothing in this plan has been implemented yet.
Target version: `1.0.0rc1`, then `rcN` until cutover to `1.0.0`.
Release candidates are opt-in; `uvx code-puppy` keeps resolving to 0.0.x (section 13).

## 1. Outcome

Code Puppy 1.0 stops being its own agent runtime and becomes a thin, branded
distribution of `pydantic-clai2` (soon `pydantic-pax`) on top of
`pydantic-ai-harness` and `pydantic-ai`.

Done means:

- `pup` / `code-puppy` start the clai2 runtime with Code Puppy identity.
- Existing settings, models, credentials, MCP servers, skills and agents carry
  over automatically on first run.
- Existing Code Puppy plugins and JSON agents keep working through a compat layer.
- `code-puppy-core-plugins` is not a dependency.
- The `code_puppy` package shrinks from about 97k lines to roughly 10k.

## 2. What the plan is based on

Measured on 2026-11-13.

| Fact | Value |
|---|---|
| `code_puppy/` today | 97,239 lines, 343 files |
| `tests/` today | 119,637 lines, 457 files |
| `code_puppy_core_plugins` (non-test) | about 58k lines, 60+ plugins |
| Current pins | `pydantic-ai-harness==0.64.0`, `pydantic-ai-slim==2.64.0` |
| Latest releases (PyPI, 2026-11-12) | harness `0.68.0`, slim `2.68.0`, `pydantic-clai2` `0.68.0` |
| `pydantic-pax` on PyPI | does not exist yet |
| clai2 on `pydantic-ai` main | about 68k lines (estimated from file sizes) |
| Hooks defined in `callbacks.py` | 77 |
| Hooks the core plugins actually register | 54 |
| `code_puppy.*` surface the core plugins import | 86 modules, 263 names |

Three findings change the shape of the work:

1. **The harness and clai2 moved.** Both now live in the `pydantic/pydantic-ai`
   monorepo (`src/pydantic_ai_harness`, `src/pydantic_clai2`). The checkout at
   `code\pydantic-ai-harness` is the old repository, frozen at v0.32.0. Its
   `pydantic-clai2/` is a 6.5k-line early version and must not be the baseline.
2. **Peers is on main but unreleased.** `pydantic_ai_harness/peers` landed on
   2026-11-13 (#11671), one day after 0.68.0. The same day's #13401 renamed
   `subagents`, `filesystem` and `spend` to `sub_agents`, `file_system` and
   `spend_limits`.
3. **Agent Teams is a design, not code.** `PLAN.md` on `pydantic-ai` main says
   "No code yet", and none of its types (`ClaimablePlanStore`, `member_runner`,
   `TeamEvent`) exist on main. Teams is out of scope for this plan.

Today Code Puppy uses only three harness modules: `code_mode`, `compaction`
and `tool_output_limits`. Everything else is reimplemented locally, which is
where the deletion comes from.

## 3. The central decision: distribution, not fork

Decided: depend on `pydantic-clai2` and extend it through its plugin API.
Its source is not copied into this repository.

- A fork would add 68k lines here and need a permanent merge from upstream.
- A dependency keeps the cache, authority-of-voice and speculation behaviour
  identical to what the benchmarks measured.
- Pin `pydantic-clai2` exactly and let it carry the harness and slim pins. It
  already pins both exactly, so one pin replaces three.

This only works if clai2 gains a few seams it does not have today (section 9).
The most important one: the config root and keyring service name are the
literal `'pydantic-clai2'` in `config/settings_store.py` and
`config/credential_store.py`, and `cli/self_update.py` reinstalls
`pydantic-clai2`. The pax rename is the natural moment to make these injectable.

## 4. Target layout

```text
code_puppy/
  main.py            entry points: build identity, run migration, call clai2 chat()
  identity.py        name, config root (XDG dirs when set, else ~/.code_puppy),
                     splash, spinners, default instructions
  migrate/           puppy.cfg, models, credentials, MCP servers, session importer
  compat/            bridge plugin, hook map, tool aliases, JSON agents,
                     legacy plugin discovery and trust
  callbacks.py       facade: register_callback keeps its signature
  config.py          facade: get/set backed by the SQLite store
  messaging/         facade: emit_* forwarded to the clai2 console
  plugins/           native plugins for features with no upstream equivalent
```

The facades stay at their old import paths because third-party plugins import
them. Each is a few dozen lines that forward to clai2.

## 5. Requirements and where each comes from

"Wired" means clai2 on main already uses it. "Gap" is work this plan owns.

| Requirement | Provided by | Wired in clai2 | Gap |
|---|---|---|---|
| Cache performance | harness `cache_stability`, `warn_on_cache_busts`; core `caching` | yes | Delete `claude_cache_client.py`, `pydantic_patches.py` and custom model clients so nothing bypasses it |
| Authority of voice | core message framing, `reinject_system_prompt`; harness provenance | yes | Compat hooks that rewrite messages must not change roles |
| Durable execution | core `durable_exec` (DBOS, Temporal, Prefect); harness `step_persistence` | `StepPersistence` only | Expose DBOS/Temporal as an opt-in plugin |
| Sandboxes and workspaces | harness bubblewrap, smol, modal, daytona, e2b, docker, `ssh_workspace` and others | `builtin_plugins/workspaces` | Confirm every listed provider is selectable; docs |
| Deferred loading | core `defer_loading`, tool search | integrations and MCP | Force `defer_loading` on everything the compat bridge registers |
| TUI and input box | clai2 `ui/`, `termflow-md>=1.0` | yes | Puppy theme, splash, spinners |
| Legacy plugins and JSON agents | none | no | Section 6 |
| Background tool calling | harness `background_tools` | no | Wire `BackgroundTools` into the stock agent |
| Agent teams | not implemented | no | Out of scope |
| Peer to peer | harness `peers` (main only) | no | Cross-process `PeerNetwork` transport; turns on in the first RC built on a release that contains Peers |
| Load time, Windows | clai2 lazy imports, bytecode install | yes | Delete `prewarm_sdks`, early-startup hacks; measure |
| Code mode, eager and speculative | harness `code_mode`, `ipython_code_mode`; clai2 speculation | Monty only | Add the IPython REPL choice |
| Settings in SQLite | clai2 `config.db` | yes | Importer from `puppy.cfg` (section 7) |
| No core-plugins dependency | none | none | Section 8 |

The benchmark results need no work of their own. They hold as long as Code
Puppy runs the stock clai2 agent rather than a modified loop.

## 6. Backward compatibility

### 6.1 Legacy plugins

Keep `register_callback(hook, func, fail_closed=False)` unchanged. One native
clai2 plugin, the bridge, replays clai2 moments into the registered callbacks.

Discovery keeps all three tiers and the existing trust model:

- entry-point group `code_puppy.plugins`
- `~/.code_puppy/plugins/<name>/register_callbacks.py`
- `<cwd>/.code_puppy/plugins/<name>/register_callbacks.py`, gated by the
  SHA-256 trust in `plugins/trust.py`

The bridge must skip entry points owned by the `code-puppy-core-plugins`
distribution. Otherwise a user who still has it installed gets all 60 old
plugins loaded on top of their native replacements.

Hooks fall into three tiers. The exact assignment is the first deliverable of
phase 3; this is the proposed shape.

| Tier | Meaning | Hooks |
|---|---|---|
| 1, supported | Mapped to a clai2 plugin method or a capability | `startup`, `shutdown`, `custom_command`, `custom_command_help`, `load_prompt`, `pre_tool_call`, `post_tool_call`, `run_shell_command`, `file_permission`, `register_tools`, `register_agent_tools`, `register_agents`, `register_skills`, `register_settings`, `register_model_type`, `load_models_config`, `agent_run_start`, `agent_run_end`, `stream_event`, `user_prompt_submit`, `interactive_turn_end`, `session_end` |
| 2, accepted | Registers without error, warns once, has no effect | styling hooks (`termflow_style`, `prompt_toolkit_style`, ...), `register_cli_args`, `handle_cli_args`, `wrap_pydantic_agent`, `transform_model_messages` |
| 3, removed | Internal plumbing no outside plugin should use | the four `claude_oauth` hooks, `should_skip_fallback_render`, `agent_event_stream_start` |

Tier 1 covers the 22 hooks that account for most registrations in the core
plugins (`custom_command` and `custom_command_help` alone are 72 of them).

Tools from `register_tools` are registered with `defer_loading=True`. That
satisfies the progressive-disclosure requirement for every legacy plugin with
no change on the plugin's side.

Import shims cover the modules plugins actually use. `code_puppy.config`,
`code_puppy.messaging` and `code_puppy.callbacks` are about half of all
imports in the core plugins. The supported list is generated from usage, not
guessed, and frozen as a contract test.

### 6.2 JSON agents

clai2 loads sub-agent definitions from `*.md` and `*.toml`. Code Puppy adds a
loader that reads `~/.code_puppy/agents/*.json` and `.code_puppy/agents/*.json`
at runtime and presents them as the same definitions. No files are rewritten.

Two pieces are needed beyond the loader:

- **Tool aliases.** JSON agents name tools like `agent_run_shell_command` and
  `replace_in_file`. A single table maps each legacy name to its harness tool.
- **Top-level agent switching.** clai2 has no `/agent` command. A native
  plugin adds it by rebuilding the stock agent from the chosen definition.

### 6.3 Dropped

- **i18n.** `code_puppy/i18n` and its catalogs are deleted; clai2 has none.
  `code_puppy.i18n.t` stays as a small English-only facade, because 17 imports
  in the core plugins use it and third-party plugins may too.
- **ACP.** The `agent-client-protocol` dependency and the `acp` plugin are removed.

## 7. Settings and state migration

Runs once at startup, before clai2 opens its stores.

| From | To |
|---|---|
| `puppy.cfg` (configparser) | `config.db` settings table |
| `models.json`, `extra_models.json` | saved models and providers |
| `secret_store` entries | clai2 encrypted credential store |
| `mcp_servers.json` | the `mcp` plugin's store |
| `.code_puppy/skills`, `.code_puppy/agents` | read in place, no copy |
| saved sessions | an importer under `/resume`, beside the existing Claude Code and Codex importers |

Rules:

- Idempotent. A marker row records the migrated source and its hash.
- Non-destructive. The old files are never modified or deleted.
- Keys with no equivalent are stored under a `legacy.` prefix, so the config
  facade still returns them to old plugins.
- `pup migrate --dry-run` prints what would change.
- Sessions are imported on demand, not in bulk. The old pickle formats are the
  riskiest input, and most old sessions are never reopened.

## 8. Deletion ledger

Line counts are today's. "Facade" means a thin forwarding module remains.

| Area | Lines | Replaced by |
|---|---|---|
| `command_line/` | 17,662 | clai2 commands and menus; facades for `set_menu_schema`, `command_registry` |
| `messaging/` | 12,838 | clai2 `ui/`; facade for `emit_*` |
| `agents/` | 11,886 | harness `Coder`, `SubAgents`, `CodeMode`, compaction; JSON loader moves to `compat/` |
| `tools/` | 16,307 | harness `FileSystem`, `Shell`, `Playwright`, `AskUser`, `Skills` |
| `mcp_/` | 8,130 | core MCP capability and the clai2 `mcp` plugin |
| `hook_engine/` | 1,595 | clai2 `hooks` plugin, plus a translator for the old hook file format |
| `config.py` | 3,364 | `config.db`; facade |
| `callbacks.py` | 2,008 | facade plus the bridge |
| `model_factory.py`, model clients, OAuth transports | 5,528 | clai2 `models/` and `/login` |
| `pydantic_patches.py` | 1,114 | nothing; the patches exist to work around the old runtime |
| session storage and migration | 1,713 | `sessions.db`; one importer |
| remaining root modules | 10,553 | clai2 runtime |
| `i18n/`, `plugins/`, `capabilities/`, `events/`, `mcp_prompts/` | 4,541 | `plugins/trust.py` moves to `compat/`; `i18n/` is dropped |

The rows add up to the full 97,239.

Core plugins, by disposition. These are proposed from names and docs; each
needs a short check against clai2 main before it is deleted.

| Disposition | Lines | Examples |
|---|---|---|
| Superseded upstream or dropped, delete | about 36k | `acp`, `chatgpt_oauth`, `copilot_auth`, `herdr`, `theme`, `agent_skills`, `plugin_list`, `prune`, `subagent_panel`, `hook_manager`, `claude_code_hooks`, `spill`, `fork`, `dbos_durable_exec`, `statusline`, `logfire_*`, the three shell and file guards |
| Port as native plugins in this repo | about 22k | `claude_code_oauth`, `computer_use`, `wiggum`, `puppy_kennel`, `jev_grep`, `azure_foundry`, `aws_bedrock`, `pstack`, `meta_oauth`, `grok_oauth`, `ollama`, `customizable_commands` |

Most of the 120k lines of tests go with the code they cover. They are replaced
by contract tests for the compat layer and migration, and tests for the native
plugins.

## 9. Upstream work in `pydantic-ai`

Needed before the matching phase can finish.

| Ask | Needed by |
|---|---|
| Injectable product identity: config root, keyring service, command name, splash, self-update package | phase 1 |
| A PyPI release containing `Peers` | phase 5 |
| `BackgroundTools` and `IPythonCodeMode` selectable in the stock agent | phase 5 |
| A cross-process `PeerNetwork` transport, or agreement that Code Puppy owns one | phase 5 |
| A CLI-argument seam for plugins, if `register_cli_args` is to be tier 1 | phase 3 |

## 10. Phases

Work happens on a `v1` branch. `main` keeps shipping 0.0.x fixes until cutover.
An in-place migration is not practical because clai2 owns the loop and the UI.

**Phase 0: groundwork**

- Set the version to `1.0.0rc1` on `v1`.
- Set up the RC release channel described in section 13.
- Bump `main` to harness 0.68.0 and slim 2.68.0 as a normal dependency update.
  It is independent of the rewrite and shortens the gap.
- Write the compat contract tests against today's implementation, so the same
  tests can judge the new one.
- Open the upstream identity change.

Exit: RC publishing works end to end with a no-op change.

**Phase 1: skeleton**

- Empty `code_puppy/` on `v1`; add `main.py` and `identity.py`.
- Depend on `pydantic-clai2`; drop the direct harness, slim, monty, mcp,
  provider SDK, `agent-client-protocol` and `code-puppy-core-plugins` dependencies.

Exit: `pup` chats, edits files and runs shell commands on Windows, macOS and
Linux, storing state under the Code Puppy config root. Cold start is recorded.

**Phase 2: migration**

- Build section 7.

Exit: a real 0.0.x home directory starts 1.0 with the same model, keys, MCP
servers and settings, and a second start changes nothing.

**Phase 3: compat**

- Facades, bridge, discovery, trust, JSON agents, tool aliases.

Exit: the contract tests pass, and three real third-party plugins load unmodified.

**Phase 4: native plugins**

- Port the survivors from section 8 into `code_puppy/plugins/`.
- Rewrite the "golden rule" in `AGENTS.md`, which currently sends all new work
  to the core plugins repository, and remove its i18n rules.
- Archive `code_puppy_core_plugins` with a final release note.

Exit: feature parity checklist signed off; no import of `code_puppy_core_plugins` remains.

**Phase 5: new capabilities**

- Workspace and sandbox selection, durable execution, background tools,
  IPython code mode, peers.

Exit: each row of section 5 has a demo script that passes.

**Phase 6: harden and cut over**

- Rewrite `README.md` and `docs/`; keep `AGENTS.md` under its 10,000-character cap.
- Gates: Windows cold start, and a session that reports no cache busts.
- Soak on RCs, then merge `v1` to `main` and release `1.0.0`.

## 11. Decisions

1. **Distribution, not fork** (section 3).
2. **Agent Teams is out of scope.** It is not implemented upstream.
3. **Peers ships as soon as a release contains it.** RCs published to PyPI must
   depend on PyPI releases of clai2, so they cannot use the `clai2-bleeding`
   channel (section 13). Development against main is local only.
4. **i18n is dropped** (section 6.3).
5. **ACP is dropped** (section 6.3).
6. **Config root keeps today's rule:** XDG directories when the user sets the
   `XDG_*` variables, `~/.code_puppy` otherwise. This is what `config.py` does
   now, so old plugins and trust files keep finding their paths.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Upstream identity seam is refused or late | It blocks phase 1. Fallback is a small, temporary patch at import time, which is exactly what this rewrite is trying to delete |
| Third-party plugins use hooks outside tier 1 | Tier 2 warns instead of failing; collect the warnings during the RC period |
| Legacy message-rewriting hooks break caching or authority | Tier 2 by default; opt-in only |
| Harness is 0.x and renames modules between minors | One exact pin through clai2; never import a harness module from compat facades without a test |
| Old core plugins still installed beside 1.0 | Bridge skips that distribution's entry points |
| Migration corrupts a working setup | Non-destructive, idempotent, dry-run available |
| Windows regressions in a new TUI | Windows is a gate in phases 1 and 6, not a follow-up |
| A stable 1.x is published by accident during the RC period | The version guard in section 13 fails the publish job |

## 13. Release channel during the RC period

Goal: `uvx code-puppy` keeps getting the latest 0.0.x. Testers opt in to the RC.

This needs no special packaging. Installers skip pre-releases when a stable
release exists. Checked on 2026-11-14 with uv 0.12.17 and `uv pip compile`:

- A bare package name resolves to the highest stable version, even when a
  newer pre-release is published (`protobuf` gave 7.36.2 with 7.37.0rc3 available).
- An exact pin or `--prerelease allow` selects the pre-release.

Testers run `uvx code-puppy@1.0.0rc1`. Prefer the exact pin over
`--prerelease allow`, which also allows pre-releases of every dependency.

Existing 0.0.x installs will not be told to upgrade. Their update notice reads
`info.version` from PyPI, which stays on the highest stable release.

Workflow changes:

| Branch | Bump | Publishes |
|---|---|---|
| `main` | `uv version --bump patch` (unchanged) | `0.0.970`, `0.0.971`, ... |
| `v1` | `uv version --bump rc` | `1.0.0rc2`, `1.0.0rc3`, ... |

- `publish.yml` triggers on `v1` as well, and picks the bump from the branch.
- Its push step rebases onto and pushes to `origin main` by name. It must use
  the triggering branch instead.
- Add a version guard before upload. Fail if the branch is `v1` and the version
  is not a pre-release, or if the branch is `main` and the version is 1.0 or
  higher. The guard matters: `uv version --bump patch` turns `1.0.0rc1` into a
  stable `1.0.1`, which every `uvx code-puppy` user would then receive.
- RC dependencies must be PyPI releases. PyPI rejects direct-URL dependencies,
  so an RC cannot depend on clai2 main. Use `[tool.uv.sources]` for local
  development against main; it does not affect the published metadata.

Cutover: merge `v1` into `main`, run `uv version --bump stable` once to get
`1.0.0`, remove the guard's `main` clause. From then on `uvx code-puppy`
resolves to 1.0.0.

If a bad release escapes, yank it on PyPI; yanked versions are skipped by
unpinned installs.
