# Python → Bun/TS Parity Backlog

Audited 2026-07-17 against the deprecated Python app (`code_puppy/`, ~55
plugins, ~53 hook phases, 40+ browser tools) and the shipped Bun/TS app
(`ts/`). This is the honest gap list, ordered by recommended priority, with
the gotchas that make each item easy or hard.

## Already at parity (shipped in Bun/TS)

Agent loop + streaming + tool dispatch · file tools (`read_file` ranged,
`create_file`, `replace_in_file` exact-match, `list_files`, `grep`, guarded
`shell`) · `ask_user` (now with arrow-key options — ahead of Python) · live
plan (`update_plan` ≈ `update_task_list`) · mid-turn steering (type-while-busy;
Python used Ctrl+T pause) · compaction (manual `/compact`, auto-threshold,
tool-result clearing, protected-token split) · session persistence + `/resume`
picker + `-c`/`-r`/`--sessions` + `/rename` + auto-titling · hooks
(`.mist/hooks.json` intent + pre-tool block/warn) · themes (4, runtime-switch,
persisted) · headroom compression (TS-only) · trace recording `/record` +
`MIST_DEBUG_STREAM` wire capture (TS-only) · input history ↑/↓ · welcome
banner · Claude-Code-style transcript (● narration, Ran-N groups, diff blocks,
Thought-for-Ns) · context-aware spinner glyphs+verbs (TS-only).

Python equivalents intentionally superseded: `.pkl` autosave → JSONL sessions;
prompt_toolkit renderer → Ink; `agent_share_your_reasoning` tool → narration
stream.

---

## P0 — blocks daily-driver parity

### 1. Provider matrix (the single biggest engine gap)
TS speaks **only the Anthropic streaming protocol**. Python supports ~16
`model_type`s: `openai`, `azure_openai`, `custom_openai`, `gemini`,
`custom_gemini`, `gemini_oauth`, `anthropic`, `custom_anthropic`,
`zai_coding`/`zai_api`, `cerebras`, `openrouter`, `chatgpt_oauth`, `copilot`,
`round_robin`, plugin types (`aws_bedrock`, `claude_code`, `synthetic`).
- [ ] `ModelClient` interface in `ts/packages/core` (stream in → normalized
      deltas/tool-calls out); the EventEnvelope seam already isolates the TUI.
- [ ] OpenAI-protocol client (chat-completions + tool calling + reasoning
      models); covers openai/azure/custom/cerebras/openrouter/synthetic/zai.
- [ ] Gemini client.
- [ ] Round-robin wrapper (`rotate_every`).
- [ ] `/add_model` (models.dev live catalog + bundled fallback — the 548KB
      `models_dev_api.json` is language-agnostic, reuse it).
- [ ] Anthropic extras: prompt caching (Python `claude_cache_client`),
      extended-thinking config, beta headers.
- [ ] OAuth device flows (claude-code, chatgpt, copilot, gemini) — port last;
      each is its own token dance + refresh persistence.
- **Gotchas:** per-provider token counting drives compaction thresholds
  (Python has `token_ratio_learner` to tune estimates); OpenAI tool-call
  streaming semantics differ enough that the mock-model test harness needs an
  OpenAI-protocol twin; 429/retry behavior must surface (remember the minimax
  "silent hang" lesson).

### 2. MCP support
Python: stdio/SSE/HTTP servers, `mcp_servers.json`, `/mcp` dashboard + 12
subcommands (list/start/stop/restart/status/edit/remove/logs/search/install/
start_all/stop_all), config wizard, per-agent bindings, retry w/ 4 backoff
strategies, circuit breaker, health monitor, curated catalog (~40KB).
- [ ] Integrate official `@modelcontextprotocol/sdk` (all three transports).
- [ ] `mcp_servers.json` compat (same file, same schema — zero-migration).
- [ ] Tool namespace merge into the engine tool belt + hook gating.
- [ ] `/mcp` command (status dashboard first; wizard later).
- [ ] Minimal reliability: restart-on-crash + timeout. Port circuit-breaker/
      health-monitor **only if real usage demands it** — it's homegrown
      complexity that the SDK may obviate.
- **Gotchas:** stdio child processes from a **compiled** Bun binary work, but
  captured-stdio log piping needs care; server lifecycle in one process (the
  Python version leans on async lifecycles that map cleanly to Bun, but
  blocking-startup semantics need a rethink).

### 3. Headless surfaces: `--serve`, `--rpc`, SDK, `-p`
Python: Starlette HTTP/SSE (`POST /session`, `/message`, `/interrupt`,
`/fork`, `/events` with Last-Event-ID replay, `/share`), auto-generated bearer
token (0600 `server.json`), OpenAPI doc, web client HTML, JSON-RPC 2.0 stdin/
stdout, async SDK (`AgentClient`/`InProcessAgentClient`), `-p --output json`.
- [ ] `Bun.serve` port of the same routes/auth/replay — **the EventEnvelope
      contract and sequence numbers already exist**; EngineSession.buffer is
      the replay log. Smallest-risk P0 item.
