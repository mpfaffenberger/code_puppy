# Manual test — sub-agent panel overflow clamp (Gap #6)

Repeatable manual checks for the sub-agent live panel in **both** UIs. Covers
the overflow-clamp fix (`clamp_panel_lines` shared by classic `BarPainterMixin`
and the TUI's `_apply_subagent_panel`). See `docs/TUI_PARITY_GAPS.md` Gap #6.

## Key mechanic

The panel shows **one row per concurrently-active sub-agent**. Sub-agents run
shell silently (no confirmation prompt), so a `sleep` keeps them alive long
enough to overlap on screen. BOTH modes now use a **terminal-height-relative**
budget — the panel fills the available space and folds the remainder into a
`… +N more` summary:

| Mode | Budget | Overflow trigger |
|---|---|---|
| `--tui` | `terminal_height - _SUBAGENT_PANEL_RESERVE` (floor `_SUBAGENT_PANEL_MIN_ROWS`) -> shows what fits + `… +N more` | more agents than fit, or a short window |
| `--interactive` | terminal-height-relative (`BarPainterMixin._panel_row_budget`) -> shows what fits + `… +N more` | more agents than fit, or a short window |

Because the budget scales with height, a **tall** window may show ALL your
agents (no summary); to force overflow, use a big swarm (Prompt C) or a short
window (Prompt B). Overflow math: with a budget of B rows, N concurrent agents
=> summary reads `… +{N-(B-1)} more`.

The magic words in every prompt: **"in parallel, in a single batch, don't wait
between them"** — otherwise the agent runs them one-at-a-time and you only ever
see one row.

## Launch

```bash
code-puppy --tui           # or -t
code-puppy --interactive   # or -i
```

---

## Prompt A — panel populates, NO overflow (baseline)

Spawns 4 -> under budget in both modes. Expect all 4 rows, spinner + mm:ss
animating, **no `… more`**, and the panel vanishing when they finish.

```
Using the invoke_agent tool, launch 4 code-puppy sub-agents IN PARALLEL — fire them all in a single batch, do not wait between them. Give each one this exact task: run the shell command `sleep 25` and then reply with the word done. I want all 4 running at the same time.
```

**Pass:** 4 rows, no `more`, panel disappears when done.

---

## Prompt B — force overflow (the actual fix under test)

Spawns 8. To *guarantee* overflow in either mode, shrink the terminal window
to ~10 rows tall first (otherwise a tall window may just show all 8).

- **Both modes (short window):** shows as many rows as fit + `… +N more`, with
  the prompt/status staying put.

```
Using the invoke_agent tool, launch 8 code-puppy sub-agents IN PARALLEL in one single batch — do not wait between invocations. Each sub-agent's task: run `sleep 30`, then reply done. All 8 must run concurrently.
```

**Pass:** panel never grows past the budget, the `… +N more` summary appears,
and the input prompt / status line stay visible (not shoved off screen).

**Fail (old bug):** TUI silently shows ~5 agents with no `more` indicator; the
rest just vanish.

---

## Prompt C — big-swarm stress

Spawns 20. Confirms the layout is bulletproof under a huge fan-out (the case
that used to trip the classic dormancy guard / blank the bar).

```
Using the invoke_agent tool, launch 20 code-puppy sub-agents IN PARALLEL in a single batch, no waiting between them. Each one: run `sleep 40`, then reply done. I need all 20 alive at once so I can watch the panel.
```

**Pass (both modes):** panel stays clamped, `… +N more` shows a big number,
prompt+status never disappear, and the panel collapses cleanly when the swarm
finishes.

---

## Things to eyeball while testing

- **Overflow math:** budget B rows => N agents show `… +{N-(B-1)} more`.
- **Height-scaling:** make the window taller and the panel shows MORE agents
  (that's the whole point — it fills the space like classic, not a fixed cap).
- **Live churn:** the mm:ss clock + braille spinner keep animating even while
  agents just sleep (the 4Hz ticker).
- **Hide-on-empty:** once every sub-agent reports done, the panel collapses to
  nothing in both modes.
- **Classic tip:** if you can't get overflow, drag the terminal window shorter
  before running Prompt B — the classic budget scales with height, so a tall
  window happily shows all 8.
