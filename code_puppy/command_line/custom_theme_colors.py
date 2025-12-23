"""Color constants and message types configuration for custom theme builder.

This module contains the available colors, style modifiers, and message type
definitions used by the custom theme builder interface.
"""

from typing import List, Tuple

# =============================================================================
# Available Colors
# =============================================================================

# Standard ANSI colors
STANDARD_COLORS: List[str] = [
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
]

# Bright variants
BRIGHT_COLORS: List[str] = [
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
]

# Common named colors
NAMED_COLORS: List[str] = [
    "orange",
    "purple",
    "pink",
    "gray",
    "grey",
    "violet",
    "indigo",
    "turquoise",
    "teal",
    "brown",
    "beige",
    "maroon",
    "navy",
    "olive",
    "coral",
    "salmon",
    "gold",
    "silver",
    "sky_blue",
    "sea_green",
    "crimson",
    "orchid",
    "plum",
    "tan",
]

# Style modifiers
STYLE_MODIFIERS: List[str] = [
    "(no style)",
    "bold",
    "dim",
    "italic",
    "underline",
    "bold italic",
    "bold underline",
    "dim italic",
]

# All available colors combined
ALL_COLORS: List[str] = STANDARD_COLORS + BRIGHT_COLORS + NAMED_COLORS

# =============================================================================
# Message Types Configuration
# =============================================================================

# Each tuple: (field_name, display_name, description)
MESSAGE_TYPES: List[Tuple[str, str, str]] = [
    ("error_color", "Error Color", "❌ Error messages"),
    ("warning_color", "Warning Color", "⚠️  Warning messages"),
    ("success_color", "Success Color", "✅ Success messages"),
    ("info_color", "Info Color", "ℹ️  Informational messages"),
    ("debug_color", "Debug Color", "🔍 Debug information"),
    ("tool_output_color", "Tool Output Color", "🔧 Tool output"),
    ("agent_reasoning_color", "Agent Reasoning Color", "🧠 Agent reasoning"),
    ("agent_response_color", "Agent Response Color", "💬 Agent responses"),
    ("system_color", "System Color", "⚙️  System messages"),
]
