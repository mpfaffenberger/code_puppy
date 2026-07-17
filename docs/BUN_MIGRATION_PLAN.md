# Mist → Bun/TypeScript Migration Plan

Status: **proposal — approved direction, pre-implementation**
Scope: full rewrite of Mist (~106k lines of Python, 432 files) onto the Bun
runtime in TypeScript.
Decision record: the owner confirmed a full TS/Bun rewrite (not a sidecar, not
a perf pass) on 2026-07-16.

---

## 0. The honest framing

Bun cannot run Python. "Migration" here means a **ground-up rewrite** in which
every load-bearing dependency is replaced:

| Today (Python) | Role | Target (TypeScript/Bun) |
|---|---|---|
| `pydantic-ai` | agent engine: tool loop, streaming, retries, usage | **Vercel AI SDK** (`ai`) — tool calling, streaming, provider registry; or hand-rolled loop if we need pydantic-ai-level control |
| `pydantic` | schemas/validation | **Zod** (native fit with AI SDK tool schemas) |
| `rich` + `prompt_toolkit` | TUI: Live regions, colors, input, completion | **Ink** (React for CLIs) or **opencode-style** custom renderer; `@inkjs/ui`; `prompts`/custom line editor |
| `termflow` | streaming markdown → ANSI | **marked + marked-terminal**, or port termflow's incremental parser (no drop-in equivalent — see Risks) |
| MCP (pydantic-ai bundled) | MCP client | **`@modelcontextprotocol/sdk`** (official TS SDK — first-class) |
| DBOS Python | durable execution | **DBOS TypeScript** (`@dbos-inc/dbos-sdk`) — exists, same company |
| Starlette/uvicorn/sse-starlette | headless server | **`Bun.serve`** (native HTTP + WebSocket; SSE via streams) |
| `httpx` | HTTP client | native `fetch` |
| sqlite (DBOS store) | persistence | **`bun:sqlite`** (built-in, fast) |
| pytest (~45k lines of tests) | tests | **`bun test`** (Jest-compatible) — tests are *rewritten*, scenarios reused as specs |
| PyInstaller + uvx/pip packaging | distribution | **`bun build --compile`** — single-file executables per platform (a genuine upgrade) |
| pyfiglet | wordmark | `figlet` npm port or embed pre-rendered glyphs |

What ports **verbatim** (the real IP, all language-agnostic):
- Every system prompt authored this cycle (working principles, engineering
  judgment, tool economy, communicating results, orchestrator overlay,
  capability-awareness rules, attribution).
- The compaction/summarization instruction set and its heading structure.
- UX specs: Option B persistent footer semantics, step ledger, spinner presets,
  task-list-in-footer, output levels, Cinnamon theme palette.
- The safety model: provenance-blind classifier design, injection-probe
  heuristics (regexes port directly), trust scopes, denial escalation.
- The HTTP/SSE API contract (`EventEnvelope`, session endpoints) — this is the
  migration seam itself.
- Docs, ROADMAPs, AGENTS.md conventions, models.json (data).

What is **lost/rebuilt**: the Python plugin ecosystem (callbacks are
Python-import based), all pytest suites as executable tests, pip/uvx install
paths during transition.

---

## 1. Strategy: strangler, not big bang

We already shipped the seam: `mist --serve` exposes sessions over HTTP/SSE with
a versioned `EventEnvelope`, plus a JSON-RPC mode and an async SDK. So the
rewrite proceeds **front-to-back against a running Python engine**, with a
working product at every phase:

```
Phase 1:  [Bun TUI] ──HTTP/SSE──> [Python engine (mist --serve)]
Phase 2+: [Bun TUI] ──in-proc───> [Bun engine]        (Python retired)
```

Benefits: user-visible value first (the snappy TUI is the point of Bun),
apples-to-apples parity testing (same API, two engines), and a viable stopping
point mid-way (TS front-end + Python engine) if priorities shift.

---

## 2. Phases