- [ ] `-p "prompt" --output json` headless mode (argv mode exists; add JSON).
- [ ] JSON-RPC + TS SDK package (`@mist/sdk`).
- [ ] Session fork (store supports copy; engine needs history-split).
- **Gotchas:** none serious — this was the strangler seam's original shape.

### 4. Input-line UX (the prompt_toolkit gap)
Python got these ~free from prompt_toolkit; Ink needs them hand-built:
- [ ] `@path` fuzzy file completion (+ file index).
- [ ] Per-command completions (`/model`, `/theme`, `/resume`, `/set`, …).
- [ ] Ctrl+R reverse history search.
- [ ] Multiline input (Alt+M/F2 toggle, Ctrl+J newline, bracketed paste).
- [ ] `!cmd` bare-shell passthrough.
- [ ] Cursor movement/editing (word-jump, Ctrl+U/K/W) — Ink gives none of it.
- **Gotchas:** this is a grind, not a risk; consider vendoring a readline-ish
  input component once rather than accreting key handlers in `index.tsx`.

### 5. Config surface
- [ ] `/set` (+ interactive menu) over `mist.cfg`, `/show`.
- [ ] `/cd`, `/reasoning`, `/verbosity`, `/model_settings` (temperature etc.),
      `/pin_model`//`/unpin` (per-agent model pinning — depends on §6).
- [ ] `/truncate`, `/load_context`, `/pop`, `/prune` (history surgery).

---

## P1 — the identity features

### 6. Subagents / multi-agent
Python: 6 built-in agents (code-puppy, planning, qa-kitten, helios/UC,
agent-creator), JSON-defined custom agents (discovered from disk, name-collision
precedence), clones, `invoke_agent` / `invoke_agent_with_model`, persistent
subagent sessions (`session_id` continuation), streaming subagent panels,
usage limits, cancellation.
- [ ] Agent abstraction (name, prompt, tool subset, model, context length)
      over `MistEngine`; JSON agent loader (`.mist/agents/`).
- [ ] `/agent` switch command + roster.
- [ ] `invoke_agent` tool → child EngineSession with scoped event forwarding
      (UI already groups steps; add a subagent panel item kind).
- **Gotchas:** subagent streaming UX is where the Python version got
  complicated (dedicated console, panel plugins); design the envelope
  namespacing (`agent_id` on events) before building UI.

### 7. Safety stack
Python: `/mode plan|build` (+Tab toggle, prompt injection), sandbox backends
(bubblewrap / macOS sandbox-exec SBPL / docker-podman `--network none` /
auto), two-stage provenance-blind classifier (allow/block/ask, fails-to-ask),
injection probe (heuristic|model|off) annotating untrusted tool results,
shell safe-prefix allowlist, destructive-command + force-push guards, denial
escalation, `/trust` scopes (project/domain/remote/org/bucket/service) gating
project plugins and content-trust labels.
TS today: regex FORBIDDEN list + hook block/warn.
- [ ] `/mode plan|build` — cheap, high-value (tool-subset switch + prompt note).
- [ ] Sandbox backends for `shell` (port the three `prepare_shell_command`
      wrappers; SBPL profile and bwrap args are copy-paste).
- [ ] Safe-prefix allowlist + destructive/force-push guards (pure TS logic).
- [ ] `/trust` scopes + project-trust gate (prereq for project plugins §8).
- [ ] Injection probe heuristic mode; model mode after §1 (needs cheap model).
- **Gotchas:** the two-stage classifier is model-backed — latency/cost per
  tool call; keep it opt-in. Windows has no sandbox backend story (Python
  didn't either — document it).

### 8. Plugin system — **the big architectural decision**
Python: 3-tier discovery (project > user > builtin), ~53 hook phases, ~55
built-in plugins, custom slash commands, trust prompt for project plugins.
Python plugins import Python — **none of them can run under Bun**.
- [ ] Decide the model: (a) TS-native ESM plugins (`.mist/plugins/*.ts|js`
      dynamically imported), (b) out-of-process plugins speaking the RPC
      surface (§3), or both — plan doc recommends (a) for built-ins + (b)
      for third-party.
- [ ] Port the hook registry (start with the ~10 phases the core actually
      fires: startup/shutdown, pre/post tool, user_prompt_submit,
      custom_command, stream_event, pre_compact).
- [ ] Triage the 55 built-ins: many are already core TS features (theme,
      spinner_activity, context_indicator, steering, agent_modes) or fold
      into other workstreams (auth plugins → §1, dbos → §9, mcp catalog → §2).
      Genuinely portable long-tail: wiggum/goal loops + judges, pop/prune,
      review_pr, session_share, statusline, emoji_filter, customizable
      commands, kennel memory (§12).
- **Gotchas (verify early):** dynamic `import()` of arbitrary disk paths from
  a **`bun build --compile`d** binary — confirm it resolves external files at
  runtime (we hit sealed-binary import surprises with react-devtools-core).
  If it doesn't, plugins force the out-of-proc route.

### 9. DBOS durable execution
- [ ] Port behind the same `/dbos on|off|status` toggle using DBOS's
      TypeScript SDK; SQLite store in `~/.mist/`.
- **Gotchas:** keep the Python lesson — never wrap subagents (serialization
  of closures), stash/restore MCP toolsets around wrapping.

### 10. Images / vision
Python: Ctrl+V / F3 clipboard-image paste → PNG attachment, `/paste`,
`load_image_for_analysis` tool, attachment plumbing in prompts.
- [ ] Image content blocks in the Anthropic client (and §1 clients).
- [ ] Clipboard→PNG capture (macOS `pngpaste`/`osascript`; Linux `xclip`).
- [ ] `load_image` tool + `@image.png` attachment syntax.
- **Gotchas:** terminal image *display* isn't needed (Python didn't render
  them either) — only ingestion.

