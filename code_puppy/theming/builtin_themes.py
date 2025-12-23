"""Built-in themes for Code Puppy.

This module defines 11 carefully crafted color themes for the CLI interface.
Each theme is designed to be visually cohesive and accessible.
"""

from .theme_models import Theme, ThemeColors

# =============================================================================
# Default Theme - The classic Code Puppy look
# =============================================================================

_default_colors = ThemeColors(
    # Message levels
    error_style="bold red",
    warning_style="yellow",
    success_style="green",
    info_style="white",
    debug_style="dim",
    # UI elements
    header_style="bold white on blue",
    prompt_style="bold green",
    accent_style="cyan",
    muted_style="dim",
    highlight_style="bold yellow",
    # Tool headers with backgrounds
    file_header_style="bold white on blue",
    grep_header_style="bold white on blue",
    shell_header_style="bold white on blue",
    # Agent messages with backgrounds
    reasoning_header_style="bold white on purple",
    response_header_style="bold white on purple",
    subagent_header_style="bold white on purple",
    subagent_response_header_style="bold white on green",
    # Tool outputs
    file_path_style="cyan",
    line_number_style="dim cyan",
    command_style="bold white",
    # Spinner
    spinner_style="bold cyan",
    spinner_text_style="bold cyan",
    # Panels
    panel_border_style="blue",
    panel_title_style="bold blue",
    # Navigation
    nav_key_style="bold cyan",
    nav_text_style="dim",
    # Diff
    diff_add_style="green",
    diff_remove_style="red",
    diff_context_style="dim",
    # Prompt
    prompt_puppy_style="bold ansibrightcyan",
    prompt_agent_style="bold ansibrightblue",
    prompt_model_style="bold ansibrightcyan",
    prompt_cwd_style="bold ansibrightgreen",
    prompt_arrow_style="bold ansibrightblue",
)

DEFAULT_THEME = Theme(
    name="default",
    display_name="Default 🐶",
    description="The classic Code Puppy look - clean and friendly",
    colors=_default_colors,
)

# =============================================================================
# Ocean Depths - Deep sea blues and teals
# =============================================================================

_ocean_depths_colors = ThemeColors(
    # Message levels - ocean-inspired
    error_style="bold #ff6b6b",  # Coral red
    warning_style="#ffd93d",  # Sunny yellow
    success_style="#6bcb77",  # Sea green
    info_style="#87ceeb",  # Sky blue
    debug_style="dim #5f9ea0",  # Dim cadet blue
    # UI elements
    header_style="bold white on #1b4965",  # Deep ocean blue bg
    prompt_style="bold #20b2aa",  # Light sea green
    accent_style="#40e0d0",  # Turquoise
    muted_style="dim #5f9ea0",  # Cadet blue
    highlight_style="bold #ffd700",  # Gold (like sunlight on water)
    # Tool headers with ocean backgrounds
    file_header_style="bold white on #1b4965",  # Deep ocean blue
    grep_header_style="bold white on #1b4965",  # Deep ocean blue
    shell_header_style="bold white on #1b4965",  # Deep ocean blue
    # Agent messages with purple-blue backgrounds
    reasoning_header_style="bold white on #4a3f6b",  # Deep purple (like deep water)
    response_header_style="bold white on #4a3f6b",  # Deep purple
    subagent_header_style="bold white on #4a3f6b",  # Deep purple
    subagent_response_header_style="bold white on #2d5a4a",  # Deep teal
    # Tool outputs
    file_path_style="#00ced1",  # Dark turquoise
    line_number_style="dim #5f9ea0",  # Cadet blue
    command_style="bold #e0ffff",  # Light cyan
    # Spinner
    spinner_style="bold #00ced1",  # Dark turquoise
    spinner_text_style="bold #40e0d0",  # Turquoise
    # Panels
    panel_border_style="#4682b4",  # Steel blue
    panel_title_style="bold #00ced1",  # Dark turquoise
    # Navigation
    nav_key_style="bold #40e0d0",  # Turquoise
    nav_text_style="dim #87ceeb",  # Sky blue
    # Diff
    diff_add_style="#6bcb77",  # Sea green
    diff_remove_style="#ff6b6b",  # Coral red
    diff_context_style="dim #5f9ea0",  # Cadet blue
    # Prompt - ocean blues
    prompt_puppy_style="bold #00ced1",  # Dark turquoise
    prompt_agent_style="bold #4169e1",  # Royal blue
    prompt_model_style="bold #40e0d0",  # Turquoise
    prompt_cwd_style="bold #6bcb77",  # Sea green
    prompt_arrow_style="bold #87ceeb",  # Sky blue
)

