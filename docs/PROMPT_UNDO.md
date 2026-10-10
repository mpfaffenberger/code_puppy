# Undo / redo in the prompt

The interactive prompt keeps a multi-step undo history for the text you are
composing. Fat-fingered a `Ctrl+U` on a long prompt? Press `Ctrl+Z`.

| Key | Action | Works out of the box? |
|-----|--------|-----------------------|
| `Ctrl+Z` | Undo | Yes: macOS, Linux, Windows |
| `Ctrl+Y` | Redo | Yes: macOS, Linux, Windows |
| `Cmd+Z` | Undo | Only if the terminal reports it (see below) |
| `Cmd+Shift+Z` | Redo | Only if the terminal reports it (see below) |
| `Ctrl+Shift+Z` | Redo | Only with CSI-u; legacy terminals send plain `Ctrl+Z` (undo) |

## What gets recorded

Every change to the buffer is undoable: typing, Backspace, Delete,
`Ctrl+W` / `Alt+Backspace` (word delete), `Ctrl+K` (kill to end of line),
`Ctrl+U` (clear the buffer), `Ctrl+C` clearing a composed prompt, pastes,
Tab completions, history recall (`Up` / `Ctrl+R`), and the `Ctrl+X Ctrl+E`
`$EDITOR` round-trip.

Steps are grouped so undo feels natural:

- Typing is grouped per word: `hello world` undoes to `hello ` and then to
  empty.
- A run of Backspaces (or Deletes) is one step.
- Kills, clears, pastes, completions and recalls are always their own step.
- Moving the cursor ends the current group.
- Any new edit drops the redo history.
- The history holds the last 100 steps and is cleared when you submit.

The editor has no text selection, so there is no "cut" or "paste over a
selection". The kill keys (`Ctrl+U` / `Ctrl+K` / `Ctrl+W`) are the cut
equivalents, and they are undoable like everything else.

## Ctrl+Z no longer suspends Code Puppy

On macOS and Linux, `Ctrl+Z` normally sends `SIGTSTP` and suspends the
process. While the Code Puppy prompt owns the terminal, it turns off the
terminal's suspend character (`VSUSP`) so `Ctrl+Z` reaches the prompt as a
key. On macOS/BSD it also turns off the delayed-suspend character (`VDSUSP`,
which is `Ctrl+Y`). Both settings come back when the prompt gives up the
terminal (for example while a full-screen menu is open, or when Code Puppy
exits). `Ctrl+\` (`SIGQUIT`) is unchanged. If you
really want to suspend Code Puppy, run `kill -TSTP <pid>` from another shell.

On Windows, the prompt reads raw console input, so `Ctrl+Z` comes in as a
key event. It never inserts `^Z` and never means end-of-file.

## Getting Cmd+Z to the prompt (macOS)

By default, terminals send nothing to the program for `Cmd`+letter. Either
the terminal handles the shortcut itself, or it has no legacy byte encoding
for it. Code Puppy recognizes `Cmd` when the terminal reports it as the
**super** modifier in a CSI-u (kitty keyboard protocol / fixterms) sequence:

| Keys | Sequence to send |
|------|------------------|
| `Cmd+Z` | `ESC [ 122 ; 9 u` |
| `Cmd+Shift+Z` | `ESC [ 122 ; 10 u` |
| `Ctrl+Shift+Z` | `ESC [ 122 ; 6 u` |

It also understands `Ctrl+Z` / `Ctrl+Y` / `Cmd+Y` as CSI-u, the
modifyOtherKeys form `ESC [ 27 ; <mods> ; <code> ~`, uppercase key codes
(`90`, `89`), and kitty's `code;mods:event` form (key releases are ignored).

Code Puppy does **not** turn on the kitty keyboard protocol itself. Doing so
would re-encode `Esc`, `Enter`, `Backspace` and `Alt` combinations for the
whole session. Instead, map the keys you want in your terminal:

**Ghostty** (`~/.config/ghostty/config`)

```
keybind = super+z=csi:122;9u
keybind = super+shift+z=csi:122;10u
```

**kitty** (`kitty.conf`)

```
map cmd+z       send_text all \x1b[122;9u
map cmd+shift+z send_text all \x1b[122;10u
```

**WezTerm** (`wezterm.lua`)

```lua
config.keys = {
  { key = 'z', mods = 'CMD', action = wezterm.action.SendString '\x1b[122;9u' },
  { key = 'z', mods = 'CMD|SHIFT', action = wezterm.action.SendString '\x1b[122;10u' },
}
```

**iTerm2**: Settings, then Profiles, then Keys, then Key Mappings, then `+`.
Record `Cmd+Z` and choose *Send Escape Sequence* with `[122;9u`. Do the same
for `Cmd+Shift+Z` with `[122;10u`. If iTerm2's own Edit menu still captures
`Cmd+Z`, rebind that menu item in macOS System Settings, under Keyboard, then
Keyboard Shortcuts, then App Shortcuts.

**Alacritty** (`alacritty.toml`)

```toml
[keyboard]
bindings = [
  { key = "Z", mods = "Command", chars = "\u001b[122;9u" },
  { key = "Z", mods = "Command|Shift", chars = "\u001b[122;10u" },
]
```

**VS Code / Cursor integrated terminal** (`keybindings.json`)

```json
{ "key": "cmd+z", "command": "workbench.action.terminal.sendSequence",
  "args": { "text": "\u001b[122;9u" }, "when": "terminalFocus" }
```

**Terminal.app** can't send `Cmd` combinations to programs. Use `Ctrl+Z`.

Shortcut: any terminal that can map a key to raw bytes can also map
`Cmd+Z` to hex `0x1a` (that is, `Ctrl+Z`) and `Cmd+Shift+Z` to `0x19`
(`Ctrl+Y`).