### Phase 0 — Foundations (~1 week)
- `bun init` a workspace at `ts/` in this repo (monorepo keeps prompts/docs/
  specs shared; split repos only at GA if desired).
- Packages: `ts/packages/core` (engine), `ts/packages/tui`, `ts/packages/protocol`
  (EventEnvelope + API types, generated/hand-ported from `code_puppy/events.py`).
- Toolchain: Bun ≥1.2, TypeScript strict, Biome (lint+format), `bun test`, CI
  job (matrix: macOS/Linux) alongside the existing Python CI.
- Verify current versions of: `ai` (Vercel AI SDK), `@modelcontextprotocol/sdk`,
  `@dbos-inc/dbos-sdk`, Ink — pin them. (Plan written against Jan-2026
  knowledge; confirm at kickoff.)

### Phase 1 — Bun TUI against the Python engine (~3-5 weeks) ⭐ first ship
- Implement the TUI in Ink talking to `mist --serve`:
  prompt line w/ completion, streamed markdown rendering, **persistent footer**
  (heartbeat + activity + step ledger + task list — port the Option B semantics
  1:1), output levels, theme (Cinnamon), spinner presets, Ctrl+C/Ctrl+T flows.
- Subscribe over SSE with `Last-Event-ID` resume; submit/interrupt/fork via the
  existing endpoints.
- Exit criteria: daily-drivable `mist-ts` binary (`bun build --compile`)
  against the Python server; tmux-harness parity captures vs the Python TUI
  (`docs/how-to-use-access-TUI.md` workflow applies unchanged).

### Phase 2 — Core engine in TS (~4-6 weeks)
- Agent loop on Vercel AI SDK: streaming, tool dispatch, retries, usage caps;
  provider registry driven by the existing `models.json` (Anthropic, OpenAI,
  custom-anthropic endpoints like minimax, round-robin).
- Context management port: history hashing, token estimation, **tool-result
  clearing**, compaction (truncation + summarization agent), protected-tail
  splitting — port `_history.py`/`_compaction.py` logic function-for-function;
  property-test against recorded Python fixtures.
- System prompts imported verbatim; dynamic fragments (cwd context, agents
  roster, mode line) as TS providers.
