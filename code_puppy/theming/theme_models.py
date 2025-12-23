"""Pydantic models for Code Puppy theming system.

Defines the structure for theme colors and theme configurations.
All color values use Rich console style strings (e.g., "bold red", "#ff5733").
"""

from typing import Optional

from pydantic import BaseModel, Field


class ThemeColors(BaseModel):
    """Color configuration for a Code Puppy theme.

    All style values use Rich console style syntax:
    - Named colors: "red", "green", "blue", "cyan", "magenta", "yellow", "white"
    - Modifiers: "bold", "dim", "italic", "underline", "blink", "reverse"
    - Hex colors: "#ff5733", "#1e90ff"
    - Combined: "bold red", "dim #808080", "bold italic cyan"

    Attributes:
        Message levels - for different severity of messages:
            error_style: Style for error messages (default: bold red)
            warning_style: Style for warning messages (default: yellow)
            success_style: Style for success messages (default: green)
            info_style: Style for informational messages (default: white)
            debug_style: Style for debug messages (default: dim)

        UI elements - for general interface styling:
            header_style: Style for section headers (default: bold cyan)
            prompt_style: Style for input prompts (default: bold green)
            accent_style: Style for accented/highlighted text (default: cyan)
            muted_style: Style for de-emphasized text (default: dim)
            highlight_style: Style for highlighted/important text (default: bold yellow)

        Agent messages - for agent communication:
            reasoning_header_style: Style for "Reasoning:" headers (default: bold magenta)
            response_header_style: Style for response section headers (default: bold blue)

        Tool outputs - for file and command operations:
            file_path_style: Style for file paths in output (default: cyan)
            line_number_style: Style for line numbers (default: dim cyan)
            command_style: Style for shell commands (default: bold white)

        Spinner - for loading animations:
            spinner_style: Style for spinner animation (default: bold cyan)
            spinner_text_style: Style for spinner text (default: bold cyan)

        Panels - for bordered content areas:
            panel_border_style: Style for panel borders (default: blue)
            panel_title_style: Style for panel titles (default: bold blue)

        Navigation hints - for keyboard shortcut displays:
            nav_key_style: Style for key labels like [Enter] (default: bold cyan)
            nav_text_style: Style for navigation descriptions (default: dim)

        Diff colors - for showing code changes:
            diff_add_style: Style for added lines (default: green)
            diff_remove_style: Style for removed lines (default: red)
            diff_context_style: Style for context lines (default: dim)
    """

    # Message levels
    error_style: str = Field(default="bold red", description="Style for error messages")
    warning_style: str = Field(
        default="yellow", description="Style for warning messages"
    )
    success_style: str = Field(
        default="green", description="Style for success messages"
    )
    info_style: str = Field(default="white", description="Style for info messages")
    debug_style: str = Field(default="dim", description="Style for debug messages")

    # UI elements
    header_style: str = Field(
        default="bold white on blue",
        description="Style for section headers (with background)",
    )
    prompt_style: str = Field(
        default="bold green", description="Style for input prompts"
    )
    accent_style: str = Field(default="cyan", description="Style for accented text")
    muted_style: str = Field(default="dim", description="Style for de-emphasized text")
    highlight_style: str = Field(
        default="bold yellow", description="Style for highlighted text"
    )

    # Tool output headers (with backgrounds)
    file_header_style: str = Field(
        default="bold white on blue",
        description="Style for file operation headers (DIRECTORY LISTING, READ FILE, EDIT FILE)",
    )
    grep_header_style: str = Field(
        default="bold white on blue",
        description="Style for GREP header",
    )
    shell_header_style: str = Field(
        default="bold white on blue",
        description="Style for SHELL COMMAND header",
    )

    # Agent messages (with backgrounds)
    reasoning_header_style: str = Field(
        default="bold white on purple",
        description="Style for AGENT REASONING header",
    )
    response_header_style: str = Field(
        default="bold white on purple",
        description="Style for AGENT RESPONSE header",
    )
    subagent_header_style: str = Field(
        default="bold white on purple",
        description="Style for INVOKE AGENT header",
    )
    subagent_response_header_style: str = Field(
        default="bold white on green",
        description="Style for sub-agent response header",
    )

    # Tool outputs
    file_path_style: str = Field(default="cyan", description="Style for file paths")
    line_number_style: str = Field(
        default="dim cyan", description="Style for line numbers"
    )
    command_style: str = Field(
        default="bold white", description="Style for shell commands"
    )

    # Spinner
    spinner_style: str = Field(
        default="bold cyan", description="Style for spinner animation"
    )
    spinner_text_style: str = Field(
        default="bold cyan", description="Style for spinner text"
    )

    # Panels
    panel_border_style: str = Field(
        default="blue", description="Style for panel borders"
    )
    panel_title_style: str = Field(
        default="bold blue", description="Style for panel titles"
    )

    # Navigation hints
    nav_key_style: str = Field(
        default="bold cyan", description="Style for navigation key labels"
    )
    nav_text_style: str = Field(default="dim", description="Style for navigation text")

    # Diff colors
    diff_add_style: str = Field(default="green", description="Style for added lines")
    diff_remove_style: str = Field(default="red", description="Style for removed lines")
    diff_context_style: str = Field(
        default="dim", description="Style for context lines"
    )

    # Prompt styles - for the main input prompt
    prompt_puppy_style: str = Field(
        default="bold ansibrightcyan",
        description="Style for puppy name in prompt",
    )
    prompt_agent_style: str = Field(
        default="bold ansibrightblue",
        description="Style for agent name in prompt",
    )
    prompt_model_style: str = Field(
        default="bold ansibrightcyan",
        description="Style for model name in prompt",
    )
    prompt_cwd_style: str = Field(
        default="bold ansibrightgreen",
        description="Style for current directory in prompt",
    )
    prompt_arrow_style: str = Field(
        default="bold ansibrightblue",
        description="Style for prompt arrow (>>>)",
    )


class Theme(BaseModel):
    """A complete Code Puppy theme configuration.

    Attributes:
        name: Unique identifier for the theme (lowercase, hyphenated)
        display_name: Human-readable theme name with optional emoji
        description: Brief description of the theme's aesthetic
        colors: ThemeColors instance with all color definitions
    """

    name: str = Field(
        ..., description="Unique theme identifier (lowercase, hyphenated)"
    )
    display_name: str = Field(..., description="Human-readable theme name")
    description: str = Field(default="", description="Theme description")
    colors: ThemeColors = Field(
        default_factory=ThemeColors, description="Theme color configuration"
    )

    def get_style(self, style_name: str) -> Optional[str]:
        """Get a style value by name from the theme's colors.

        Args:
            style_name: Name of the style (e.g., "error_style", "header_style")

        Returns:
            The style string if found, None otherwise
        """
        return getattr(self.colors, style_name, None)

    def to_style_dict(self) -> dict[str, str]:
        """Convert theme colors to a flat dictionary of style names to values.

        Returns:
            Dictionary mapping style names to their Rich style strings
        """
        return self.colors.model_dump()
