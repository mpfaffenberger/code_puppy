# Plan: In-Place Status Rendering (stop stacking intermediate steps)

Status: **proposal — not yet implemented**
Owner: Mist UI/UX
Related feedback: intermediate `AGENT RESPONSE` blocks + tool peeks pile up in
scrollback; users want Claude-Code / Codex-style behavior where intermediate
steps render as a **single live region that updates and replaces**, and only
the final answer (plus a compact step summary) persists.

---

## 1. Problem

During an agentic turn, the model alternates: narrate → call a tool → narrate →
call a tool → … → final answer. Today each of those pieces is printed
**permanently** to scrollback:

- Every assistant text part prints a full-width `AGENT RESPONSE` banner + text
  (`_print_response_banner` in `code_puppy/agents/event_stream_handler.py`).
- Every tool call prints a peek line (`shell: $ …`, `read_file: …`) via
  `_build_legacy_peek` in `code_puppy/messaging/renderers.py`.

So a 6-step task = 6 stacked banners + 6 peek lines. It reads as a noisy log,
not a focused status.

### What "good" looks like
- While working: one **live, updating** region shows the current step
  (`Running: npm test ⠹`) and a short rolling list of recent/completed steps
  (`✓ Read README.md`, `✓ Ran 4 checks`).
- When done: the live region is cleared and replaced by the **final answer**
  only, optionally preceded by a collapsed `▸ 6 steps` summary the user can
  ignore or expand.

---

## ✅ Recommended solution — Option A: "deferred text + live steps ledger"

> This is the chosen approach. Options B and C (§3) are documented only as
> rejected alternatives.

### What it is
A single **live "steps ledger"** — rendered inside the spinner's existing Rich
`Live` region (which already updates in place and self-clears) — replaces the
stacked `AGENT RESPONSE` banners and tool peeks while the agent works:

1. **Defer assistant narration instead of printing it.** Buffer each completed
   text part. Then decide based on what comes next *in the same turn*:
   - a **tool call follows** → that narration was *intermediate*: collapse it to
     a one-line ledger row (`• <gist>`) and **never** write it to scrollback.
   - the **turn ends** right after it → that text was the **final answer**:
     print it to scrollback normally.
2. **Tool calls live in the ledger, not scrollback.** On `pre_tool_call` add an
   active animated row (`Running: npm test ⠹`); on `post_tool_call` collapse it
   to `✓ Ran 4 checks`. The permanent `shell:` / `read_file:` peek lines are
   suppressed.
3. **The ledger updates in place.** It shows the active row (animated) + the last
   *k* completed rows (dim). It lives in / just above the spinner `Live` region,
   so it overwrites itself instead of growing.
4. **On turn end:** clear the ledger and print only the final answer, optionally
   preceded by a collapsed `▸ N steps` line. Nothing is lost — a `/steps`
   command can reprint the full step log on demand.

### Why this one
- Directly maps to the two halves of the problem: intermediate **narration**
  (step 1) and **tool calls** (step 2) both stop stacking and become in-place,
  updating status — exactly the Claude-Code / Codex behavior requested.
- **Reuses** the spinner `Live` region rather than rebuilding the renderer →
  smallest, safest change.
- Ships **incrementally** behind a flag (§4), so the fragile streaming path is
  never broken for users who don't opt in.

### The plan, in one line per phase (detail in §4)
- **Phase 1** — tool calls → ledger rows, suppress permanent tool peeks.
- **Phase 2** — defer/flush intermediate narration (the banner stacking).
- **Phase 3** — end-of-turn `▸ N steps` summary, `/steps`, visual polish.

### The one hard part
We only know a text part is the *final* answer once the turn ends with no tool
call after it (§7 Q2). The whole design hinges on that detection; everything
else is rendering plumbing.

---

## 2. Current architecture (what we build on)

