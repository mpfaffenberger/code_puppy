---
name: status
description: Display the pipeline stage and status of all task files
ui-mode: flux-status
exec: {python} {script:flux_status.py}
---

# /flux/status — PIPELINE STATUS

Show the current pipeline stage and status of every active task file in `todo/`.

> **Note:** This command is handled natively by the bundled flux_status.py
> script (resolved under code-puppy's config dir). The markdown below is
> reference documentation only — it is not executed by the AI.

## DATA SOURCE

Reads `~/.flux/<flattened-dir>/todo/*.md` only. `<flattened-dir>` is derived from
the current working directory at the time `/flux/status` is invoked — every
non-alphanumeric character in the absolute path is replaced with a hyphen.
Completed tasks moved to `done/` by `/flux/qa` are intentionally excluded.

## DISPLAY

Renders a floating overlay panel (upper-right corner) with:

- One row per task file: filename | stage | status
- Summary footer with counts per status value
- ESC to close

### Example output

```
𝕱 PIPELINE STATUS        (Ctrl+F to close)
══════════════════════════════════════════════
 ─────────────────────────────────────────────
 FIX_COMMAND_HINTS.md  exec   🔄 in-progress
 DARK_MODE.md          qa     🔁 needs-rework
═══════════════════════════════════════════════
```

If there are no task files in `todo/`, the panel shows:

```
(no todos)
```
