"""Banner color data constants.

The interactive ``/colors`` TUI that used to live here (and its
``/diff`` sibling) was removed: banner and diff styling are owned by
the theme system now (the ``theme`` plugin's ``/themes`` picker drives
palettes, banner colors, and diff tints together).

This module survives as a pure data module because the theme plugin
imports these constants from this path -- keep the module name stable.
"""

# Banner display names; decorative icons are intentionally omitted.
BANNER_DISPLAY_INFO = {
    "thinking": ("THINKING", ""),
    "agent_response": ("AGENT RESPONSE", ""),
    "shell_command": ("SHELL COMMAND", ""),
    "read_file": ("READ FILE", ""),
    "edit_file": ("EDIT FILE", ""),
    "create_file": ("CREATE FILE", ""),
    "replace_in_file": ("REPLACE IN FILE", ""),
    "delete_snippet": ("DELETE SNIPPET", ""),
    "grep": ("GREP", ""),
    "directory_listing": ("DIRECTORY LISTING", ""),
    "agent_reasoning": ("AGENT REASONING", ""),
    "invoke_agent": ("INVOKE AGENT", ""),
    "subagent_response": ("\u2713 AGENT RESPONSE", ""),
    "list_agents": ("LIST AGENTS", ""),
    "universal_constructor": ("UNIVERSAL CONSTRUCTOR", ""),
    "terminal_tool": ("TERMINAL TOOL", ""),
    "llm_judge": ("LLM JUDGE", ""),
}

# Sample content to show after each banner
BANNER_SAMPLE_CONTENT = {
    "thinking": "Let me analyze this code structure and figure out the best approach...",
    "agent_response": "I've implemented the feature you requested. The changes include...",
    "shell_command": "$ npm run test -- --silent\nTimeout: 60s",
    "read_file": "/path/to/file.py (lines 1-50)",
    "edit_file": "MODIFY /path/to/file.py\n--- a/file.py\n+++ b/file.py",
    "create_file": "CREATE /path/to/new_file.py\nFile created successfully.",
    "replace_in_file": "MODIFY /path/to/file.py\n--- a/file.py\n+++ b/file.py",
    "delete_snippet": "MODIFY /path/to/file.py\nSnippet deleted from file.",
    "grep": "/src for 'handleClick'\nButton.tsx (3 matches)",
    "directory_listing": "/src (recursive=True)\ncomponents/\n   \u2514\u2500\u2500 Button.tsx",
    "agent_reasoning": "Current reasoning:\nI need to refactor this function...",
    "invoke_agent": "code-reviewer (New session)\nSession: review-auth-abc123",
    "subagent_response": "code-reviewer\nThe code looks good overall...",
    "list_agents": "- code-puppy: Code Puppy\n- planning-agent: Planning Agent",
    "universal_constructor": "action=create tool_name=api.weather\nCreated successfully",
    "terminal_tool": "$ chromium --headless\nBrowser terminal session started",
    "llm_judge": "Verdict: Complete\nGoal verified \u2014 all tests pass.",
}

# Available background colors grouped by theme
BANNER_COLORS = {
    # Cool colors
    "blue": "blue",
    "dark blue": "dark_blue",
    "navy blue": "navy_blue",
    "deep sky blue": "deep_sky_blue4",
    "steel blue": "steel_blue",
    "dodger blue": "dodger_blue3",
    # Cyans & Teals
    "dark cyan": "dark_cyan",
    "cyan": "cyan4",
    "teal": "dark_turquoise",
    "aquamarine": "aquamarine1",
    # Greens
    "green": "green4",
    "dark green": "dark_green",
    "sea green": "dark_sea_green4",
    "spring green": "spring_green4",
    "chartreuse": "chartreuse4",
    # Purples & Magentas
    "purple": "purple",
    "dark magenta": "dark_magenta",
    "medium purple": "medium_purple4",
    "dark violet": "dark_violet",
    "plum": "plum4",
    "orchid": "dark_orchid",
    # Reds & Oranges
    "red": "red3",
    "dark red": "dark_red",
    "indian red": "indian_red",
    "orange red": "orange_red1",
    "orange": "dark_orange3",
    # Yellows & Golds
    "gold": "gold3",
    "dark goldenrod": "dark_goldenrod",
    "olive": "dark_olive_green3",
    # Grays
    "grey30": "grey30",
    "grey37": "grey37",
    "grey42": "grey42",
    "grey50": "grey50",
    "grey58": "grey58",
    "dark slate gray": "dark_slate_gray3",
    # Pink tones
    "hot pink": "hot_pink3",
    "deep pink": "deep_pink4",
    "pale violet red": "pale_violet_red1",
}
