# prune

A surgical, non-linear companion to `/pop`. Adds the slash command
`/prune` which opens a multi-select TUI of conversation history and
lets you cherry-pick:

1. **Whole messages** to remove (their tool calls + matching tool returns
   tag along automatically).
2. **Individual tool calls** inside a message — useful when the
   assistant made one bad call in an otherwise useful turn.
3. **Any mixture** of the two.

Where `/pop` slices a contiguous tail of messages, `/prune` is for when
you want to reach into the middle of history and yank specific things
out without touching everything around them.

## Usage

```
/prune              Open the interactive multi-select TUI
/prune preview      Open the TUI; on confirm, report the changes
                    without applying them
```

## Key bindings

| Key                    | Action                                  |
| ---------------------- | --------------------------------------- |
| `↑`/`↓` or `k`/`j`     | Move cursor (auto-scrolls list viewport) |
| `PageUp`/`PageDown`    | Jump one full page in the list          |
| `Home`/`End`           | Jump to top/bottom of the list          |
| `space`                | Toggle current row's checkbox           |
| `a`                    | Select all messages                     |
| `c`                    | Clear all selections                    |
| `shift+↑`/`shift+↓`    | Scroll detail pane line-by-line         |
| `J`/`K`                | Same as shift+↓/shift+↑ (terminal-friendly) |
| `<` / `>`              | Page-scroll the detail pane             |
| `g`                    | Jump detail pane back to top            |
| `enter`                | Confirm and apply                       |
| `q` / `Esc` / `Ctrl+C` | Cancel without changes                  |

## Pagination & layout

The list pane shows a sliding window of rows sized to the terminal —
when you scroll past the visible range, the window follows. Rows hidden
above or below are summarized with `↑ N more above` / `↓ N more below`
indicators. Selections live in independent sets and are never tied to
what's currently visible, so scrolling around (or even resizing
between sessions) preserves every checked box.

Pane widths are pinned to absolute halves of the terminal at startup
so the divider never jitters as you move the cursor through entries
with different content lengths.

## Context-window indicator

At open time the menu queries the agent for its model's context length,
estimates per-message tokens, and walks newest → oldest to figure out
which messages would fit on the next turn after accounting for system
prompt + tool-definition overhead.

A budget header sits under the title:

```
 context: 42,400/50,000 tokens (85%)   overhead: 8,000t
```

Color:
* **green** — under 70% of context used
* **yellow** — 70-90%
* **red** — over 90%

Each message row gets a small indicator after the checkbox:

| Glyph | Meaning                                              |
| ----- | ---------------------------------------------------- |
| `●`   | In the context window (would be sent next turn)      |
| `○`   | Out of the window (silently dropped — prune candidates!) |
| `·`   | Estimator unavailable                                |

Individual message rows also show their estimated token count at the
end of the line (`~120t`). The detail pane echoes the same info plus a
plain-text “in context” / “out of context window” label.

If the agent doesn't expose token-estimation helpers, the menu degrades
silently — the budget line just reads `context: unavailable` and rows
show `·` markers without token counts.

## What the display shows

Left pane: a tree of messages. Each message that has tool calls expands
inline with one indented sub-row per call. Both the message and the
tool-call rows have their own checkbox.

```
[ ]   003  asst   ⚡  "Running tests..."
        └─ [ ]  ⚡  agent_run_shell_command  command=pytest
[x]   002  user        "now make it idempotent"
[ ]   001  asst   ✎   "I've updated the auth module..."
        └─ [~]  ✎   create_file  file_path=auth.py
        └─ [~]  ✎   replace_in_file  file_path=auth.py
```

Checkbox states:

| Box   | Meaning                                                       |
| ----- | ------------------------------------------------------------- |
| `[ ]` | Not selected                                                  |
| `[x]` | Explicitly selected — will be removed                         |
| `[~]` | Implied by parent message selection — will be removed too     |

Selecting a message implicitly selects all its child tool calls
(their boxes flip to `[~]`). If you then deselect the message, the
children go back to `[ ]` — toggling individual tool calls only matters
when the parent message is *not* selected.

Right pane: details for whatever the cursor is on — full message text
and tool args, plus a warning footer if your selection touches any
side-effecting tool calls (file writes, shell commands, browser/terminal).

Footer of the left pane shows a running count: how many messages and
how many extra individual tool calls are currently flagged.

## What `/prune` actually does

After you confirm:

1. Removes every message whose history index is selected.
2. For every selected individual tool call, removes that single
   `ToolCallPart` from its parent `ModelResponse`.
3. Computes the union of all tool-call IDs that just disappeared and
   removes their matching `ToolReturnPart`s from any `ModelRequest`s
   that still survive.
4. Drops messages that ended up with zero meaningful parts.
5. Runs the same conservative tail-pruner as `/pop` to clean up any
   leftover dangling tool fragments.
6. Writes the new history back to the agent.

## What `/prune` does NOT do

- **Does not roll back tool side effects.** Files written, commands
  run, browser state changed — all still happened. Pruning erases the
  transcript, not reality. Use `git` for actual rollback.
- **Does not touch the system prompt.** Index 0 is invisible and
  un-prunable; this is a hard invariant matching `/pop`.
- **Does not protect against breaking the conversation.** If you remove
  the message that established important context, the agent will not
  magically know about it on the next turn. Prune with care.

## Detail pane: nothing is truncated

The right pane always shows the **full** content of whatever the cursor
is on — no character limits, no `…` ellipsis. That includes:

* **Full message text**, including long tool-return payloads
* **Full tool-call args**, pretty-printed as indented JSON
* All tool calls attached to a message, each with their own full args
  block

When content is taller than the pane, scroll it with `shift+↑/↓` (or
`J/K`) for line-by-line, `</>` for a page at a time, and `g` to jump
back to the top. The detail scroll position resets to the top whenever
the cursor moves to a different row, so each row's detail starts fresh.

## Source layout

```
prune/
├── __init__.py             # package marker
├── register_callbacks.py   # /prune registration + history mutation
├── prune_model.py          # dataclasses + history introspection
├── prune_render.py         # pure rendering helpers (formatted-text)
└── prune_menu.py           # prompt_toolkit menu state + keybindings
```

The dangling-fragment pruner is duplicated from `pop_command`
deliberately — these plugins are siblings with no inter-dependency. If
you fix one, fix the other.
