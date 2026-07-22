# subagent_panel

A live, two-line status block for each running sub-agent, painted just above the
bouncing puppy:

```
  INVOKE AGENT  pup-ticket-investigator  claude-4-8-opus
  (spin) 00:19  calling read_file
  INVOKE AGENT  pup-analysis-adjudicator
  (spin) 00:25  calling grep

Milo is thinking... (  o  )
```

- Line 1 is the `INVOKE AGENT` banner (same color/styling as core).
- Line 2 is a single-char animated spinner + `mm:ss` elapsed + the current
  activity, color-coded: **yellow** = calling a tool, **magenta** = thinking,
  **green** = writing the response.
- Parallel sub-agents stack, each with its own live row. By default every
  tracked agent renders as long as it fits. Users may set an optional row ceiling;
  terminal height still takes precedence so the prompt + status always keep their
  rows. If a swarm exceeds either limit, hidden rows collapse into a single
  `… +N more` summary rather than blanking the whole bar.
- **Nested sub-agents render as a true tree.** A sub-agent that itself calls
  `invoke_agent` is shown indented under its parent. Only top-level (depth-0)
  agents get the full two-line `INVOKE AGENT` banner; deeper agents collapse to
  a compact one-liner -- `<elbow> name  mm:ss  purpose  model` -- so the banner
  text + model label aren't repeated at every level:

  ```
    INVOKE AGENT  regression-runner  gpt-5.5
    (spin) 00:12  calling invoke_agent
    \u2514\u2500 pup-ticket-investigator  00:12  calling read_file  claude-4-8-opus
       \u2514\u2500 deep-helper  00:12  thinking...  gpt-5.5-mini
  ```

  The parent link is captured at emit time from an async-safe `ContextVar`
  (`_PARENT_SID`), NOT the bus's single global `_current_session_id`. The
  global is shared across all asyncio tasks, so two `invoke_agent` calls running
  concurrently would clobber it and mis-parent one root under the other (a bogus
  deep chain). A `ContextVar` is copied into each task at `create_task` time, so
  concurrent siblings each see their own correct parent -- see
  `_install_parent_tracking` (mirrors `set_session_context`) + `_install_emit_hook`.
- **On completion** the block doesn't just vanish: a persistent frozen record
  is printed to the transcript mirroring the live look, with line 2 finalized
  as a green check + `mm:ss completed`:

  ```
    INVOKE AGENT  pup-ticket-investigator  claude-4-8-opus
    (check) 00:45  completed
  ```

  (The redundant core "<check> <name> completed successfully" line is suppressed.)
  Nested agents get a compact one-liner frozen record instead of the full block:
  `<elbow> name  (check) mm:ss  completed  model`.

## How it works (3 monkeypatches, 1 callback -- no core edits)

The puppy spinner already runs a Rich `Live` that repaints ~20x/second. Rather
than spin up a second `Live` (which fights the puppy's -- the reason the
built-in `SubAgentConsoleManager` is dead code), this plugin reuses it:

1. **`ConsoleSpinner._generate_spinner_panel`** -> returns
   `Group(status block..., "", puppy)` so the existing loop renders everything.
2. **`RichConsoleRenderer._render_subagent_invocation`** -> *captures* the exact
   metadata (name / session_type / model / **session_id**) and *suppresses* the
   permanent banner. The live block now owns the banner, so there's no
   duplicate, and registration is exact even for parallel sub-agents (no
   session-id guessing).
3. **`RichConsoleRenderer._do_render`** -> when the `SubAgentResponseMessage`
   arrives (core skips it), print the persistent frozen two-line record + pop
   the live row, and suppress the redundant completion-text line.

Status text is fed by the **`stream_event`** callback, keyed by `session_id`.
`record_event` is *update-only*: an event for an unregistered session is ignored,
which cleanly filters out the main agent's own stream events. `coalesce_patch.py`
batches sub-agent stream-event callbacks (~50ms) so parallel token streams do
not starve the steer overlay's event-loop continuations.

## Config

Runtime controls:

```text
/set subagent_panel off
/set subagent_panel on
/set subagent_panel_max_rows 8
/set subagent_panel_max_rows 0  # automatic; show every row that fits
```

The row ceiling takes effect immediately. It never overrides the terminal-height
safety clamp.

Environment startup hard-disable:

| Var | Default | Meaning |
|-----|---------|---------|
| DISABLE_SUBAGENT_PANEL | unset | Set 1 to skip registration entirely |
| SUBAGENT_PANEL | 1 | Set 0 to skip registration entirely |
| SUBAGENT_PANEL_IDLE_S | 600 | Prune after this many idle seconds (safety net) |

## Notes

- Installs wrappers at **startup**, but `/set subagent_panel off` makes them pass through live.
- The permanent invocation banner (with Prompt/Session) is intentionally
  replaced by the transient live block; on completion a compact frozen
  two-line record (banner + green check) is left in the transcript.
