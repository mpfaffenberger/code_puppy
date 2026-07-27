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
**nothing** -- zero overhead, zero output, no behaviour change, no socket,
no worker thread. If they're present it opens a background reporter that
reports code-puppy's state **authoritatively**: herdr never has to infer
it from the screen.

## State is authoritative

State is a pure function of two facts the plugin observes directly:

```text
blocked   if awaiting the human
working   elif a run is in flight (run_depth > 0)
idle      otherwise
```

* **run depth** comes from `agent_run_start` / `agent_run_end`, refcounted
  so a finishing sub-agent doesn't flip the pane `idle` mid-turn (the same
  pattern the `puppy_spinner` plugin uses).
* **awaiting** comes from the `awaiting_user_input` callback, which fires
  from the single process-wide choke-point
  (`command_runner.set_awaiting_user_input`) that *every* interactive wait
  already passes through -- shell-command approval, file-permission
  approval, `ask_user_question`, and every menu/picker. One hook captures
  every block, so there is nothing left for herdr to guess.

User-initiated menus carry `notify=False`; the plugin suppresses their
`blocked` report entirely so quick pickers don't spam attention.

## Activity text is best-effort

Alongside the authoritative state, the plugin attaches a short activity
`message` (`thinking`, `running <tool>`, `awaiting input`) driven by
`pre_tool_call` / `post_tool_call`. This is decorative: it rides a separate
lane, deduplicates on the `(state, message)` pair, and can **never** delay
or override the authoritative state, the session reference, or the final
release. If a hook-blocked tool misses its completion callback, the next
run / tool / wait / turn event corrects the message; state stays correct
regardless.

## Pane metadata (model / context / tokens)

At the end of every interactive turn the plugin also reports pane
metadata via `pane.report_metadata`: the current model, context-window
fill percentage, and a compact token count. herdr stores these under the
pane with a 24h TTL (so stale numbers self-clear after an abrupt exit),
but it only *renders* them when your sidebar layout references the
matching `$name` fields. Add them to `rows_by_agent` in your herdr
config:

```toml
[ui.sidebar.agents.rows_by_agent]
codepuppy = [
  ["state_icon", "workspace", "tab"],
  ["agent", "$model"],
  ["$context", "$tokens"],
]
```

The payload uses static keys (`model`, `context`, `tokens`) with
string values and no indicator glyphs -- herdr rows already carry their
own state icons. If context usage can't be computed for a turn, no
metadata is sent and the pane keeps its last good values until the TTL
expires.

## Session reference

On each prompt the plugin reports a **stable** session reference (the
durable autosave name and pickle path) via `pane.report_agent_session` --
not the per-run `group_id`, which changes every turn. It re-reports only
when the reference actually changes (after `/clear`, `/session new`,
`/autosave_load`, `/load_context`, a quick resume, or an agent switch).
This is a stable *reference*; automatic process restoration from it is
**unverified** and not claimed here.

## Notifications are herdr's job

The plugin sends no notifications itself. herdr derives attention and
completion notifications from the agent-state transitions the plugin
reports, and herdr's own toast / sound settings control delivery. This
plugin's only job is to report accurate state.

## Release on exit

On `session_end` / `shutdown` the plugin calls `pane.release_agent` once
(idempotent, bounded) so herdr knows code-puppy has let go of the pane --
no lingering stale `working`. There is no intermediate `idle` report on
shutdown; if herdr is unavailable the release is bounded and can never
delay process exit.

## No install needed on the herdr side

Because this plugin ships with code-puppy and self-activates inside a
pane, there is nothing to run -- `herdr integration install` is **not**
required for code-puppy. Just start code-puppy inside herdr:

```bash
herdr           # start / attach herdr
code-puppy      # (or: pup) -- herdr picks up its state automatically
```

herdr also recognises the `code-puppy` / `pup` process on its own, so even
with this plugin disabled you still get basic detection. The plugin
upgrades that from screen-scraped guessing to authoritative, event-driven
state, metadata, and activity.

## Design notes

* **Never disturbs the agent.** All socket I/O happens on a daemon
  worker thread; the sync file-permission and tool hot-paths just enqueue
  and return. The tool observers always return `None`, so they can never
  block or transform a tool call.
* **Critical vs decorative.** State edges, session references, and the
  release ride a critical lane that always overtakes decorative traffic
  (activity messages, metadata). Decorative saturation can never displace
  a critical report.
* **Edge-triggered + deduped.** Only genuine `(state, message)` changes
  hit the socket.
* **Fail-soft.** A missing/closed socket, a departed herdr, an
  unresolvable source -- all are swallowed to the debug log. Reporting
  your state is never worth crashing your agent over.

## Files

| file                    | responsibility                              |
| ----------------------- | ------------------------------------------- |
| `client.py`             | herdr socket transport (JSON, worker thread)|
| `reporter.py`           | event -> state machine (refcount + dedup)   |
| `sources.py`            | fail-soft adapters (tokens / session / msg) |
| `register_callbacks.py` | callback wiring + env activation guard       |