| Piece | Location | Role |
|---|---|---|
| Stream handler | `agents/event_stream_handler.py::event_stream_handler` | Consumes `PartStart/PartDelta/PartEnd` for Thinking/Text/ToolCall parts; prints banners + streams text. |
| Banners | `_print_thinking_banner`, `_print_response_banner` | Full-width colored banners; call `pause_all_spinners()`. |
| Output levels | `config.get_output_level()` → `low`/`medium`/`high` | `low` already collapses tool/thinking/info to one-line peeks; **does not collapse assistant text**. |
| Peeks | `messaging/renderers.py::_build_legacy_peek` + `_LOW_MODE_PEEK_LABELS` | One-line dim summaries in low mode. |
| Spinner (Live) | `messaging/spinner/console_spinner.py` (`rich.live.Live`, `transient=True`) | **Already an in-place, self-clearing region.** Shows activity label + frame + token context. |
| Activity label | `messaging/spinner/spinner_base.py` (`set_activity`) + `plugins/spinner_activity` | Per-tool live status (`Running: …`), resumed during tool exec. |

**Key asset:** the spinner is already a Rich `Live` region that updates in place
and clears on stop. The in-place "steps ledger" is an extension of this idea,
not a from-scratch build.

**Key difficulty:** we cannot know an assistant text part is the *final* answer
until the turn ends (i.e. no tool call follows it). Distinguishing
intermediate-vs-final is the crux.

---

## 3. Design options

### Option A — Deferred text + live steps ledger (recommended)
- **Defer** printing assistant text. Buffer each completed text part instead of
  printing it immediately.
  - If a **tool call follows** → that text was *intermediate*: collapse it into
    the live ledger as a one-line step (`• <first line of narration>`), do not
    print to scrollback.
  - If the **turn ends** right after it → that text was the *final answer*:
    print it normally to scrollback.
- **Tool calls** render only as live ledger rows while running, then collapse to
  `✓ <activity label>` when complete. No permanent peek line.
- The **ledger** is rendered inside (or just above) the existing spinner `Live`
  region: an active row (current step, animated) + the last *k* completed rows
  (dim). On turn end, the ledger is cleared and optionally a collapsed
  `▸ N steps` line is printed.
- Pros: closest to Claude Code; reuses the Live region; bounded scrollback.
- Cons: deferring the final text adds a small latency before it appears
  (we wait to confirm no tool follows); careful handling of streaming vs
  buffering.

### Option B — Two-region layout (transcript + persistent footer)
- A persistent footer `Live` shows current activity + rolling steps; the
  transcript area above only receives final answers.
- Pros: very clean, most "app-like".
- Cons: biggest rework; Rich `Live` + concurrent `console.print` above a pinned
  footer is fragile (line-duplication risks we already fight today). Higher risk.

### Option C — Collapse-on-complete (Rich `Group`)
- Print each step into a `Live(Group(...))`; when a step finishes, rewrite its
  block to a one-line `✓` summary.
- Pros: keeps things visible as they happen.
- Cons: `Live` must own the whole turn's output; interleaving streamed markdown
  (termflow) inside a `Live` group is complex and risky.

### Decision (original)
**Go with Option A.** It delivers the requested behavior, reuses the spinner
`Live` region, and is the most incremental / least risky. Options B/C can be
revisited later if we want a fully pinned footer.

### Decision (REVISED — Option B is now the recommended path)

Option A was implemented (`compact_steps`) and **does not render correctly in
the live TUI**: the ledger's `Live` region flashed/collapsed, intermediate
status stayed invisible, and it spammed `▸ N steps`. Separately, every attempt
at an always-on liveliness signal failed for the **same root cause**:

> Mist streams assistant text via raw `console.file.write` (termflow), which
> **bypasses Rich's `Live` coordination**. Any second writer to the terminal —
> a spinner `Live`, a background OSC title thread — races with that raw stream
> and corrupts output (spinner pauses to avoid it; the OSC heartbeat spewed
> raw `]2;…` into scrollback).

There is no safe side-channel. The only robust fix is to make **one Rich `Live`
own the whole turn's output**, with streamed text routed *through* it. That is
Option B.

See **§3b** below for the full Option B plan.

---

## 3b. Option B — Persistent Footer (recommended)

### Goal
A single, always-present footer (pinned to the bottom) shows liveliness +
current activity + a rolling step ledger, while the transcript scrolls above it.
Because **one** `Live` owns all output, nothing races — no pause/resume hacks,
no corruption, and the liveliness signal is genuinely always-on (incl. the
response-generation gap).

### The core change (and the hard part)
Today: streamed markdown is written with `console.file.write` / a termflow
`SmoothTermflowWriter`, **outside** any `Live`. Option B requires **all** output
during an agent turn to go through the single managed `Live`:

- Wrap the turn in one `Live(get_renderable(), console=…, transient=False)` whose
  renderable is a `Group(transcript_tail, Rule, footer)` — OR use Rich's
  `Live.console.print(...)` so prints scroll *above* the live footer (Rich
  supports printing above a live region when `Live` owns the console).
- Re-point the termflow streaming so each rendered line is emitted via the
  Live-owned console (`live.console.print`) instead of raw `console.file.write`.
  This is the crux: termflow currently emits ANSI directly; it must hand lines
  to the Live-managed console so the footer stays pinned and uncorrupted.
- The footer renderable = heartbeat glyph + spinner activity (`SpinnerBase`
  activity/context) + the `StepLedger` rolling rows. Retire the standalone
  `ConsoleSpinner` `Live` (one `Live` only — two `Live`s conflict).

### Implementation steps (each verifiable in tmux, see §3c)
1. **Footer renderable** — a function returning the `Group(footer rows)` built
   from `SpinnerBase` (activity/context) + `StepLedger`. Pure render, no I/O.
2. **Single turn-level `Live`** — start in `event_stream_handler` (or the run
   wrapper) for the whole turn; `refresh_per_second≈12`; `transient=False` so the
   footer clears cleanly at turn end.
3. **Route streamed text through the Live console** — replace the termflow
   `console.file.write` path with `live.console.print(...)` (or `Live`'s
   "print above" API). Verify no line duplication.
4. **Retire `ConsoleSpinner`'s own `Live`** — its frames/activity now feed the
   footer; remove the pause/resume plumbing (`pause_all_spinners`, the
   `pre_tool_call` resume hack, the response-gap resume).
5. **Liveliness** — the footer animates a heartbeat glyph every frame regardless
   of phase; no side-channel needed.
6. **Ledger** — `compact_steps` rows render in the footer; the "defer narration"
   logic from Option A is reused as-is.

### §3c. Verification harness (now available)
We can drive the real TUI headlessly:
```bash
tmux new-session -d -s mt -x 170 -y 45
tmux send-keys -t mt '.venv-user/bin/mist' Enter        # boot
tmux send-keys -t mt 'list the files then summarize' Enter
# capture rendered frames over time to inspect spinner / footer / artifacts:
tmux capture-pane -t mt -p        # rendered screen (post-escape-processing)
tmux capture-pane -t mt -pe       # include escape sequences (catch corruption)
tmux kill-session -t mt
```
`capture-pane -p` shows exactly what the user sees; `-pe` exposes raw escapes so
regressions like the `]2;` OSC corruption are caught automatically. Each step
above lands behind `compact_steps` (default off) and is validated by capturing
panes mid-stream before flipping the default.

### Risks
- **Line duplication / scroll jank** if termflow text isn't fully routed through
  the Live console — the #1 thing to verify per-step in tmux.
- Performance: one `Live` at ~12fps over a long stream — keep the footer
  renderable cheap (plain `Text`/`Group`, no heavy panels).
- Provider stalls still show the heartbeat (good) — confirm it doesn't fight the
  partially-streamed transcript above.

---

## 4. Phased implementation

Each phase is independently shippable and gated so defaults stay safe.

### Phase 0 — Config + scaffolding (no visible change)
- Add `compact_steps` setting (default **off** initially; flip to on once
  proven). Also reuse `output_level=low` as the natural home — likely gate the
  new behavior on `low` mode OR a dedicated flag. Decide in review (see §7 Q1).
- Add a `StepLedger` helper (`messaging/step_ledger.py`): holds active step +
  recent completed steps; renders a `rich` renderable; thread-safe like
  `SpinnerBase` context/activity.

### Phase 1 — Tool calls become live ledger rows (no permanent peek)
- When `compact_steps` is on: route tool-call status into the ledger
  (`pre_tool_call` → active row; `post_tool_call` → collapse to `✓`), and
  **suppress** the permanent peek line for tool calls.
- Render the ledger inside the spinner `Live` panel
  (`console_spinner._generate_spinner_panel`): activity row + last *k* completed
  rows.
- Outcome: tool steps stop stacking; they live in the updating region.
- Lowest risk (tool peeks are already terse; we're moving them, not inventing
  new streaming).

