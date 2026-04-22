"""Slide content for the onboarding wizard.

🐶 Lean, mean, ADHD-friendly slides. 5 slides max!
"""

from typing import List, Tuple

from code_puppy.config import get_puppy_emoji

# ============================================================================
# Slide Data Constants
# ============================================================================

# Model subscription options
MODEL_OPTIONS: List[Tuple[str, str, str]] = [
    ("chatgpt", "ChatGPT Plus/Pro/Max", "OAuth login - no API key needed"),
    ("claude", "Claude Code Pro/Max", "OAuth login - no API key needed"),
    ("api_keys", "API Keys", "OpenAI, Anthropic, Google, etc."),
    ("openrouter", "OpenRouter", "Single key for 100+ models"),
    ("skip", "Skip for now", "Configure later with /set or /add_model"),
]


# ============================================================================
# Navigation Footer (shown on ALL slides)
# ============================================================================


def get_nav_footer() -> str:
    """Navigation hints shown at bottom of every slide."""
    return (
        "\n[dim]─────────────────────────────────────[/dim]\n"
        "[green]→/l[/green] Next  "
        "[green]←/h[/green] Back  "
        "[green]↑↓/jk[/green] Options  "
        "[green]Enter[/green] Select  "
        "[yellow]ESC[/yellow] Skip"
    )


# ============================================================================
# Gradient Banner
# ============================================================================


def get_gradient_banner() -> str:
    """Generate the gradient CODE PUPPY banner."""
    try:
        import pyfiglet

        lines = pyfiglet.figlet_format("CODE PUPPY", font="ansi_shadow").split("\n")
        colors = ["bright_blue", "bright_cyan", "bright_green"]
        result = []
        for i, line in enumerate(lines):
            if line.strip():
                color = colors[min(i // 2, len(colors) - 1)]
                result.append(f"[{color}]{line}[/{color}]")
        return "\n".join(result)
    except ImportError:
        return f"[bold bright_cyan]═══ CODE PUPPY {get_puppy_emoji()} ═══[/bold bright_cyan]"


# ============================================================================
# Slide Content (5 slides total)
# ============================================================================


def slide_welcome() -> str:
    """Slide 1: Welcome - quick intro."""
    content = get_gradient_banner()
    content += "\n\n"
    content += f"[bold white]Welcome! {get_puppy_emoji()}[/bold white]\n\n"
    content += "[cyan]Quick setup:[/cyan]\n"
    content += "  1. Pick your model provider\n"
    content += "  2. Optional: MCP servers\n"
    content += "  3. Learn when to use which agent\n"
    content += "  4. Start coding!\n\n"
    content += "[dim]Takes ~1 minute. Let's go![/dim]"
    content += get_nav_footer()
    return content


def slide_models(selected_option: int, options: List[Tuple[str, str]]) -> str:
    """Slide 2: Model selection."""
    content = "[bold cyan]📦 Pick Your Models[/bold cyan]\n\n"
    content += "[white]How do you want to access LLMs?[/white]\n\n"

    for i, (_, label) in enumerate(options):
        if i == selected_option:
            content += f"[bold green]▶ {label}[/bold green]\n"
        else:
            content += f"[dim]  {label}[/dim]\n"

    content += "\n"

    # Context based on selection
    opt = options[selected_option][0] if options else None
    if opt == "chatgpt":
        content += "[yellow]💡 ChatGPT OAuth[/yellow]\n"
        content += "  Uses your existing subscription\n"
        content += "  GPT-5.2, GPT-5.2-codex\n"
    elif opt == "claude":
        content += "[yellow]💡 Claude OAuth[/yellow]\n"
        content += "  Uses your existing subscription\n"
        content += "  Opus/Sonnet/Haiku 4.5\n"
    elif opt == "api_keys":
        content += "[yellow]💡 API Keys[/yellow]\n"
        content += "  [cyan]/set OPENAI_API_KEY=sk-...[/cyan]\n"
        content += "  [cyan]/add_model[/cyan] to browse 1500+ models\n"
    elif opt == "openrouter":
        content += "[yellow]💡 OpenRouter[/yellow]\n"
        content += "  One API key, all providers\n"
        content += "  [cyan]/set OPENROUTER_API_KEY=...[/cyan]\n"
    else:
        content += "[dim]No worries! Use /set or /add_model later[/dim]\n"

    content += get_nav_footer()
    return content


def slide_mcp() -> str:
    """Slide 3: MCP servers (optional power-ups)."""
    content = "[bold cyan]🔌 MCP Servers (Optional)[/bold cyan]\n\n"
    content += "[white]Supercharge with external tools![/white]\n\n"
    content += "[green]Commands:[/green]\n"
    content += "  [cyan]/mcp install[/cyan]  Browse catalog\n"
    content += "  [cyan]/mcp list[/cyan]     See your servers\n\n"
    content += "[yellow]🌟 Popular picks:[/yellow]\n"
    content += "  • GitHub integration\n"
    content += "  • Postgres/databases\n"
    content += "  • Slack, Linear, etc.\n\n"
    content += "[dim]Skip this if you just want to code![/dim]"
    content += get_nav_footer()
    return content


def slide_use_cases() -> str:
    """Slide 4: When to use which agent - THE IMPORTANT ONE."""
    content = "[bold cyan]🎯 When to Use What[/bold cyan]\n\n"

    content += f"[bold yellow]{get_puppy_emoji()} Code Puppy (default)[/bold yellow]\n"
    content += "  [green]USE FOR:[/green] Direct coding tasks\n"
    content += "  • Fix this bug\n"
    content += "  • Add a feature to this file\n"
    content += "  • Refactor this function\n"
    content += "  • Write tests for X\n\n"

    content += "[bold yellow]📋 Planning Agent[/bold yellow]\n"
    content += "  [green]USE FOR:[/green] Complex multi-step projects\n"
    content += "  • Build me a REST API with auth\n"
    content += "  • Create a CLI tool from scratch\n"
    content += "  • Refactor entire codebase\n"
    content += "  • Multi-file architectural changes\n\n"

    content += "[cyan]Switch: /agent planning-agent[/cyan]\n"
    content += "[dim]Planning breaks big tasks into steps,[/dim]\n"
    content += "[dim]then delegates to specialists.[/dim]"
    content += get_nav_footer()
    return content


def slide_done(trigger_oauth: str | None) -> str:
    """Slide 5: You're ready!"""
    content = "[bold green]🎉 Ready to Roll![/bold green]\n\n"
    content += "[bold cyan]Essential commands:[/bold cyan]\n"
    content += "  [cyan]/model[/cyan]   Switch models\n"
    content += "  [cyan]/agent[/cyan]   Switch agents\n"
    content += "  [cyan]/help[/cyan]    All commands\n\n"

    content += "[bold yellow]Pro tips:[/bold yellow]\n"
    content += "  • Be specific in prompts\n"
    content += "  • Use Planning Agent for big tasks\n"
    content += "  • @ for file path completion\n\n"

    if trigger_oauth:
        content += f"[bold cyan]→ {trigger_oauth.title()} OAuth next![/bold cyan]\n\n"

    content += "[dim]Re-run anytime: [/dim][cyan]/tutorial[/cyan]\n"
    content += (
        f"\n[bold yellow]Press Enter to start coding! {get_puppy_emoji()}[/bold yellow]"
    )
    content += get_nav_footer()
    return content