OCEAN_DEPTHS_THEME = Theme(
    name="ocean-depths",
    display_name="Ocean Depths 🌊",
    description="Deep sea blues and teals - calm and focused",
    colors=_ocean_depths_colors,
)

# =============================================================================
# Forest Night - Earthy greens and natural tones
# =============================================================================

_forest_night_colors = ThemeColors(
    # Message levels
    error_style="bold #e74c3c",  # Autumn red
    warning_style="#f39c12",  # Amber
    success_style="#27ae60",  # Forest green
    info_style="#bdc3c7",  # Silver
    debug_style="dim #7f8c8d",  # Dim gray
    # UI elements
    header_style="bold white on #1a472a",  # Dark forest green bg
    prompt_style="bold #1abc9c",  # Turquoise green
    accent_style="#3498db",  # Moonlight blue
    muted_style="dim #7f8c8d",  # Asphalt
    highlight_style="bold #f1c40f",  # Sunflower
    # Tool headers with forest backgrounds
    file_header_style="bold white on #1a472a",  # Dark forest green
    grep_header_style="bold white on #1a472a",  # Dark forest green
    shell_header_style="bold white on #1a472a",  # Dark forest green
    # Agent messages with purple backgrounds (night flowers)
    reasoning_header_style="bold white on #4a235a",  # Deep purple
    response_header_style="bold white on #4a235a",  # Deep purple
    subagent_header_style="bold white on #4a235a",  # Deep purple
    subagent_response_header_style="bold white on #145a32",  # Deep green
    # Tool outputs
    file_path_style="#1abc9c",  # Turquoise
    line_number_style="dim #27ae60",  # Nephritis
    command_style="bold #ecf0f1",  # Clouds
    # Spinner
    spinner_style="bold #2ecc71",  # Emerald
    spinner_text_style="bold #27ae60",  # Nephritis
    # Panels
    panel_border_style="#27ae60",  # Forest green
    panel_title_style="bold #2ecc71",  # Emerald
    # Navigation
    nav_key_style="bold #1abc9c",  # Turquoise
    nav_text_style="dim #95a5a6",  # Concrete
    # Diff
    diff_add_style="#27ae60",  # Forest green
    diff_remove_style="#c0392b",  # Pomegranate
    diff_context_style="dim #7f8c8d",  # Asphalt
    # Prompt - forest greens
    prompt_puppy_style="bold #2ecc71",  # Emerald
    prompt_agent_style="bold #16a085",  # Green sea
    prompt_model_style="bold #1abc9c",  # Turquoise
    prompt_cwd_style="bold #27ae60",  # Forest green
    prompt_arrow_style="bold #3498db",  # Moonlight blue
)

FOREST_NIGHT_THEME = Theme(
    name="forest-night",
    display_name="Forest Night 🌲",
    description="Earthy greens and natural tones - grounded and serene",
    colors=_forest_night_colors,
)

# =============================================================================
# Synthwave - Retro neon cyberpunk
# =============================================================================