### Phase 2 — Defer intermediate assistant narration
- In the stream handler, **buffer** completed text parts instead of printing.
  Track whether a tool call follows within the same turn:
  - tool follows → push a collapsed `•` row to the ledger; discard the buffered
    text from scrollback.
  - turn ends → flush the buffered text to scrollback as the final answer
    (with the normal banner).
- Edge cases to handle: multiple text parts before a tool; text with no tool and
  no further parts (final); cancellation/steer mid-turn (flush what we have);
  `high` mode (never defer — show everything).

### Phase 3 — End-of-turn summary + polish
- On turn end: clear the ledger; optionally print `▸ N steps` (dim, collapsed).
- Optional: `/steps` command to reprint the last turn's full step log on demand
  (so nothing is truly lost — it's just not in the scrollback by default).
- Visual polish: spacing, the `✓ / • / ▸` glyphs, dim styling, theme colors.

---

## 5. Affected files (estimate)

- `code_puppy/messaging/step_ledger.py` — **new** (StepLedger model + render).
- `code_puppy/messaging/spinner/console_spinner.py` — render ledger in the Live
  panel.
- `code_puppy/messaging/spinner/spinner_base.py` — ledger accessors (mirror the
  activity/context pattern).
- `code_puppy/plugins/spinner_activity/register_callbacks.py` — push/complete
  ledger rows on pre/post tool call.
- `code_puppy/agents/event_stream_handler.py` — defer/flush assistant text;
  suppress intermediate banners when `compact_steps` is on.
- `code_puppy/messaging/renderers.py` — suppress tool peeks when steps are
  ledgered.
- `code_puppy/config.py` — `compact_steps` getter (+ validation).
- Tests under `tests/messaging/` and `tests/agents/`.

---

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Breaking the main streaming renderer (line duplication, Live conflicts) — the most fragile code in the app | Gate entirely behind `compact_steps` (default off); ship phase-by-phase; keep `medium`/`high` paths untouched. |
| Deferred final answer feels laggy | Only defer *completed* text parts; flush immediately on turn end; the wait is bounded by "did a tool-call part start?". |
| Losing information users wanted (what command ran) | Keep a retrievable full step log (`/steps`); show `✓ <activity>` rows; never silently drop errors (errors always print). |
| Cancellation / steering mid-turn | On `BaseException` in the handler, flush buffered text + finalize the ledger (mirror existing `_abort_all_drainers`). |
| Thread-safety (spinner thread reads ledger while handler writes) | Lock-guarded ledger like `_activity_lock` / `_context_lock`. |
| Cannot visually verify in this environment | Each phase verified by the user in a real terminal (screenshots / recorded session); unit tests cover the state machine (defer/flush/collapse) without a TTY. |

---

## 7. Open questions (decide before/at implementation)

1. **Gating:** new `compact_steps` flag, or fold into `output_level=low`?
   (Leaning: dedicated flag, default on once proven, independent of verbosity.)
2. **Final-answer detection:** is "no tool call started after the last text
   part" a reliable end-of-turn signal across providers, or do we also key off
   the run-complete event? (Verify with pydantic-ai event order.)
3. **Ledger depth:** how many completed steps to keep visible (k = 3? 5?).
4. **Errors/approvals:** confirm these always break out of the ledger and render
   prominently (they must never be collapsed).
5. **Reasoning/thinking:** keep collapsing as today, or also surface a one-line
   "thinking…" ledger row?

---

## 8. Verification strategy

- **Unit tests** (no TTY): drive the defer/flush/collapse state machine with
  synthetic part sequences (text→tool→text→end) and assert what lands in
  scrollback vs the ledger.
- **Manual/visual** (user, real terminal): run multi-step tasks at each phase;
  confirm (a) steps don't stack, (b) final answer is intact, (c) errors/approvals
  still show, (d) cancellation is clean.
- **Regression:** `medium`/`high` output unchanged; full test suite + `ruff`
  green before each push.

---

## 9. Rollout

- Land behind `compact_steps=off`; d-foot the author's config to `on` for
  dogfooding.
- After phases 1–2 look right in a real terminal, flip the default to `on`.
- Document in README (`/set compact_steps`, `/steps`).
