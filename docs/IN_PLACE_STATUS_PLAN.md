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

### Decision
**Go with Option A.** It delivers the requested behavior, reuses the spinner
`Live` region, and is the most incremental / least risky. Options B/C can be
revisited later if we want a fully pinned footer.

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