_synthwave_colors = ThemeColors(
    # Message levels - neon vibes
    error_style="bold #ff2a6d",  # Hot pink
    warning_style="#ffcc00",  # Electric yellow
    success_style="#05ffa1",  # Neon green
    info_style="#d1f7ff",  # Electric blue white
    debug_style="dim #9d4edd",  # Dim purple
    # UI elements
    header_style="bold #d1f7ff on #7209b7",  # Cyan on violet
    prompt_style="bold #4cc9f0",  # Electric cyan
    accent_style="#7209b7",  # Violet
    muted_style="dim #480ca8",  # Dark purple
    highlight_style="bold #ffcc00",  # Electric yellow
    # Tool headers with neon backgrounds
    file_header_style="bold #d1f7ff on #7209b7",  # Cyan on violet
    grep_header_style="bold #d1f7ff on #7209b7",  # Cyan on violet
    shell_header_style="bold #d1f7ff on #7209b7",  # Cyan on violet
    # Agent messages with hot pink backgrounds
    reasoning_header_style="bold white on #b5179e",  # Hot pink bg
    response_header_style="bold white on #b5179e",  # Hot pink bg
    subagent_header_style="bold white on #b5179e",  # Hot pink bg
    subagent_response_header_style="bold #1a1a2e on #05ffa1",  # Dark on neon green
    # Tool outputs
    file_path_style="#4cc9f0",  # Cyan
    line_number_style="dim #7209b7",  # Violet
    command_style="bold #d1f7ff",  # Light cyan
    # Spinner
    spinner_style="bold #f72585",  # Pink
    spinner_text_style="bold #4cc9f0",  # Cyan
    # Panels
    panel_border_style="#7209b7",  # Violet
    panel_title_style="bold #f72585",  # Pink
    # Navigation
    nav_key_style="bold #4cc9f0",  # Cyan
    nav_text_style="dim #9d4edd",  # Purple
    # Diff
    diff_add_style="#05ffa1",  # Neon green
    diff_remove_style="#ff2a6d",  # Hot pink
    diff_context_style="dim #480ca8",  # Dark purple
    # Prompt - neon cyberpunk
    prompt_puppy_style="bold #f72585",  # Hot pink
    prompt_agent_style="bold #7209b7",  # Violet
    prompt_model_style="bold #4cc9f0",  # Electric cyan
    prompt_cwd_style="bold #05ffa1",  # Neon green
    prompt_arrow_style="bold #ffcc00",  # Electric yellow
)

SYNTHWAVE_THEME = Theme(
    name="synthwave",
    display_name="Synthwave 🌆",
    description="Retro neon cyberpunk - pink, purple, and cyan dreams",
    colors=_synthwave_colors,
)

# =============================================================================
# Monokai Pro - Classic dark editor theme
# =============================================================================

_monokai_pro_colors = ThemeColors(
    # Message levels - Monokai palette
    error_style="bold #ff6188",  # Red
    warning_style="#ffd866",  # Yellow
    success_style="#a9dc76",  # Green
    info_style="#fcfcfa",  # Foreground
    debug_style="dim #727072",  # Comment gray
    # UI elements
    header_style="bold white on #403e41",  # Monokai dark bg
    prompt_style="bold #a9dc76",  # Green
    accent_style="#ab9df2",  # Purple
    muted_style="dim #727072",  # Comment
    highlight_style="bold #ffd866",  # Yellow
    # Tool headers with Monokai backgrounds
    file_header_style="bold #78dce8 on #403e41",  # Cyan on dark
    grep_header_style="bold #78dce8 on #403e41",  # Cyan on dark
    shell_header_style="bold #78dce8 on #403e41",  # Cyan on dark
    # Agent messages with purple backgrounds
    reasoning_header_style="bold white on #5c4d7d",  # Purple bg
    response_header_style="bold white on #5c4d7d",  # Purple bg
    subagent_header_style="bold white on #5c4d7d",  # Purple bg
    subagent_response_header_style="bold #2d2a2e on #a9dc76",  # Dark on green
    # Tool outputs
    file_path_style="#78dce8",  # Cyan
    line_number_style="dim #727072",  # Comment
    command_style="bold #fcfcfa",  # Foreground
    # Spinner
    spinner_style="bold #ff6188",  # Red (Monokai accent)
    spinner_text_style="bold #78dce8",  # Cyan
    # Panels
    panel_border_style="#727072",  # Comment gray
    panel_title_style="bold #ff6188",  # Red
    # Navigation
    nav_key_style="bold #78dce8",  # Cyan
    nav_text_style="dim #727072",  # Comment
    # Diff
    diff_add_style="#a9dc76",  # Green
    diff_remove_style="#ff6188",  # Red
    diff_context_style="dim #727072",  # Comment
    # Prompt - Monokai
    prompt_puppy_style="bold #ff6188",  # Red accent
    prompt_agent_style="bold #ab9df2",  # Purple
    prompt_model_style="bold #78dce8",  # Cyan
    prompt_cwd_style="bold #a9dc76",  # Green
    prompt_arrow_style="bold #ffd866",  # Yellow
)

MONOKAI_PRO_THEME = Theme(
    name="monokai-pro",
    display_name="Monokai Pro 🎨",
    description="Classic dark editor theme - timeless and elegant",
    colors=_monokai_pro_colors,
)

# =============================================================================
# Solarized Dark - Precision-crafted palette
# =============================================================================

