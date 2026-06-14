# Code Puppy TUI Rebuild — Phased Plan

> **Status:** approved direction, planning phase. Spike validated (`spikes/textual_spike/`).
> **Decision:** rebuild the UI on **Textual** (Python, in-process) as a new
> `RendererProtocol` implementation + input provider over the existing
> `MessageBus`. Non-Python frameworks were eliminated (see Decision Record).
> **Strategy:** big-bang full rebuild (with an incremental safety valve, see §7).

---

## 1. Why Textual (Decision Record)

Three constraints decided it, all confirmed by the spike:

| Constraint | Outcome |
|---|---|
| Stay pure `uvx`/`pip`-installable | Textual is one Python dep. Non-Python = node/binary bundle. **Eliminates Ink/Ratatui/OpenTUI/Bubble Tea.** |
| Polish bar = "clean, modern, cohesive" | Textual delivers header/footer/command-palette/modals/theming out of the box. |
| Web on the roadmap | `textual-serve` serves the *same app* to a browser — one codebase, zero rewrite. |

**The reuse multiplier:** the ~53KB of Rich formatting in `rich_renderer.py`
ports nearly verbatim — refactor each `_render_x` to **return a renderable**
instead of calling `console.print`, then mount it in a Textual widget.

Frameworks surveyed (June 2026 data): Bubble Tea 43.1k (Go), Ink 38.9k (JS/React,
powers Claude Code/Codex/Gemini CLI), Textual 36.3k (Python), Ratatui 21.0k (Rust),
OpenTUI 11.8k (TS, young).

---

## 2. Target Architecture

```
┌──────────────────────── one Python process ────────────────────────┐
│  Agent core (UNCHANGED)                                              │
│       │ emits Pydantic AnyMessage          ▲ reads AnyCommand        │
│       ▼                                     │                        │
│   MessageBus (bus.py, UNCHANGED)            │                        │
│       │ outgoing queue            incoming queue                     │
│       ▼                                     ▲                        │
│   TextualRenderer (NEW, impl RendererProtocol)                       │
│       │ message_to_renderable(msg) -> Rich renderable               │
│       ▼                                     │                        │
│   CooperApp (NEW Textual App)                                        │
│     • ChatScreen: RichLog (output) + Input (prompt)                 │
│     • ModalScreens: model picker, MCP wizard, /set, diff, onboarding │
│     • key bindings -> push AnyCommand (steer/cancel/pause) to bus    │
└─────────────────────────────────────────────────────────────────────┘
```

**Invariant:** the agent never knows what's drawing. Everything crosses the
`MessageBus`. The 1,895 `emit_*` call sites do **not** change.

---

## 3. Work Buckets (scope + de-risk status)

| # | Bucket | Effort | Status |
|---|---|---|---|
| 1 | **Renderer** — cover all `AnyMessage` types, refactor `_render_x` to return renderables | M | **De-risked** (spike `renderer.py`) |
| 2 | **Chat shell + input** — replace prompt_toolkit input loop; wire steer/cancel/pause keys | M | Partly proven (spike input loop) |
| 3 | **Menus** — rebuild ~50 prompt_toolkit menus as `ModalScreen`s | **L (≈70%)** | **De-risked** (spike `model_picker_screen.py`) |
| 4 | **Console leak cleanup** — route 33 stray `Console()` sites through the bus | S–M | Not started |

Cost signals (from grep): 1,895 `emit_*` (no change) · 33 `Console(` (must route) ·
161 `prompt_toolkit` imports across 50 files (must replace).

---

## 4. Phases

### Phase 0 — Foundations & feature flag (S) —  DONE
**Goal:** new UI can be toggled on without deleting the old one.
*Shipped: `textual` dep; 3-layer `ui_mode` resolver in `config.py`; `code_puppy/tui/`*
*(`app.py` CooperApp scaffold, `renderer.py` TextualRenderer over the real bus,*
*`launcher.py`, `screens/`); `/ui` command; cli_runner gating; `tests/tui/` (12 tests).*
- Add `textual` (and later `textual-serve`) to `pyproject.toml` deps.
- Introduce a launch switch with **three layers** (decided): a `puppy.cfg` config
  key for the persistent default, a `CODE_PUPPY_UI=textual|classic` env var that
  overrides it, and a `/ui` slash command to flip live in-session. Default
  `classic` until parity. Precedence: `/ui` (session) > env var > config > default.