### 11. Browser automation + QA agent
Python: ~40 Playwright tools + qa-kitten agent + saved workflows.
- [ ] Optional module: `playwright` (TS-native) behind lazy install — do NOT
      compile it into the binary.
- **Gotchas:** Playwright wants its own browser downloads (~hundreds of MB);
  must stay an opt-in extra with a graceful "run `mist browser install`"
  path from the sealed binary.

---

## P2 — long tail (port on demand)

- [ ] **Skills** (`/skills`, `activate_skill`, `list_or_search_skills`).
- [ ] **Kennel memory** (`/kennel` local memory search/stats).
- [ ] **Universal Constructor** (`/uc`, user-authored `uc:*` tools) — in TS
      this becomes "write a plugin" if §8 lands; maybe fold together.
- [ ] **Wiggum / goal loops** (`/wiggum`, `/goal` + LLM judges, `/judges`).
- [ ] **Session share** (`/share` redacted HTML export / `--upload`).
- [ ] **Session trees** (`/tree`, `/fork`, labels).
- [ ] **Theme catalog**: 13 curated palettes (catppuccin ×2, tokyo-night,
      solarized-light, rose-pine-dawn, …) + OSC terminal-palette application
      + `/diff` and `/colors` color pickers + **light themes** (TS themes
      assume dark terminals today). Breathing themes (mist/hinokami/moon) are
      the new identity; port the catalog as "civilian" themes.
- [ ] **Onboarding**: `/tutorial`, first-run wizard.
- [ ] **PR workflows**: `/generate-pr-description`, `/review`.
- [ ] **Statusline** (Claude-Code-style external statusline scaffold).
- [ ] **`/context` visualization** (token bar: ▒ overhead █ messages ░ free).
- [ ] **Keymap config** (`keymap.py` — user-remappable cancel/pause keys).
- [ ] **Emoji filter, prompt_newline, wide completion menu** (cosmetic toggles).

## Cross-cutting gotchas

1. **Test asymmetry.** Python: ~45k lines of pytest. TS: 26 bun tests. The
   golden-transcript parity harness (mock model) is the leverage point —
   record Python-engine transcripts for the same scenarios and assert the TS
   engine's envelope stream matches shape-for-shape before porting risky
   subsystems (§1, §6).
2. **Sealed-binary dynamic loading** (§8 gotcha) — one spike answers it;
   do the spike before designing the plugin API.
3. **Windows.** Bun-on-Windows is fine for the core, but: no sandbox backend,
   different clipboard tooling, `bash -lc` shell assumption in `tools.ts`
   breaks (needs cmd/powershell path), keybinding differences. Python
   special-cased Windows (UTF-8 stdio forcing, uvx notes). Decide support
   tier before the release matrix.
4. **Packaging cutover.** Release matrix (`bun build --compile` per platform,
   Homebrew tap, Scoop manifest), pip shim that downloads the binary so
   `uvx mist-agent` keeps working one cycle, then archive `code_puppy/`.
5. **models.json compatibility.** TS reads `~/.mist/extra_models.json` with
   its own shape; Python reads `models.json` + models.dev cache. Unify on one
   registry file before `/add_model` lands, with migration.
6. **Two config worlds.** Python `mist.cfg` has dozens of keys (compaction
   strategy/threshold, tool-result clearing knobs, sandbox, probe, prefixes,
   yolo…). TS reads only `model` + env vars. `/set` (§5) should adopt the
   same key names so existing user configs keep meaning something.