_solarized_dark_colors = ThemeColors(
    # Message levels - Solarized accent colors
    error_style="bold #dc322f",  # Red
    warning_style="#b58900",  # Yellow
    success_style="#859900",  # Green
    info_style="#839496",  # Base0
    debug_style="dim #586e75",  # Base01
    # UI elements
    header_style="bold #93a1a1 on #073642",  # Light on Base02
    prompt_style="bold #859900",  # Green
    accent_style="#2aa198",  # Cyan
    muted_style="dim #586e75",  # Base01
    highlight_style="bold #b58900",  # Yellow
    # Tool headers with Solarized backgrounds
    file_header_style="bold #93a1a1 on #073642",  # Light on Base02
    grep_header_style="bold #93a1a1 on #073642",  # Light on Base02
    shell_header_style="bold #93a1a1 on #073642",  # Light on Base02
    # Agent messages with magenta backgrounds
    reasoning_header_style="bold #fdf6e3 on #6c3461",  # Light on magenta-ish
    response_header_style="bold #fdf6e3 on #6c3461",  # Light on magenta-ish
    subagent_header_style="bold #fdf6e3 on #6c3461",  # Light on magenta-ish
    subagent_response_header_style="bold #002b36 on #859900",  # Dark on green
    # Tool outputs
    file_path_style="#2aa198",  # Cyan
    line_number_style="dim #657b83",  # Base00
    command_style="bold #93a1a1",  # Base1
    # Spinner
    spinner_style="bold #268bd2",  # Blue
    spinner_text_style="bold #2aa198",  # Cyan
    # Panels
    panel_border_style="#073642",  # Base02
    panel_title_style="bold #268bd2",  # Blue
    # Navigation
    nav_key_style="bold #2aa198",  # Cyan
    nav_text_style="dim #586e75",  # Base01
    # Diff
    diff_add_style="#859900",  # Green
    diff_remove_style="#dc322f",  # Red
    diff_context_style="dim #586e75",  # Base01
    # Prompt - Solarized
    prompt_puppy_style="bold #268bd2",  # Blue
    prompt_agent_style="bold #2aa198",  # Cyan
    prompt_model_style="bold #d33682",  # Magenta
    prompt_cwd_style="bold #859900",  # Green
    prompt_arrow_style="bold #b58900",  # Yellow
)

SOLARIZED_DARK_THEME = Theme(
    name="solarized-dark",
    display_name="Solarized Dark ☀️",
    description="Precision-crafted Solarized palette - scientifically designed",
    colors=_solarized_dark_colors,
)

# =============================================================================
# Dracula - Dark with vivid purple/pink accents
# =============================================================================

_dracula_colors = ThemeColors(
    # Message levels - Dracula palette
    error_style="bold #ff5555",  # Red
    warning_style="#ffb86c",  # Orange
    success_style="#50fa7b",  # Green
    info_style="#f8f8f2",  # Foreground
    debug_style="dim #6272a4",  # Comment
    # UI elements
    header_style="bold #f8f8f2 on #44475a",  # Light on selection bg
    prompt_style="bold #50fa7b",  # Green
    accent_style="#ff79c6",  # Pink
    muted_style="dim #6272a4",  # Comment
    highlight_style="bold #f1fa8c",  # Yellow
    # Tool headers with Dracula backgrounds
    file_header_style="bold #f8f8f2 on #44475a",  # Light on selection
    grep_header_style="bold #f8f8f2 on #44475a",  # Light on selection
    shell_header_style="bold #f8f8f2 on #44475a",  # Light on selection
    # Agent messages with purple/pink backgrounds
    reasoning_header_style="bold #f8f8f2 on #6d4a7d",  # Light on purple
    response_header_style="bold #f8f8f2 on #6d4a7d",  # Light on purple
    subagent_header_style="bold #f8f8f2 on #6d4a7d",  # Light on purple
    subagent_response_header_style="bold #282a36 on #50fa7b",  # Dark on green
    # Tool outputs
    file_path_style="#8be9fd",  # Cyan
    line_number_style="dim #6272a4",  # Comment
    command_style="bold #f8f8f2",  # Foreground
    # Spinner
    spinner_style="bold #bd93f9",  # Purple
    spinner_text_style="bold #ff79c6",  # Pink
    # Panels
    panel_border_style="#bd93f9",  # Purple
    panel_title_style="bold #ff79c6",  # Pink
    # Navigation
    nav_key_style="bold #8be9fd",  # Cyan
    nav_text_style="dim #6272a4",  # Comment
    # Diff
    diff_add_style="#50fa7b",  # Green
    diff_remove_style="#ff5555",  # Red
    diff_context_style="dim #6272a4",  # Comment
    # Prompt - Dracula
    prompt_puppy_style="bold #bd93f9",  # Purple
    prompt_agent_style="bold #ff79c6",  # Pink
    prompt_model_style="bold #8be9fd",  # Cyan
    prompt_cwd_style="bold #50fa7b",  # Green
    prompt_arrow_style="bold #f1fa8c",  # Yellow
)

