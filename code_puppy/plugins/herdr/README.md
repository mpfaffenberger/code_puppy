# herdr integration

Makes code-puppy a first-class citizen in
[**herdr**](https://herdr.dev), a terminal workspace manager for coding
agents. When you run several agents at once, herdr's sidebar rolls each
one up to a single glanceable state -- who's **working**, who's
**blocked** waiting on you, and who's **done** -- so you always know
which pane needs attention.

This plugin teaches code-puppy to report that state authoritatively.

## What it does

herdr injects three environment variables into every pane it owns:

| variable            | meaning                                   |
| ------------------- | ----------------------------------------- |
| `HERDR_ENV=1`       | this shell is running inside a herdr pane |
| `HERDR_SOCKET_PATH` | herdr's local control socket              |
| `HERDR_PANE_ID`     | the pane this process owns (e.g. `w1:p1`) |

On startup the plugin checks for those. If they're absent it does
**nothing** -- zero overhead, zero output, no behaviour change. If
they're present it opens a background reporter that maps code-puppy's
lifecycle callbacks onto herdr's three semantic states:

| code-puppy event                                | herdr state |
| ----------------------------------------------- | ----------- |
| `agent_run_start`, `user_prompt_submit`         | `working`   |
| `pre_tool_call` (most tools), `post_tool_call`  | `working`   |
| `ask_user_question`, file-permission prompts    | `blocked`   |
| `interactive_turn_end`, `agent_run_cancel`      | `idle`      |
| `startup`, `session_end`, `shutdown`            | `idle`      |

Sub-agent runs fire the same start/end hooks as the root run, so the
reporter refcounts active runs and only falls `idle` when the whole turn
hands control back to you (mirroring the `puppy_spinner` plugin).

## No install needed on the herdr side

Because this plugin ships with code-puppy and self-activates inside a
pane, there is nothing to run -- `herdr integration install` is **not**
required for code-puppy. Just start code-puppy inside herdr:

```bash
herdr           # start / attach herdr
code-puppy      # (or: pup) -- herdr picks up its state automatically
```

herdr also recognises the `code-puppy` / `pup` process on its own and
reads the on-screen approval prompts, so even with this plugin disabled
you still get detection. The plugin upgrades that from screen-scraped
guessing to authoritative, event-driven state.

## Blocked detection is shared with herdr

Not every interactive prompt in code-puppy flows through a callback
(shell-command approval, for instance, prompts from inside the tool).
The plugin reports the prompts it *can* see, and herdr's screen manifest
independently detects any visible approval UI and overrides a stale
`working` -- which is exactly why this plugin does **not** claim herdr
"full lifecycle authority". Belt and suspenders.

## Design notes

* **Never disturbs the agent.** All socket I/O happens on a daemon
  worker thread; the sync file-permission hot-path just enqueues and
  returns. The permission observer always returns `None`, so it can
  never accidentally veto a file operation.
* **Edge-triggered + deduped.** Only state *changes* hit the socket.
* **Fail-soft.** A missing/closed socket, a departed herdr, a full
  queue -- all are swallowed to the debug log. Reporting your state is
  never worth crashing your agent over.

## Files

| file                    | responsibility                              |
| ----------------------- | ------------------------------------------- |
| `client.py`             | herdr socket transport (JSON, worker thread)|
| `reporter.py`           | event -> state machine (refcount + dedup)   |
| `register_callbacks.py` | callback wiring + env activation guard       |
