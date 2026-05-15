# Agent Steering 🎯

Pause a running Code Puppy agent and inject a steering message without
losing the context it's accumulated so far.

## How it works

1. While the agent is running, press the **pause key** (default: `Ctrl+T`).
2. The spinner hides and a tiny raw-terminal, single-line prompt opens:

   ```text
   steer [now]> change it to java
   ```

3. Press `Tab` to toggle delivery mode:

   ```text
   steer [queue]>
   ```

   - **now** *(default)*: agent sees the message at its very next model
     call, mid-turn if necessary. Use this to interrupt/redirect ASAP.
   - **queue**: agent finishes its current turn first, then sees the
     message as a fresh user turn. Use this for additive follow-up work.

4. Type a single-line message. Submit with `Enter`, edit with Backspace,
   toggle mode with `Tab`, or cancel with `Esc`, `Ctrl+C`, or `Ctrl+D`.
5. On submit, the message is delivered per the selected mode and the
   agent resumes. On cancel, the agent resumes with no steering message.

## Configuration

Change the pause key via the config file or `/set`:

```text
/set pause_agent_key ctrl+p
```

Valid options: `ctrl+a`, `ctrl+b`, `ctrl+e`, `ctrl+f`, `ctrl+g`,
`ctrl+k`, `ctrl+n`, `ctrl+o`, `ctrl+p`, `ctrl+r`, `ctrl+t` (default),
`ctrl+u`, `ctrl+v`, `ctrl+w`, `ctrl+x`, `ctrl+y`.

> **tmux users:** `ctrl+b` (default prefix) and `ctrl+a` (common remap)
> may be swallowed by tmux before reaching Code Puppy. Pick a key your
> tmux doesn't capture — e.g. `ctrl+o` or `ctrl+g`.

Tune the safety auto-resume timeout (default 45s):

```text
/set max_pause_seconds 60
```

## Why a plugin?

Per `AGENTS.md`, all new behaviour lives in plugins so core stays lean.
The pause/steer primitive itself (the `PauseController`, the bus commands,
and the runtime gates) is core; the Ctrl+T user experience lives here.