DRACULA_THEME = Theme(
    name="dracula",
    display_name="Dracula 🧛",
    description="Dark with vivid purple and pink accents - mysteriously beautiful",
    colors=_dracula_colors,
)

# =============================================================================
# Nord - Arctic-inspired cool blue tones
# =============================================================================

_nord_colors = ThemeColors(
    # Message levels - Nord palette
    error_style="bold #bf616a",  # Aurora Red
    warning_style="#ebcb8b",  # Aurora Yellow
    success_style="#a3be8c",  # Aurora Green
    info_style="#eceff4",  # Snow Storm 3
    debug_style="dim #4c566a",  # Polar Night 4
    # UI elements
    header_style="bold #eceff4 on #3b4252",  # Snow on Polar Night 2
    prompt_style="bold #a3be8c",  # Aurora Green
    accent_style="#81a1c1",  # Frost 3
    muted_style="dim #4c566a",  # Polar Night 4
    highlight_style="bold #ebcb8b",  # Aurora Yellow
    # Tool headers with Nord backgrounds
    file_header_style="bold #eceff4 on #3b4252",  # Snow on Polar Night
    grep_header_style="bold #eceff4 on #3b4252",  # Snow on Polar Night
    shell_header_style="bold #eceff4 on #3b4252",  # Snow on Polar Night
    # Agent messages with purple backgrounds
    reasoning_header_style="bold #eceff4 on #5e4a6d",  # Snow on purple
    response_header_style="bold #eceff4 on #5e4a6d",  # Snow on purple
    subagent_header_style="bold #eceff4 on #5e4a6d",  # Snow on purple
    subagent_response_header_style="bold #2e3440 on #a3be8c",  # Dark on green
    # Tool outputs
    file_path_style="#8fbcbb",  # Frost 1
    line_number_style="dim #4c566a",  # Polar Night 4
    command_style="bold #e5e9f0",  # Snow Storm 2
    # Spinner
    spinner_style="bold #88c0d0",  # Frost 2
    spinner_text_style="bold #81a1c1",  # Frost 3
    # Panels
    panel_border_style="#4c566a",  # Polar Night 4
    panel_title_style="bold #88c0d0",  # Frost 2
    # Navigation
    nav_key_style="bold #8fbcbb",  # Frost 1
    nav_text_style="dim #4c566a",  # Polar Night 4
    # Diff
    diff_add_style="#a3be8c",  # Aurora Green
    diff_remove_style="#bf616a",  # Aurora Red
    diff_context_style="dim #4c566a",  # Polar Night 4
    # Prompt - Nord frost
    prompt_puppy_style="bold #88c0d0",  # Frost 2
    prompt_agent_style="bold #5e81ac",  # Frost 4
    prompt_model_style="bold #81a1c1",  # Frost 3
    prompt_cwd_style="bold #a3be8c",  # Aurora Green
    prompt_arrow_style="bold #8fbcbb",  # Frost 1
)

NORD_THEME = Theme(
    name="nord",
    display_name="Nord ❄️",
    description="Arctic-inspired cool blue tones - crisp and clean",
    colors=_nord_colors,
)

# =============================================================================
# Gruvbox - Retro warm earth tones
# =============================================================================

