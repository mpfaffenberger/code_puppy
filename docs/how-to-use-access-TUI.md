# How to Access & Drive the Mist TUI (headless verification)

Mist is an interactive terminal UI (Rich `Live`, streaming text, spinner). An
agent/automation cannot "see" it the way a human does — but it **can** drive the
real TUI headlessly and inspect exactly what renders, using a pseudo-terminal.

This is how to verify visual behavior (spinner animation, streaming, the status
footer, escape-sequence corruption) **without relying on user screenshots**.

---

## TL;DR

```bash
SESSION=mt
tmux kill-session -t $SESSION 2>/dev/null
tmux new-session -d -s $SESSION -x 170 -y 45        # detached, fixed size
tmux send-keys -t $SESSION '.venv-user/bin/mist' Enter
# ...wait for boot (DBOS init etc.)...
tmux capture-pane -t $SESSION -p                    # rendered screen (what the user sees)
tmux capture-pane -t $SESSION -pe                   # + raw escape codes (catch corruption)
tmux send-keys -t $SESSION '/help' Enter            # drive it
tmux kill-session -t $SESSION                       # always clean up
```

---

## Why a PTY is required

Mist needs a real TTY: `prompt_toolkit` for input, Rich `Live` for the spinner,
and ANSI colors. Piping (`mist < /dev/null`) makes it EOF out immediately
(`Input is not a terminal`). A **pseudo-terminal** (tmux pane, or Python `pty`)
gives it a real TTY so it runs normally, while we capture the output
programmatically.

Available tools on this machine (all work):
- `tmux` — **preferred**; gives the *rendered* screen grid.
- `script`, `expect` — alternatives.
- Python `pty` — gives the *raw* byte stream (every escape sequence).

---

## Method A — tmux (preferred: see the rendered screen)

`tmux capture-pane` returns the terminal grid **after** escape processing —
i.e. exactly what a human would see. Best for layout/spinner/footer checks.

### 1. Boot in a detached session
```bash
tmux kill-session -t mt 2>/dev/null
tmux new-session -d -s mt -x 170 -y 45     # -x cols, -y rows (fixed = stable captures)
tmux send-keys -t mt 'cd /Users/bajajra/git/mist && .venv-user/bin/mist' Enter
```

### 2. Wait for boot, then capture
Boot does a version check + DBOS init (~10-15s). Don't use the foreground
`sleep` command (blocked); orchestrate the wait inside a small script:

```bash
.venv/bin/python - <<'PY'
import subprocess, time
def tmux(*a): return subprocess.run(["tmux", *a], capture_output=True, text=True)
# poll the pane until the input prompt appears (max ~25s)
ready = False
for _ in range(25):
    pane = tmux("capture-pane", "-t", "mt", "-p").stdout
    if ">>>" in pane:           # the prompt line
        ready = True
        break
    time.sleep(1)
print("ready" if ready else "timed out")
print("\n".join(pane.splitlines()[-20:]))
PY
```

### 3. Two capture modes
```bash
tmux capture-pane -t mt -p     # rendered text only — "what the user sees"
tmux capture-pane -t mt -pe    # include escape sequences — catch corruption
```
- Use `-p` to verify the spinner glyph, the prompt, the status footer, layout.
- Use `-pe` to catch escape-corruption regressions (e.g. raw `]2;…` OSC text
  leaking into scrollback, ANSI not being interpreted, etc.).

### 4. Drive it (send keystrokes)
```bash
tmux send-keys -t mt '/help' Enter                  # a command (no model call)
tmux send-keys -t mt 'list the files here' Enter    # a real task (HITS THE MODEL)
tmux send-keys -t mt C-c                             # Ctrl+C (cancel)
tmux send-keys -t mt '/exit' Enter                   # quit cleanly
```

### 5. Capturing animation (spinner / streaming over time)
A single capture is a snapshot. To verify the spinner *animates* or text
*streams*, capture repeatedly and diff:
```bash
.venv/bin/python - <<'PY'
import subprocess, time
def cap(): return subprocess.run(
    ["tmux","capture-pane","-t","mt","-p"], capture_output=True, text=True).stdout
subprocess.run(["tmux","send-keys","-t","mt","list files then summarize","Enter"])
frames = []
for _ in range(8):
    frames.append(cap().splitlines()[-3:])   # bottom rows = spinner/status
    time.sleep(0.6)
for i, f in enumerate(frames):
    print(f"--- t={i*0.6:.1f}s ---"); print("\n".join(f))
PY
```
Different spinner glyphs across frames ⇒ it's animating. Identical ⇒ stalled.

### 6. Always clean up
```bash
tmux kill-session -t mt 2>/dev/null
```

---

## Method B — Python `pty` (see the raw byte stream)

When you need every escape sequence exactly as emitted (e.g. to confirm an OSC
title write is well-formed, or to see what termflow streams), drive Mist through
a raw pty and read the bytes:

```bash
.venv/bin/python - <<'PY'
import pty, os, time, select
pid, fd = pty.fork()
if pid == 0:                       # child
    os.execv(".venv-user/bin/mist", [".venv-user/bin/mist"])
else:                              # parent: read raw output
    buf = b""
    deadline = time.time() + 15
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.3)
        if r:
            try: buf += os.read(fd, 4096)
            except OSError: break
    os.write(fd, b"/exit\n")        # send input as bytes
    print(repr(buf[-1500:]))        # repr() shows \x1b escapes literally
PY
```
`repr()` makes escape bytes (`\x1b]2;…`, `\x1b[38;2;…m`) visible, so malformed
or split sequences are obvious.

---

## What this is good for

| Goal | Method | What to look at |
|---|---|---|
| Spinner glyph / style correct | tmux `-p` | bottom rows of the pane |
| Spinner actually animating | tmux loop (§5) | glyph changes across frames |
| Streamed text not duplicated | tmux `-p` | the AGENT RESPONSE body |
| Escape-code corruption (`]2;`, stray ANSI) | tmux `-pe` / pty `repr()` | raw sequences |
| Status footer pins to bottom | tmux `-p` | last N rows stay put while text scrolls |
| Theme colors / truecolor | tmux `-pe` | `\x1b[38;2;r;g;bm` truecolor codes present |
| Boot errors / missing model/key | tmux `-p` | the startup output |

## What it can't do
- It can't judge *aesthetics* (does it "look premium") — only structure/colors.
- Sending a real task prompt triggers a live **model API call** (cost + latency).
  Prefer `/help`, `/agent`, `/model`, or short prompts for layout checks; reserve
  full prompts for end-to-end verification.

---

## Gotchas
- **Fixed pane size** (`-x`/`-y`): keep it constant so captures are comparable.
- **Foreground `sleep` is blocked** in this harness — do waits inside a Python
  script (`time.sleep`) or poll the pane in a loop, not `sleep 10` on the CLI.
- **Always `kill-session`** when done; a stray detached session keeps a `mist`
  (and its DBOS/MCP subprocesses) alive in the background.
- Use **`.venv-user/bin/mist`** (the non-editable user install) to test what a
  real user sees, or **`.venv/bin/mist`** (editable) to test live source changes.
- DBOS/durable mode adds boot time and a sqlite store; `/dbos off` if you want a
  faster, simpler boot for pure UI checks.
