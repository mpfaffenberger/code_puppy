"""Bundled terminal palettes for OSC-level theming.

Each palette ships:
    bg   = #rrggbb default background
    fg   = #rrggbb default foreground
    ansi = list of 16 #rrggbb hex strings (ANSI slots 0-15)

The Catppuccin / Tokyo Night palettes are the canonical
upstream specs (same ones mure ships). The original theme
palettes (ocean/forest/sunset/vaporwave) are coherent extensions
of their existing Rich color schemes.
"""

from __future__ import annotations

# --- Mure-port bundled palettes ---------------------------------------------

CATPPUCCIN_MOCHA = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "ansi": [
        "#45475a",
        "#f38ba8",
        "#a6e3a1",
        "#f9e2af",
        "#89b4fa",
        "#f5c2e7",
        "#94e2d5",
        "#bac2de",
        "#585b70",
        "#f38ba8",
        "#a6e3a1",
        "#f9e2af",
        "#89b4fa",
        "#f5c2e7",
        "#94e2d5",
        "#a6adc8",
    ],
}

CATPPUCCIN_LATTE = {
    "bg": "#eff1f5",
    "fg": "#4c4f69",
    "ansi": [
        "#4c4f69",
        "#d20f39",
        "#40a02b",
        "#df8e1d",
        "#1e66f5",
        "#8839ef",
        "#179299",
        "#acb0be",
        "#5c5f77",
        "#e64553",
        "#a6d189",
        "#fe640b",
        "#7287fd",
        "#ea76cb",
        "#94e2d5",
        "#bcc0cc",
    ],
}

TOKYO_NIGHT = {
    "bg": "#1a1b26",
    "fg": "#c0caf5",
    "ansi": [
        "#15161e",
        "#f7768e",
        "#9ece6a",
        "#e0af68",
        "#7aa2f7",
        "#bb9af7",
        "#7dcfff",
        "#a9b1d6",
        "#414868",
        "#f7768e",
        "#9ece6a",
        "#e0af68",
        "#7aa2f7",
        "#bb9af7",
        "#7dcfff",
        "#c0caf5",
    ],
}

DEEP_BLACK = {
    "bg": "#050505",
    "fg": "#e6e6e6",
    "ansi": [
        "#050505",
        "#ff6b6b",
        "#94d82d",
        "#ffd166",
        "#4dabf7",
        "#b197fc",
        "#63e6be",
        "#adb5bd",
        "#1f1f1f",
        "#ff8787",
        "#a9e34b",
        "#ffe066",
        "#74c0fc",
        "#d0bfff",
        "#96f2d7",
        "#f1f3f5",
    ],
}

# --- Light-mode bundled palettes -------------------------------------------

SOLARIZED_LIGHT = {
    "bg": "#fdf6e3",
    "fg": "#657b83",
    "ansi": [
        "#073642",
        "#dc322f",
        "#859900",
        "#b58900",
        "#268bd2",
        "#d33682",
        "#2aa198",
        "#eee8d5",
        "#fdf6e3",
        "#cb4b16",
        "#93a1a1",
        "#839496",
        "#657b83",
        "#6c71c4",
        "#586e75",
        "#002b36",
    ],
}

GITHUB_LIGHT = {
    "bg": "#ffffff",
    "fg": "#24292e",
    "ansi": [
        "#24292e",
        "#d73a49",
        "#28a745",
        "#dbab09",
        "#0366d6",
        "#6f42c1",
        "#1b7c83",
        "#6a737d",
        "#586069",
        "#cb2431",
        "#22863a",
        "#b08800",
        "#005cc5",
        "#5a32a3",
        "#3192aa",
        "#d1d5da",
    ],
}

ROSE_PINE_DAWN = {
    "bg": "#faf4ed",
    "fg": "#575279",
    "ansi": [
        "#f2e9e1",
        "#b4637a",
        "#56949f",
        "#ea9d34",
        "#286983",
        "#907aa9",
        "#d7827e",
        "#575279",
        "#9893a5",
        "#b4637a",
        "#56949f",
        "#ea9d34",
        "#286983",
        "#907aa9",
        "#d7827e",
        "#cecacd",
    ],
}

# --- Coherent palettes for the original 4 themes ---------------------------

OCEAN = {
    "bg": "#0a1929",
    "fg": "#d6eaf8",
    "ansi": [
        "#0a1929",
        "#e74c3c",
        "#48c9b0",
        "#f4d03f",
        "#3498db",
        "#1abc9c",
        "#5dade2",
        "#aed6f1",
        "#34495e",
        "#ec7063",
        "#1abc9c",
        "#f7dc6f",
        "#5499c7",
        "#48c9b0",
        "#85c1e9",
        "#ebf5fb",
    ],
}

FOREST = {
    "bg": "#1a2310",
    "fg": "#e3eecc",
    "ansi": [
        "#1a2310",
        "#c0392b",
        "#27ae60",
        "#d4ac0d",
        "#7d6608",
        "#16a085",
        "#1e8449",
        "#aed581",
        "#52682d",
        "#cd6155",
        "#52be80",
        "#f4d03f",
        "#7d6608",
        "#48c9b0",
        "#7dcea0",
        "#eaf2cf",
    ],
}

SUNSET = {
    "bg": "#2d1b0e",
    "fg": "#ffe4cc",
    "ansi": [
        "#2d1b0e",
        "#e74c3c",
        "#d35400",
        "#f39c12",
        "#7d3c98",
        "#c0392b",
        "#e67e22",
        "#fad7a0",
        "#5d4037",
        "#ec7063",
        "#e67e22",
        "#f9e79f",
        "#a93226",
        "#d35400",
        "#f5b041",
        "#fdebd0",
    ],
}

VAPORWAVE = {
    "bg": "#16002a",
    "fg": "#ffe0ff",
    "ansi": [
        "#16002a",
        "#ff6ec7",
        "#48c9b0",
        "#f7dc6f",
        "#bb6bd9",
        "#ec407a",
        "#7fdbff",
        "#e8daef",
        "#5b2c6f",
        "#ff79c6",
        "#80deea",
        "#fff59d",
        "#d7bde2",
        "#f06292",
        "#80deea",
        "#fce4ec",
    ],
}

BUBBLEGUM_PINK = {
    "bg": "#2a0f1f",
    "fg": "#fff1f7",
    "ansi": [
        "#2a0f1f",
        "#ff5fa2",
        "#ff8ec7",
        "#ffd1e8",
        "#ff4f93",
        "#d96cff",
        "#ff9fd2",
        "#fff1f7",
        "#4d1d39",
        "#ff7ab2",
        "#ffb3da",
        "#ffe0ef",
        "#ff6fb0",
        "#eb8cff",
        "#ffc4e1",
        "#fff8fb",
    ],
}
