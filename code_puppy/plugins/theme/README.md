# theme — `/theme` for Mist

A friendlier `/theme` command with an **interactive picker**, **live preview**,
and **four layers of theming** — banner headers, body text, inline markup,
AND the whole terminal window background/foreground/ANSI palette via OSC
escape sequences (mure-style).

## What you get

```
/theme
```
Launches a split-panel TUI with 14 themes (5 neon/dark themes, 7 palette-first/light themes, surprise, reset).


## What gets themed

| Level | Surface | Themed? |
|-------|---------|---------|
| 0 | Banner headers (`[ THINKING ]`, etc.) | ✅ |
| 1 | Body text (`emit_info`/`warning`/`success`/`error`/`debug` + diffs) | ✅ |
| 2 | Inline Rich markup (`[bold cyan]`, `[dim cyan]`, `[magenta]`...) | ✅ |
| 3 | **Entire terminal window** (bg/fg/16-color ANSI palette via OSC 10/11/4) | ✅ |

**Semantic colors are preserved** at Level 2 (red errors stay angry, yellow warnings warn). Level 3 OSC remap is broader — it changes how *your terminal itself* interprets every ANSI color, so e.g. an `ls` ran after `/theme tokyo-night` will also look Tokyo Night. Pure terminal-level magic.

Themes persist to your Mist config and survive restarts. The OSC palette auto-resets on Mist exit (via `atexit`) so you never get a stuck-pink terminal.

## Bundled themes

| # | Theme | Vibe |
|---|-------|------|
| 1 | 🌊 Ocean | cool blues, cyans & teals |
| 2 | 🌲 Forest | earthy greens & olives |
| 3 | 🌅 Sunset | warm reds, oranges & gold |
| 4 | 🪩 Vaporwave | neon pinks & purples |
| 5 | 🫧 Bubblegum Pink | sweet pinks, candy neon & glow |
| 6 | 🐱 Catppuccin Mocha | soothing pastel dark (mure default) |
| 7 | ☕ Catppuccin Latte | soothing pastel light |
| 8 | 🌃 Tokyo Night | neon-on-navy night |
| 9 | 🌑 Deep Black | inky noir with subtle neon edge |
| 10 | ☀️ Solarized Light | classic warm beige with calm accents |
| 11 | 📄 GitHub Light | crisp white, familiar code colors |
| 12 | 🌸 Rose Pine Dawn | soft pastel rose light |
| 13 | 🎲 Surprise Me | a fresh random remix every time |
| 14 | 🔄 Restore Defaults | back to Mist + terminal factory |

## Power-user shortcuts

```
/theme 5            apply theme #5 (Bubblegum Pink)
/theme bubblegum    apply by alias (also: pink, mocha, latte, tokyo,
                    solarized, github, rose-pine)
/theme tokyo-night  apply by canonical name
/theme surprise     re-roll a random palette
/theme default      restore Mist + terminal factory colors
/theme reset        alias of /theme default
/theme show         dump current banner + content style mappings
```

## Architecture (Zen-compliant, one job per file)

| File | Responsibility |
|------|----------------|
| `themes.py` | Theme catalog + banner/content/remap/palette construction |
| `bundled_palettes.py` | Hex palette data (Catppuccin, Tokyo Night, Deep Black, +5 originals) |
| `content_styles.py` | Mutates `RichConsoleRenderer` style maps (Level 1) |
| `rich_themes.py` | Monkey-patches `Console.get_style()` for inline remap (Level 2) |
| `osc_palette.py` | OSC escape sequences for terminal-wide bg/fg/ANSI palette (Level 3) |
| `picker.py` | prompt_toolkit split-panel TUI with live preview |
| `register_callbacks.py` | `/theme` command handler, glue only |
| `__init__.py` | Re-applies persisted (L1 + L2 + L3) on plugin load |

## How each level works (the spicy bits)

**Level 1** — mutates `code_puppy.messaging.rich_renderer.DEFAULT_STYLES` and walks live `RichConsoleRenderer._styles` via `gc.get_objects()`.

**Level 2** — Rich's stock `Theme` only intercepts named styles, not base colors inside `[bold cyan]`. So we monkey-patch `Console.get_style()` on every live `Console`: every resolved `Style` flows throughd if `.color`/`.bgcolor` matches our remap, we swap. Tracked in a `WeakKeyDictionary` for clean swap-without-leak.

**Level 3** — fires xterm OSC sequences (`\\033]10;#fg\\007`, `\\033]11;#bg\\007`, `\\033]4;N;#hex\\007`) which modern terminals honor terminal-wide. Auto-resets on exit via `atexit`. Persists across restarts via JSON in `mist.cfg`. Supported in iTerm2, Terminal.app, Alacritty, kitty, ode, GNOME Terminal, Windows Terminal. Unsupported terminals silently ignore.

Plays nice with `/colors` — same color pool, same config keys for banners.
