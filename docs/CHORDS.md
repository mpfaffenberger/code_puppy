# Ctrl+X Chords

> Full reference. The must-follow chord rules are summarized in `AGENTS.md`.

`Ctrl+X` is a **chord prefix** (readline-style), never a standalone hotkey. The
line editor arms a pending state on `Ctrl+X`, paints a hint of the currently
registered bindings on the bottom bar, and resolves the NEXT key against the
chord registry in `code_puppy/messaging/chords.py`. `Esc` (or any unbound key)
cancels the chord; unbound keys are then processed normally.

| Chord | Action | Registered by | Active when |
|-------|--------|---------------|-------------|
| `Ctrl+X Ctrl+E` | Edit the prompt buffer in `$VISUAL`/`$EDITOR` | `run_ui` | Always (UI lifetime) |
| `Ctrl+X Ctrl+X` | Kill all running shell commands | `command_runner` | While shell commands run |
| `Ctrl+X Ctrl+B` | Background all running shell commands | `command_runner` | While shell commands run |
| `Ctrl+X Ctrl+S` | Toggle speculative execution (`enable_speculative_code_mode`), rebuilds the current agent for the next turn | `run_ui` | Always (UI lifetime) |

**Design notes:**

- **No modes.** This replaced a modal design where a bare `Ctrl+X` meant
  "kill shells if a handler happened to be armed, editor chord otherwise" --
  the arm/disarm lifecycle raced against keystrokes. Now `Ctrl+X` always
  flows into the editor; the registry decides what the follow-up key does.
- **Backgrounding is mid-flight detach.** `Ctrl+X Ctrl+B` makes every
  streaming shell tool call return immediately with `background=True`,
  `log_file`, and `pid`; the process keeps running and its remaining output
  diverts to the log file (readers keep the pipes drained).
- **Headless fallback.** With no line editor installed (piped stdin, embeds),
  a bare `Ctrl+X` keeps its historical kill-all-shells meaning via the
  listener's spawn-time `on_escape` callback.

**Plugins can register their own chords:**

```python
from code_puppy.messaging.chords import register_chord, unregister_chord

register_chord("\x14", my_callback, "Ctrl+T do the thing")  # Ctrl+X Ctrl+T
```

Rules for chord callbacks: they run on the key-listener thread, so **never
block** (hop to the asyncio loop's executor like the `$EDITOR` handler in
`messaging/external_editor.py`); never raise (failures are swallowed and
logged); register only while the binding is meaningful so the armed-chord
hint stays honest. Keys are single raw control characters -- prefer
`Ctrl+<letter>` bytes; digits and F-keys are deliberately unsupported.