- Create `code_puppy/tui/` package skeleton: `app.py`, `renderer.py`, `screens/`, `widgets.py`.
- Stand up the headless pilot test harness (mirror the spike's `run_test` pattern) in `tests/tui/`.
- **Exit:** `CODE_PUPPY_UI=textual` boots an empty CooperApp; classic path untouched.

### Phase 1 — Output renderer parity (M) — DONE (Option B: capture bridge)
**Goal:** every message type renders in Textual as well as it does today.
*Shipped: `code_puppy/tui/capture.py` (RichCaptureFormatter) drives the real*
*RichConsoleRenderer against an in-memory console and converts ANSI ->*
*`Text.from_ansi` for RichLog. Zero formatting duplication, full message-type*
*parity, zero risk to classic UI, all policy gates reused. Interactive/animated*
*types (spinner, input/confirm/select) are skipped here -> Phase 2 widgets.*
*`tests/tui/test_capture_parity.py` covers all types. Native renderable*
*promotion for hot paths (diff/markdown/shell) deferred to a later phase.*
- Promote `message_to_renderable` to production; add a branch per `AnyMessage`
  subtype (TextMessage, FileListing, FileContent, GrepResult, Diff, Shell*,
  AgentReasoning, AgentResponse, SubAgent*, StatusPanel, VersionCheck, Skill*,
  Divider, SpinnerControl).
- Refactor `rich_renderer.py` `_render_x` methods to **return** renderables; the
  classic renderer keeps `console.print(renderable)`, the Textual one mounts it.
  (Shared formatting, two thin sinks — DRY.)
- Honor existing config gates (`get_output_level`, suppress flags, pause/silence,
  sub-agent verbosity) in the new renderer.
- Spinners → Textual `LoadingIndicator`/status; map `SpinnerControl`.
- **Exit:** a scripted message-replay test shows visual parity for all types.

### Phase 2 — Chat shell, input & control plane (M) — IN PROGRESS
**Goal:** the main interactive loop is fully Textual.
*2a DONE: prompt submits real agent turns via a Textual `@work` worker
(`run_prompt_with_attachments`, streaming routed to a hidden console so it
can't corrupt the screen); tool activity renders live via the bus; the final
AgentResponseMessage renders as markdown; slash commands dispatch through
`handle_command`; exit/quit + busy-state input lock. Remaining: steering/
cancel/pause, interactive request modals, completions, shell passthrough,
live token streaming.*
*2d DONE: interactive request modals (TextInput/Confirm/Selection ModalScreens
in `screens/interactive.py`). handle_bus_message routes UserInputRequest/
ConfirmationRequest/SelectionRequest to a modal that ALWAYS replies via
`bus.provide_response` (even on Escape) so the agent can't hang. Fixed a latent
bug: SelectionResponse.selected_index `ge=0` rejected the documented `-1`
cancel sentinel -> relaxed to `ge=-1` (also fixes classic selection-cancel).*
*2b DONE: control plane. Escape hard-cancels the running turn (Textual worker
.cancel()); Ctrl+T pauses the agent (PauseAgentCommand) and opens a steer modal
that injects SteerAgentCommand(mode='now') + ResumeAgentCommand on submit, or
just resumes on cancel. Busy-state always clears.*
*2e DONE: prompt completion. `completion.py` computes /command (from the
registry) and @path (reusing the classic file_path_completion internals)
candidates; a non-focusable CompletionList dropdown above the prompt, driven
by keys forwarded from PromptArea (Up/Down navigate, Tab/Enter accept, Esc
dismiss). on_mount imports command_handler so built-in commands register up
front. Remaining Phase 2 (optional): shell passthrough, live token streaming,
long-tail completers (model args / skills / mcp / pins).*
*POLISH DONE: !shell passthrough runs captured (not inheriting stdio) on a
thread worker and emits results via the bus; live token streaming previews
response text deltas (TextPartDelta) line-buffered into a transient,
auto-scrolling #stream RichLog (registered via the stream_event callback),
cleared when the final markdown lands in #log. Remaining: long-tail completers.*
- ChatScreen: scrollback `RichLog` + **multiline `TextArea`** prompt (decided —
  supports multi-line prompts/paste; bind Enter=submit, Shift+Enter=newline).
- Reimplement the input loop currently in `cli_runner.interactive_mode`:
  history file, completions, slash-command dispatch, `!shell` passthrough,
  exit/quit, Ctrl+C cancel, Ctrl+D exit.
- Wire the **control plane** to bus commands:
  - Ctrl+T → `PauseAgentCommand` / steering (`SteerAgentCommand`) → resume.
  - Esc/Ctrl+C → `CancelAgentCommand`.
  - Honor `request_input`/`ConfirmationRequest`/`SelectionRequest` as in-app modals
    (replaces the async prompts in `rich_renderer._render_user_input_request`).
- **Port the completers faithfully** (decided): recreate path / model / slash-command
  completion from `prompt_toolkit_completion.py` as a Textual completion dropdown
  over the `TextArea`. (Command palette stays as a bonus, not the primary path.)
- **Exit:** a full agent turn (prompt → tools → response) runs end-to-end in Textual,
  including steer + cancel.

### Phase 3 — Menus as ModalScreens (L — the big one) — IN PROGRESS
**Goal:** every `/command` menu is a Textual modal.
*Foundation DONE: `screens/base.py` FilterableListScreen + ListChoice (the
reusable filter+list+dismiss kit); `menus.py` MENU_OPENERS maps menu commands
to modal openers; app._dispatch_command intercepts a BARE menu command (e.g.
/model) to open the modal, while args (/model gpt-x) fall through to the
classic handler. First menu ported: /model (picker applies via
set_model_and_reload_agent). Ported so far: /model, /agent (+/a /agents), autosave load picker
(__AUTOSAVE_LOAD__), /set (two-step: pick key -> edit value via the validated
apply_setting; TextInputModal gained a prefill option), /diff (two-step color
picker; ListChoice gained a `style` field so rows render color swatches).
Wave A COMPLETE. Also ported /colors (3-step banner->color swatch picker,
reusing the ListChoice.style swatches). Remaining: B (MCP family), C leftovers
(/judges CRUD, /add-model wizard, /uc tool browser, onboarding). Note: those
are forms/CRUD/wizards; MCP is a multi-screen wizard cluster.*
*FormScreen kit DONE: screens/form.py FormScreen + FormField (kinds: text/
password/select/bool, required-field validation, dismiss(values_dict) or None).
The reusable multi-field-form building block for the remaining wizard/CRUD
menus.*
*WAVE B (MCP) DONE: tui/mcp_install.py ports /mcp install [id] - catalog
browser (FilterableListScreen over catalog.servers + a custom entry) ->
per-server FormScreen (custom name + env vars + cmd args) -> install_server_
from_catalog; custom path -> FormScreen(name/type/command/args/url/auth) ->
register_server + persist to MCP_SERVERS_FILE. app._dispatch_command routes
/mcp install to it. All OTHER /mcp subcommands (list/start/stop/status/logs/
remove/restart/help) already work in the TUI - they only emit via the bus.
Remaining: /uc (tool browser), onboarding; long-tail completers.*
*WAVE C progress: /judges (CRUD - list->add/edit FormScreen / delete
ConfirmModal; FormScreen gained 'textarea' kind) + /add_model (manual form
writing an extra_models.json entry - pragmatic replacement for the 54KB
models.dev catalog wizard) DONE. Remaining: /uc (bespoke tool browser),
onboarding wizard, long-tail completers.*
Build a small reusable kit first (DRY), then port menus in waves.
- **Kit:** `screens/base.py` with a `FilterableListScreen` (filter Input +
  OptionList + dismiss-with-value), `FormScreen`, `ConfirmScreen`. The model
  picker spike is the template.
- **Wave A (high traffic):** model picker, `/set` settings, agent menu, diff menu.
- **Wave B (MCP):** the entire `command_line/mcp/` wizard family (install/list/
  start/stop/logs/custom-server form) — biggest sub-cluster.
- **Wave C (config/onboarding):** colors menu, judges menu, autosave menu,
  add-model menu, model-settings menu, onboarding wizard/slides, UC menu.
- Each ported menu: delete its prompt_toolkit impl behind the feature flag,
  add a pilot test.
- **Plugin extensibility (decided):** add a `register_screen` callback hook so
  plugins can contribute their own Textual modals/widgets (mirrors the existing
  `register_*` hook family in `callbacks.py`). Document it in `CONTRIBUTING`/`HOOKS.md`.
- **Exit:** zero `prompt_toolkit` imports remain under `command_line/` for the
  Textual path; all 50 menus have modal equivalents + tests; `register_screen`
  hook live with one example plugin screen.

### Phase 4 — Console leak cleanup (S–M)
**Goal:** nothing prints behind Textual's back.
- Audit the 33 `Console(` sites; reroute each through the bus (`emit_*`) or the
  app's `write_renderable`.
- Add a guard/test that fails if a raw `Console().print` runs while the Textual
  app owns the terminal.
- **Exit:** no stray output corrupts the TUI in a full session.

### Phase 5 — Polish, theming, web, cutover (M)
**Goal:** make it the default; light up web.
- Theme pass (map existing banner/diff colors to Textual CSS variables; respect
  `colors_menu` config).
- Fix the web (`textual-serve`) errors deferred earlier; document the web launch.
- Performance: batch high-frequency streaming writes to `RichLog`; verify firehose
  shell output doesn't stutter.
- Flip default to `CODE_PUPPY_UI=textual`; keep `classic` as fallback for one
  release, then remove.
- Update README + docs; remove the `spikes/` directory.
- **Exit:** Textual is default, classic removed, docs updated.

---

## 5. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Menu volume (50) drags on | High | Med | Reusable screen kit; port in waves; each is mechanical. |
| Thread→UI marshalling bugs | Med | Med | Single funnel via `call_from_thread`; covered by pilot tests. |
| Streaming throughput / flicker | Med | Med | Batch writes; `RichLog` is designed for this; perf test in Phase 5. |
| Steering/pause/cancel regressions | Med | High | Port behavior 1:1 from `pause_controller`; explicit tests. |
| Console leaks corrupt the screen | Med | Med | Phase 4 audit + guard test. |
| Web parity gap (deferred errors) | Low | Low | Isolated to Phase 5; native is the primary target. |
| Completion UX worse than prompt_toolkit | Med | Med | Prototype completion early in Phase 2; fall back to palette. |

---

## 6. Testing Strategy

- **Headless pilot tests** (`App.run_test()`) for every screen and the main loop —
  already proven in the spike (no TTY needed, CI-friendly).
- **Message-replay parity tests:** feed a fixed list of `AnyMessage` through both
  renderers; assert no exceptions + snapshot key structure.
- **Control-plane tests:** simulate Ctrl+T steer, Esc cancel, confirmation modals.
- Keep `ruff check --fix` + `ruff format` green; 600-line cap per file.

---

## 7. Big-Bang vs. Incremental (safety valve)

Chosen: **big-bang** (one cohesive rebuilt UI). The feature flag in Phase 0 gives
us an *optional* incremental path for free: ship the Textual chat shell (Phases
0–2) behind the flag while menus (Phase 3) are still being ported, falling back to
classic menus if needed. Same end state, lower risk. Recommend keeping the flag
until Phase 5 cutover regardless.

---

## 8. Resolved Decisions

1. **Launch switch** — **all three layers**: `puppy.cfg` key (persistent default) +
   `CODE_PUPPY_UI` env override + `/ui` live toggle. Precedence: session > env >
   config > default(`classic`). *(Phase 0)*
2. **Completion UX** — **port the prompt_toolkit completers faithfully** to a
   Textual dropdown; command palette is a bonus. *(Phase 2)*
3. **Input widget** — **multiline `TextArea`** (Enter submit / Shift+Enter newline). *(Phase 2)*
4. **Plugin hooks** — **yes, add `register_screen`** so plugins contribute Textual
   screens/widgets. *(Phase 3)*
5. **Web errors** — **fix in this effort, Phase 5**, alongside cutover.

---

## 9. Spike Artifacts (throwaway, to be deleted at Phase 5)

`spikes/textual_spike/` — proves the thesis end-to-end:
- `renderer.py` — TextualRenderer over the real bus (bucket 1)
- `app.py` + `smoke_test.py` — chat shell + e2e loop (bucket 2)
- `model_picker_screen.py` — real menu as modal w/ live data (bucket 3)
- `serve.py` — browser via textual-serve (web roadmap; has known errors)
- `preview.png` / `preview_modal.png` — visual proof