- `Bun.serve` implementation of the same HTTP/SSE API (the TUI doesn't notice).
- Exit criteria: golden-transcript parity — identical prompts/tool scenarios
  produce equivalent event streams from both engines.

### Phase 3 — Tools & MCP (~3-4 weeks)
- Port the tool belt: file ops (read ranges, grep, edits with exact-match
  semantics), shell runner (streaming, timeouts, background), task list,
  ask-user-question, subagent invocation (`invoke_agent`), skills discovery.
- MCP via the official TS SDK (stdio + SSE servers, tool prefixing).
- Safety gates: permission modes, shell-prefix classifier (port regex/shlex
  logic), destructive-command + force-push guards, injection probe, denial
  escalation, two-stage classifier backend.

### Phase 4 — Platform & plugins (~3-4 weeks)
- Config system (`mist.cfg` compatible read; migrate to TOML/JSON later),
  sessions/autosave (`bun:sqlite`), kennel memory, themes, onboarding.
- **Plugin system rethink**: Python entry-point plugins can't port. Options:
  (a) TS plugins (dynamic import of `register_callbacks.ts`) mirroring the
  callback names; (b) out-of-proc plugins over the RPC surface. Recommend (a)
  for built-ins + (b) for third-party. Port built-in plugins (spinner_activity,
  agents_roster, cwd_context, answer_echo, theme, …).
- DBOS-TS durability behind the same `/dbos` toggle; subagents stay non-durable
  (preserve the pickle-crash lesson — same rule, new runtime).

### Phase 5 — Parity, cutover, distribution (~2-3 weeks)
- Side-by-side beta (`mist` = Python, `mist-ts` = Bun) → flip default.
- `bun build --compile` release matrix replaces PyInstaller job; keep pip
  shim that downloads the binary for one compatibility cycle.
- Docs/README rewrite; archive `code_puppy/` after one stable release.

**Total: roughly 3.5–5.5 months of focused solo effort** (parallelizable to
~2-3 months with subagent fan-out on well-specified ports, e.g. tools and
plugin ports are highly parallel).

---

## 3. Top risks (ranked)

1. **`pydantic-ai` has no true equivalent.** Vercel AI SDK covers 80% but
   differs in streaming event granularity, retry semantics, and history
   processors. Mitigation: Phase 2 golden-transcript parity harness; keep our
   own thin agent-loop layer so the SDK is swappable.
2. **Streaming markdown renderer.** termflow's incremental ANSI rendering is
   bespoke; marked-terminal is not incremental. Budget real time here or port
   termflow's parser. This is the #1 "feels worse than Python" risk — and the
   double-spacing/`eps**` class of bugs lives exactly here. Build the
   stream-replay debug harness (`MIST_DEBUG_STREAM`) into the TS renderer from
   day one.
3. **TUI regression of hard-won UX.** Option B footer, pause/steer, approval
   menus — re-verify each with the tmux harness; the captures in this repo are
   the spec.
4. **Test coverage cliff.** 45k lines of pytest don't port. Mitigation:
   scenario extraction (each test file's *behaviors* become a checklist),
   fixtures recorded from Python runs replayed in `bun test`.
5. **Ecosystem churn** (Bun/AI SDK move fast). Pin versions; upgrade windows
   per phase.
6. **Split-brain maintenance** during the overlap. Freeze Python feature work
   after Phase 2 starts; bugfixes only.

---

## 4. Open decisions (defaults chosen, revisit at Phase 0)

- **TUI framework:** ~~Ink vs custom ANSI renderer~~ **DECIDED: Ink (GO,
  2026-07-16).** Spike verified against the live Python engine: `<Static>`
  gives print-above semantics natively, footer animated in 12/12 tmux frames
  while streaming SSE. Escape hatch to a custom renderer remains for the
  streaming-markdown pane only.
- **Repo layout:** monorepo `ts/` (default) vs new repo.
- **Name/binary:** `mist` (TS takes over the name at cutover) — default yes.
- **pydantic-ai fidelity:** exact event-shape parity vs "close enough +
  documented deltas". Default: parity for `EventEnvelope`, freedom inside.

## 5. Immediate next actions (Phase 0 kickoff)

1. Scaffold `ts/` workspace (`core`, `tui`, `protocol`), Biome, `bun test`, CI.
2. Hand-port `EventEnvelope` + session API types to `ts/packages/protocol`;
   contract-test them against a live `mist --serve`.
3. Spike: Ink app that connects to `mist --serve`, streams one session with a
   pinned footer — go/no-go on Ink vs custom renderer within a week.

---

## Discovery log

- **2026-07-17 — Cutover executed: `mist` = Bun/TS.** The Phase-5 flip is
  done ahead of full parity, per user direction: `/opt/homebrew/bin/mist` →
  `ts/dist/mist` (compiled binary, renamed from `mist-ts`); `mist-ts` kept
  as a legacy alias to the same binary; `mist-py` → the Python venv build as
  the transition escape hatch. Python app now prints a deprecation notice at
  interactive startup and is in maintenance mode (bug fixes only). README
  rewritten with the TS quickstart as primary. Still Python-only, pending
  port: MCP, subagents/orchestration, plugins, DBOS, `--serve` HTTP surface,
  full theme catalog. Packaging cutover (release matrix + pip shim) remains.

- **2026-07-16 — "Python headless hang" root-caused: provider quota.** The
  apparent engine hang (`mist --serve` / `-p` turns never completing, even at
  baseline commit `84b33f1`) coincided with the minimax **Token Plan being
  exhausted** — the TS engine's first live call surfaced the truth instantly
  with `HTTP 429: Token Plan usage limit reached`, while the Python engine
  swallows the condition into silent retries with no user-facing signal.
  Corrected conclusion: not a pre-existing engine bug; it's quota exhaustion
  plus poor 429 surfacing. Two follow-ups: (a) live-model verification of the
  Bun engine is blocked until quota is topped up or another key is provided —
  everything else is verified against a protocol-faithful mock model;
  (b) the Python engine's silent-retry-on-429 UX is a real defect worth a
  loud error, tracked separately.

- **2026-07-16 — Milestone: self-contained `mist-ts` binary runs the full
  agentic loop.** `bun build --compile` produces a 62MB single binary (TUI +
  in-proc Bun engine). tmux-verified end-to-end with the protocol-faithful
  mock model: prompt → tool_use → real shell execution (`✓ $ seq 1 4` step
  row) → tool_result → token-streamed markdown answer (headers/bold/bullets
  rendered) → input returns. Zero Python, zero network.

  **Honest parity status (mist-ts v0 vs Python Mist):** shipped — agent loop,
  Anthropic-protocol streaming (incl. custom endpoints like minimax), 6-tool
  belt (ranged read / create / exact-match edit / list / grep / guarded
  shell), ported core system prompt, polished TUI, mock-model test harness.
  **Not yet ported:** MCP, subagents/orchestration, plugins, safety
  classifiers beyond the destructive-command guard, compaction/tool-result
  clearing, /commands + config UI, themes, sessions/autosave, DBOS. Live-model
  verification blocked on provider quota (mock-verified; endpoint path proven
  up to the provider's 429).

---

## Product decisions (2026-07-16, owner-directed)

- **Prolog: rejected.** No load-bearing fit — policy rules, plan constraints,
  and dependency graphs are all better served by plain TS (Zod, small
  functions) than by embedding a Prolog runtime (tau-prolog is slow/obscure;
  SWI is a heavyweight native dep). Revisit only if we ever build
  datalog-style whole-repo code indexing, which is out of scope.
- **Headroom: integrated behind `MIST_HEADROOM=1`.** `headroom-ai` (TS SDK,
  local-first) compresses bulky tool results (>2k chars) before they enter
  history via `compress([{role:"tool",content}])`; savings surface in the
  status line ("↓N saved") via `headroom.saved` events. Graceful no-op if the
  lib fails — original content always wins. Off by default until savings are
  validated on real workloads.
- **Plan-DST + steering (the workflows-style visualization).** The model
  maintains a live plan via the `update_plan` tool (full-replace, statuses
  pending/active/done/skipped); `plan.updated` envelopes re-render a bordered
  Plan panel in place while the agent works. The user can **type mid-run +
  Enter to steer**: nudges queue into the engine and inject as user messages
  before the next model request ("freshest intent — adjust immediately").
- **Clarifying questions (Claude-Code-style, capped).** `ask_user` engine tool
  suspends the loop on a Promise; the TUI swaps the input box into an answer
  box. Prompt caps it: at most 1-2 sharp questions, only when undiscoverable
  and a wrong guess is costly.
- **Hooks (intent preservation + guardrails).** `.mist/hooks.json`
  (project ∪ user): `intent` — a durable project-vision paragraph injected
  into the system prompt every turn (anti-drift); `pre_tool` regex rules
  (block/warn) gate tool calls before execution.
- **Status granularity: codex as the bar.** One concise line per action
  (`✓ $ cmd`, `✓ read path`, `✓ grep 'x' — N matches`), no narration between
  steps, plan + heartbeat carry the "what's happening" load.

- **2026-07-17 — LIVE-verified with GLM-5.2.** The owner's z.ai subscription
  (`https://api.z.ai/api/anthropic`, model code `glm-5.2` — note: Claude Code's
  `glm-5.2[1m]` suffix is client-side, the API rejects it) registered in
  `~/.mist/extra_models.json` with **zero engine code changes**. tmux-verified
  full stack on the compiled binary: GLM spontaneously published a 3-item plan
  (live ▸/○ panel), executed create_file + read_file on real files, streamed
  the answer token-by-token, returned to input. The strangler payoff: model
  onboarding is pure config.