_gruvbox_colors = ThemeColors(
    # Message levels - Gruvbox palette
    error_style="bold #fb4934",  # Red
    warning_style="#fabd2f",  # Yellow
    success_style="#b8bb26",  # Green
    info_style="#ebdbb2",  # Foreground
    debug_style="dim #928374",  # Gray
    # UI elements
    header_style="bold #ebdbb2 on #3c3836",  # Light on dark bg
    prompt_style="bold #b8bb26",  # Green
    accent_style="#fe8019",  # Orange
    muted_style="dim #928374",  # Gray
    highlight_style="bold #fabd2f",  # Yellow
    # Tool headers with Gruvbox backgrounds
    file_header_style="bold #ebdbb2 on #3c3836",  # Light on dark
    grep_header_style="bold #ebdbb2 on #3c3836",  # Light on dark
    shell_header_style="bold #ebdbb2 on #3c3836",  # Light on dark
    # Agent messages with purple backgrounds
    reasoning_header_style="bold #ebdbb2 on #5d4157",  # Light on purple
    response_header_style="bold #ebdbb2 on #5d4157",  # Light on purple
    subagent_header_style="bold #ebdbb2 on #5d4157",  # Light on purple
    subagent_response_header_style="bold #282828 on #b8bb26",  # Dark on green
    # Tool outputs
    file_path_style="#8ec07c",  # Aqua
    line_number_style="dim #a89984",  # Gray
    command_style="bold #ebdbb2",  # Foreground
    # Spinner
    spinner_style="bold #fe8019",  # Orange
    spinner_text_style="bold #fabd2f",  # Yellow
    # Panels
    panel_border_style="#665c54",  # Dark gray
    panel_title_style="bold #fe8019",  # Orange
    # Navigation
    nav_key_style="bold #8ec07c",  # Aqua
    nav_text_style="dim #928374",  # Gray
    # Diff
    diff_add_style="#b8bb26",  # Green
    diff_remove_style="#fb4934",  # Red
    diff_context_style="dim #928374",  # Gray
    # Prompt - Gruvbox warm
    prompt_puppy_style="bold #fe8019",  # Orange
    prompt_agent_style="bold #d3869b",  # Purple
    prompt_model_style="bold #83a598",  # Blue
    prompt_cwd_style="bold #b8bb26",  # Green
    prompt_arrow_style="bold #fabd2f",  # Yellow
)

GRUVBOX_THEME = Theme(
    name="gruvbox",
    display_name="Gruvbox 🍂",
    description="Retro warm earth tones - cozy and nostalgic",
    colors=_gruvbox_colors,
)

# =============================================================================
# Tokyo Night - Modern purple/blue aesthetic
# =============================================================================

_tokyo_night_colors = ThemeColors(
    # Message levels - Tokyo Night palette
    error_style="bold #f7768e",  # Red
    warning_style="#e0af68",  # Yellow
    success_style="#9ece6a",  # Green
    info_style="#a9b1d6",  # Foreground
    debug_style="dim #565f89",  # Comment
    # UI elements
    header_style="bold #c0caf5 on #24283b",  # Bright on dark bg
    prompt_style="bold #9ece6a",  # Green
    accent_style="#bb9af7",  # Purple
    muted_style="dim #565f89",  # Comment
    highlight_style="bold #e0af68",  # Yellow
    # Tool headers with Tokyo Night backgrounds
    file_header_style="bold #c0caf5 on #24283b",  # Bright on dark
    grep_header_style="bold #c0caf5 on #24283b",  # Bright on dark
    shell_header_style="bold #c0caf5 on #24283b",  # Bright on dark
    # Agent messages with purple backgrounds
    reasoning_header_style="bold #c0caf5 on #5a4a78",  # Bright on purple
    response_header_style="bold #c0caf5 on #5a4a78",  # Bright on purple
    subagent_header_style="bold #c0caf5 on #5a4a78",  # Bright on purple
    subagent_response_header_style="bold #1a1b26 on #9ece6a",  # Dark on green
    # Tool outputs
    file_path_style="#7dcfff",  # Cyan
    line_number_style="dim #565f89",  # Comment
    command_style="bold #c0caf5",  # Bright foreground
    # Spinner
    spinner_style="bold #7aa2f7",  # Blue
    spinner_text_style="bold #bb9af7",  # Purple
    # Panels
    panel_border_style="#565f89",  # Comment
    panel_title_style="bold #7aa2f7",  # Blue
    # Navigation
    nav_key_style="bold #7dcfff",  # Cyan
    nav_text_style="dim #565f89",  # Comment
    # Diff
    diff_add_style="#9ece6a",  # Green
    diff_remove_style="#f7768e",  # Red
    diff_context_style="dim #565f89",  # Comment
    # Prompt - Tokyo Night
    prompt_puppy_style="bold #7aa2f7",  # Blue
    prompt_agent_style="bold #bb9af7",  # Purple
    prompt_model_style="bold #7dcfff",  # Cyan
    prompt_cwd_style="bold #9ece6a",  # Green
    prompt_arrow_style="bold #e0af68",  # Yellow
)

