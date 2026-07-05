# puppy_spinner

The bouncing-puppy spinner on the bottom bar's status-prefix slot —
now with customizable styles.

## `/spinner` command

| Command | What it does |
|---|---|
| `/spinner` | Interactive picker with a **live animated preview** |
| `/spinner <name> [seconds]` | Apply a spinner by name, optionally at a custom speed |
| `/spinner init` | Write a starter `spinners.json` for custom spinners |

Edits to `spinners.json` are picked up automatically (the file's mtime
is watched) — the currently animating spinner refreshes on its own,
and the picker reloads its list live *even while it's open*. No reload
step.

Picker navigation matches the `/plugins` menu: `j`/`k` + up/down move the
selection, `PgUp`/`PgDn` page through the list, `g`/`G` (or `Home`/`End`)
jump to first/last, `Enter` applies, `q`/`Esc`/`Ctrl-C` cancels.
`-`/`+` (or `←`/`→`) adjust the highlighted spinner's speed live in the
preview; `Enter` saves the speed you dialed straight into
`spinners.json` as that spinner's speed — same place you'd edit by
hand, and it sticks until you change it again. `i` writes the starter
`spinners.json` right from the menu (same as `/spinner init`).

The choice persists in `puppy.cfg` (`spinner_style` key) and takes
effect on the very next animation frame — no restart, even mid-run.

## Builtin spinners

Every builtin runs at 0.2s per frame by default — per-spinner tuning is
what the picker's speed keys and `spinners.json` tweaks are for. The
one exception: the classic `puppy` trots at 0.06s out of the box.

The puppy pack: `puppy` (default), `bone`, `zoomies`, `paws`, `dots`.

Plus a cli-spinners-style pack: `aesthetic`, `binary`, `bouncingBall`,
`bouncingBar`, `chevrons`, `dots8Bit`, `dotsCircle`, `dotsWide`,
`fistBump`, `growHorizontal`, `growVertical`, `noise`, `pong`, `sand`.

The picker shows everything alphabetically.

Frames for that pack live in `builtin_frames.py` — a generated,
data-only module (non-ASCII is escape-spelled for the repo emoji
filter); edit descriptions there, not frame art.

## Custom spinners

Drop a `spinners.json` next to `puppy.cfg` (usually
`~/.code_puppy/spinners.json` — the picker's preview pane shows the
exact path):

```json
{
  "sniffer": {
    "frames": ["( .    ) ", "(  .   ) ", "(   .  ) ", "(    . ) "],
    "interval": 0.1,
    "description": "a very minimalist puppy"
  }
}
```

### Re-speeding a builtin

An entry that names a builtin and **omits `frames`** is a *tweak*: it
inherits the builtin's frames and just overrides `interval` and/or
`description` — no copying frame art:

```json
{
  "zoomies": { "interval": 0.1 }
}
```

Speed has one rule: a spinner runs at its `spinners.json` value when
present, else the builtin default (0.2s). The picker's speed keys and
`/spinner <name> <seconds>` don't add another layer — they just save
that value into the file for you.

Rules:

- `frames`: non-empty list of non-empty strings (padded to equal width
  automatically; capped at 40 chars per frame). Omit it only when the
  entry name matches a builtin (that's a tweak, see above).
- `interval`: seconds per frame, clamped to `0.02`–`1.0` (default `0.2`).
- `description`: optional, shown in the picker's preview pane.
- **User entries override builtins** on name collision — yes, you can
  redefine `puppy`. We're not mad, just disappointed.
- A broken file never crashes anything: bad entries are skipped with a
  log warning, and an unknown configured name falls back to the classic
  kennel bounce.