TOKYO_NIGHT_THEME = Theme(
    name="tokyo-night",
    display_name="Tokyo Night 🗼",
    description="Modern purple and blue aesthetic - stylish and sophisticated",
    colors=_tokyo_night_colors,
)

# =============================================================================
# Catppuccin Mocha - Soothing pastel palette
# =============================================================================

_catppuccin_mocha_colors = ThemeColors(
    # Message levels - Catppuccin Mocha palette
    error_style="bold #f38ba8",  # Red
    warning_style="#f9e2af",  # Yellow
    success_style="#a6e3a1",  # Green
    info_style="#cdd6f4",  # Text
    debug_style="dim #6c7086",  # Overlay0
    # UI elements
    header_style="bold #cdd6f4 on #313244",  # Text on Surface0
    prompt_style="bold #a6e3a1",  # Green
    accent_style="#cba6f7",  # Mauve
    muted_style="dim #6c7086",  # Overlay0
    highlight_style="bold #f9e2af",  # Yellow
    # Tool headers with Catppuccin backgrounds
    file_header_style="bold #cdd6f4 on #313244",  # Text on Surface0
    grep_header_style="bold #cdd6f4 on #313244",  # Text on Surface0
    shell_header_style="bold #cdd6f4 on #313244",  # Text on Surface0
    # Agent messages with mauve backgrounds
    reasoning_header_style="bold #cdd6f4 on #5c4a6d",  # Text on mauve-ish
    response_header_style="bold #cdd6f4 on #5c4a6d",  # Text on mauve-ish
    subagent_header_style="bold #cdd6f4 on #5c4a6d",  # Text on mauve-ish
    subagent_response_header_style="bold #1e1e2e on #a6e3a1",  # Base on green
    # Tool outputs
    file_path_style="#94e2d5",  # Teal
    line_number_style="dim #6c7086",  # Overlay0
    command_style="bold #cdd6f4",  # Text
    # Spinner
    spinner_style="bold #f5c2e7",  # Pink
    spinner_text_style="bold #cba6f7",  # Mauve
    # Panels
    panel_border_style="#585b70",  # Surface2
    panel_title_style="bold #f5c2e7",  # Pink
    # Navigation
    nav_key_style="bold #94e2d5",  # Teal
    nav_text_style="dim #6c7086",  # Overlay0
    # Diff
    diff_add_style="#a6e3a1",  # Green
    diff_remove_style="#f38ba8",  # Red
    diff_context_style="dim #6c7086",  # Overlay0
    # Prompt - Catppuccin pastel
    prompt_puppy_style="bold #f5c2e7",  # Pink
    prompt_agent_style="bold #cba6f7",  # Mauve
    prompt_model_style="bold #89b4fa",  # Blue
    prompt_cwd_style="bold #a6e3a1",  # Green
    prompt_arrow_style="bold #f9e2af",  # Yellow
)

CATPPUCCIN_MOCHA_THEME = Theme(
    name="catppuccin-mocha",
    display_name="Catppuccin Mocha 🐱",
    description="Soothing pastel palette - warm and inviting",
    colors=_catppuccin_mocha_colors,
)

# =============================================================================
# Theme Registry
# =============================================================================

BUILTIN_THEMES: dict[str, Theme] = {
    DEFAULT_THEME.name: DEFAULT_THEME,
    OCEAN_DEPTHS_THEME.name: OCEAN_DEPTHS_THEME,
    FOREST_NIGHT_THEME.name: FOREST_NIGHT_THEME,
    SYNTHWAVE_THEME.name: SYNTHWAVE_THEME,
    MONOKAI_PRO_THEME.name: MONOKAI_PRO_THEME,
    SOLARIZED_DARK_THEME.name: SOLARIZED_DARK_THEME,
    DRACULA_THEME.name: DRACULA_THEME,
    NORD_THEME.name: NORD_THEME,
    GRUVBOX_THEME.name: GRUVBOX_THEME,
    TOKYO_NIGHT_THEME.name: TOKYO_NIGHT_THEME,
    CATPPUCCIN_MOCHA_THEME.name: CATPPUCCIN_MOCHA_THEME,
}
