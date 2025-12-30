"""Slide content for the onboarding wizard.

🐶 Contains all slide definitions and content generators for the onboarding
wizard. Separated from the main wizard logic for maintainability.
"""

from typing import List, Tuple

# ============================================================================
# Slide Data Constants
# ============================================================================

# Model subscription options for slide 1
MODEL_OPTIONS: List[Tuple[str, str, str]] = [
    ("chatgpt", "ChatGPT Plus (Pro/Max)", "OAuth login with your ChatGPT subscription"),
    ("claude", "Claude Code Pro/Max", "OAuth login with your Claude subscription"),
    ("api_keys", "API Keys (OpenAI, Anthropic, etc.)", "Use your own API keys"),
    ("openrouter", "OpenRouter", "Single API key for multiple providers"),
    ("free", "Free tiers / Other providers", "Explore free and community models"),
    ("skip", "Skip this", "Configure later with /set or /add_model"),
]

# Common API keys users might want to configure
API_KEYS_INFO: List[Tuple[str, str]] = [
    ("OPENAI_API_KEY", "OpenAI (GPT-5.2, GPT-5.2-codex)"),
    ("ANTHROPIC_API_KEY", "Anthropic (Opus/Sonnet/Haiku 4.5)"),
    ("GOOGLE_API_KEY", "Google (Gemini 3 Pro)"),
    ("XAI_API_KEY", "xAI (Grok 4)"),
    ("MINIMAX_API_KEY", "MiniMax (MiniMax M2.1)"),
    ("OPENROUTER_API_KEY", "OpenRouter (100+ models)"),
]

# Key agents to highlight
KEY_AGENTS: List[Tuple[str, str, str]] = [
    ("planning-agent", "📋 Planning Agent", "Breaks down complex tasks"),
    ("qa-kitten", "🐱 QA Kitten", "Browser automation with Playwright"),
    ("security-auditor", "🛡️ Security Auditor", "Risk-based security review"),
    ("code-reviewer", "🔍 Code Reviewer", "Holistic code review"),
    ("python-programmer", "🐍 Python Programmer", "Modern Python specialist"),
]


# ============================================================================
# Gradient Banner Generator
# ============================================================================


def get_gradient_banner() -> str:
    """Generate the gradient CODE PUPPY banner.

    Returns:
        Rich markup string with gradient-colored pyfiglet banner.
    """
    try:
        import pyfiglet

        intro_lines = pyfiglet.figlet_format("CODE PUPPY", font="ansi_shadow").split(
            "\n"
        )

        # Blue to cyan to green gradient (top to bottom)
        gradient_colors = ["bright_blue", "bright_cyan", "bright_green"]

        result_lines = []
        for line_num, line in enumerate(intro_lines):
            if line.strip():
                color_idx = min(line_num // 2, len(gradient_colors) - 1)
                color = gradient_colors[color_idx]
                result_lines.append(f"[{color}]{line}[/{color}]")
            else:
                result_lines.append("")

        return "\n".join(result_lines)
    except ImportError:
        # Fallback if pyfiglet not available
        return (
            "[bold bright_cyan]╔═══════════════════════════════╗\n"
            "║        CODE PUPPY 🐶          ║\n"
            "╚═══════════════════════════════╝[/bold bright_cyan]"
        )


# ============================================================================
# Slide Content Generators
# ============================================================================


def slide_welcome() -> str:
    """Slide 0: Welcome with gradient banner.

    Returns:
        Rich markup string for the slide content.
    """
    content = get_gradient_banner()
    content += "\n\n"
    content += "[bold white]Welcome to Code Puppy! 🐶[/bold white]\n\n"
    content += "[dim]Let's get you set up for coding success![/dim]\n\n"
    content += "[cyan]This wizard will help you configure:[/cyan]\n"
    content += "  • Model subscriptions & API keys\n"
    content += "  • MCP server integrations\n"
    content += "  • Appearance customization\n"
    content += "  • Agent system overview\n\n"
    content += "[bold yellow]🎯 Navigation:[/bold yellow]\n"
    content += "[green]→[/green] or [green]l[/green]  Next slide\n"
    content += "[green]←[/green] or [green]h[/green]  Previous slide\n"
    content += "[green]↓[/green] or [green]j[/green]  Next option\n"
    content += "[green]↑[/green] or [green]k[/green]  Previous option\n"
    content += "[green]Enter[/green]    Select/proceed\n"
    content += "[green]ESC[/green]      Skip wizard\n\n"
    content += "[dim]You can always run[/dim]\n"
    content += "[cyan]/onboarding[/cyan] [dim]later![/dim]"

    return content


def slide_model_subscription(
    selected_option: int, options: List[Tuple[str, str]]
) -> str:
    """Slide 1: Model subscription selection.

    Args:
        selected_option: Index of the currently selected option.
        options: List of (id, label) tuples for display.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]📦 Model Subscription[/bold cyan]\n\n"
    content += "[white]Do you have a model subscription?[/white]\n\n"

    for i, (_, label) in enumerate(options):
        if i == selected_option:
            content += f"[bold green]▶ {label}[/bold green]\n"
        else:
            content += f"[dim]  {label}[/dim]\n"

    content += "\n\n"

    # Dynamic content based on selection
    selected_opt = options[selected_option][0] if options else None
    if selected_opt == "chatgpt":
        content += "[bold yellow]💡 ChatGPT Plus/Pro/Max[/bold yellow]\n\n"
        content += "[green]OAuth login gives you access to:[/green]\n"
        content += "  • GPT-5.2\n"
        content += "  • GPT-5.2-codex\n"
        content += "  • No API key needed!\n"
    elif selected_opt == "claude":
        content += "[bold yellow]💡 Claude Code Pro/Max[/bold yellow]\n\n"
        content += "[green]OAuth login gives you access to:[/green]\n"
        content += "  • Claude Opus 4.5\n"
        content += "  • Claude Sonnet 4.5\n"
        content += "  • Claude Haiku 4.5\n"
        content += "  • No API key needed!\n"
    elif selected_opt == "api_keys":
        content += "[bold yellow]💡 API Keys[/bold yellow]\n\n"
        content += "[green]Use your own API keys for:[/green]\n"
        content += "  • OpenAI (GPT-5.2, GPT-5.2-codex)\n"
        content += "  • Anthropic (Opus/Sonnet/Haiku 4.5)\n"
        content += "  • Google (Gemini)\n"
        content += "  • And many more!\n"
    elif selected_opt == "openrouter":
        content += "[bold yellow]💡 OpenRouter[/bold yellow]\n\n"
        content += "[green]Single API key for 100+ models:[/green]\n"
        content += "  • All major providers\n"
        content += "  • Pay-per-use pricing\n"
        content += "  • Great for exploration!\n"
    elif selected_opt == "free":
        content += "[bold yellow]💡 Free Tiers[/bold yellow]\n\n"
        content += "[green]Explore free options:[/green]\n"
        content += "  • Google Gemini (free tier)\n"
        content += "  • Groq (fast inference)\n"
        content += "  • Local with Ollama\n"
    else:
        content += "[dim][Configure later using /set or /add_model][/dim]\n"

    content += "\n\n[dim]Press → to continue[/dim]"
    return content


def slide_api_keys(model_choice: str | None) -> str:
    """Slide 2: API key setup information.

    Args:
        model_choice: User's model subscription selection from slide 1.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]🔑 API Key Configuration[/bold cyan]\n\n"

    if model_choice in ("chatgpt", "claude"):
        content += "[green]✓ You selected OAuth login![/green]\n\n"
        content += "[dim]After this wizard, we'll guide you\n"
        content += "through the OAuth authentication flow.[/dim]\n\n"
        content += "You can also add API keys for\n"
        content += "additional providers:\n\n"
    else:
        content += "[white]Common API keys to configure:[/white]\n\n"

    for key_name, description in API_KEYS_INFO:
        content += f"[cyan]{key_name}[/cyan]\n"
        content += f"  [dim]{description}[/dim]\n"

    content += "\n\n"
    content += "[bold yellow]⚙️ Configuration[/bold yellow]\n\n"
    content += "[green]Set API keys with:[/green]\n\n"
    content += "[cyan]/set OPENAI_API_KEY=sk-...[/cyan]\n\n"
    content += "[dim]Keys are stored securely in[/dim]\n"
    content += "[dim]~/.config/code_puppy/puppy.cfg[/dim]\n\n"
    content += "[green]Browse 1500+ models:[/green]\n"
    content += "[cyan]/add_model[/cyan]\n"
    content += "[dim]65+ providers available![/dim]"

    return content


def slide_mcp_servers() -> str:
    """Slide 3: MCP server information.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]🔌 MCP Servers[/bold cyan]\n\n"
    content += "[white]Extend Code Puppy with MCP![/white]\n\n"
    content += "Model Context Protocol (MCP) lets you\n"
    content += "add external tools and integrations.\n\n"
    content += "[green]Commands:[/green]\n"
    content += "  [cyan]/mcp install[/cyan] - Browse curated catalog\n"
    content += "  [cyan]/mcp add[/cyan]     - Add custom server\n"
    content += "  [cyan]/mcp list[/cyan]    - View configured servers\n"
    content += "  [cyan]/mcp status[/cyan]  - Check server health\n\n"
    content += "[bold yellow]🌟 Popular MCP Servers[/bold yellow]\n\n"
    content += "[green]@anthropic/mcp-server-github[/green]\n"
    content += "  GitHub integration\n\n"

    content += "[green]@anthropic/mcp-server-postgres[/green]\n"
    content += "  Database access\n\n"
    content += "[dim]Custom JSON configuration also supported[/dim]"

    return content


def slide_appearance() -> str:
    """Slide 4: Appearance customization.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]🎨 Appearance[/bold cyan]\n\n"
    content += "[white]Customize your Code Puppy experience![/white]\n\n"
    content += "[green]Banner Colors:[/green]\n"
    content += "  [cyan]/colors[/cyan] - Customize tool banners\n"
    content += "  Change colors for THINKING, SHELL,\n"
    content += "  READ FILE, EDIT FILE, etc.\n\n"
    content += "[green]Diff Highlighting:[/green]\n"
    content += "  [cyan]/diff[/cyan] - Syntax highlighting themes\n"
    content += "  Configure addition/deletion colors\n"
    content += "  with live preview!\n\n"
    content += "[bold yellow]🖼️ Preview[/bold yellow]\n\n"
    content += "[on blue] THINKING [/on blue] ⚡\n"
    content += "[on dark_cyan] SHELL COMMAND [/on dark_cyan] 🚀\n"
    content += "[on green] EDIT FILE [/on green] ✏️\n"
    content += "[on purple] READ FILE [/on purple] 📂\n"
    content += "[dim]All colors customizable![/dim]"

    return content


def slide_agent_system() -> str:
    """Slide 5: Agent system overview.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]🤖 Agent System[/bold cyan]\n\n"
    content += "[white]Code Puppy has specialized sub-agents![/white]\n\n"
    content += "[green]Switch agents:[/green]\n"
    content += "  [cyan]/agent[/cyan] or [cyan]/a[/cyan]\n\n"
    content += "[green]Key Agents:[/green]\n"
    for _, name, desc in KEY_AGENTS:
        content += f"  {name}\n"
        content += f"    [dim]{desc}[/dim]\n"
    content += "\n\n"
    content += "[bold yellow]🔧 Agent Tips[/bold yellow]\n\n"
    content += "[green]Create custom agents:[/green]\n"
    content += "[cyan]/agent agent-creator[/cyan]\n"
    content += "[dim]Agents are defined with JSON[/dim]\n"
    content += "[dim]in ~/.code_puppy/agents/[/dim]\n\n"
    content += "[green]Each agent has:[/green]\n"
    content += "  • Custom system prompt\n"
    content += "  • Selected tools\n"
    content += "  • Optional pinned model\n"

    return content


def slide_model_pinning() -> str:
    """Slide 6: Model pinning feature.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]📌 Model Pinning[/bold cyan]\n\n"
    content += "[white]Pin specific models to agents![/white]\n\n"
    content += "[green]Command:[/green]\n"
    content += "  [cyan]/pin_model[/cyan]\n\n"
    content += "[green]Example Multi-LLM Workflow:[/green]\n"
    content += "  [yellow]Planning:[/yellow]    Kimi k2 (thinking)\n"
    content += "  [yellow]Implement:[/yellow]  Claude Opus 4\n"
    content += "  [yellow]Testing:[/yellow]    GLM 4.7\n"
    content += "  [yellow]Review:[/yellow]     GPT-5.2-codex\n\n"
    content += "[bold yellow]🎯 Why Pin Models?[/bold yellow]\n\n"
    content += "Different models excel at\n"
    content += "different tasks:\n\n"
    content += "[green]Planning:[/green]\n"
    content += "  Deep reasoning models\n\n"
    content += "[green]Coding:[/green]\n"
    content += "  Code-specialized models\n\n"
    content += "[green]Review:[/green]\n"
    content += "  Critical analysis models\n\n"
    content += "[dim]Mix and match for best results![/dim]"

    return content


def slide_planning_agent() -> str:
    """Slide 7: Planning agent power.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]🚀 The Planning Agent[/bold cyan]\n\n"
    content += "[bold yellow]Your Secret Weapon![/bold yellow]\n\n"
    content += "The Planning Agent can:\n\n"
    content += "  ✓ Break down complex tasks\n"
    content += "  ✓ Create actionable roadmaps\n"
    content += "  ✓ Orchestrate sub-agents\n"
    content += "  ✓ Manage multi-step workflows\n\n"
    content += "[green]Try it:[/green]\n"
    content += "  [cyan]/agent planning-agent[/cyan]\n"
    content += "[dim]Then describe your project![/dim]\n\n"
    content += "[bold yellow]💡 Example Prompt[/bold yellow]\n\n"
    content += "[cyan]'Plan a REST API for a\n"
    content += "todo app with auth,\n"
    content += "database, and tests'[/cyan]\n\n"
    content += "The Planning Agent will:\n\n"
    content += "1. Analyze requirements\n"
    content += "2. Break into phases\n"
    content += "3. Create file structure\n"
    content += "4. Delegate to specialists\n"
    content += "5. Track progress\n"

    return content


def slide_model_settings() -> str:
    """Slide 8: Model settings.

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold cyan]⚙️ Model Settings[/bold cyan]\n\n"
    content += "[white]Fine-tune model behavior![/white]\n\n"
    content += "[green]Command:[/green]\n"
    content += "  [cyan]/model_settings[/cyan] or [cyan]/ms[/cyan]\n\n"
    content += "[green]Configurable Parameters:[/green]\n"
    content += "  [yellow]temperature[/yellow]    - Creativity (0.0-2.0)\n"
    content += "  [yellow]max_tokens[/yellow]     - Response length\n"
    content += "  [yellow]top_p[/yellow]          - Nucleus sampling\n"
    content += "  [yellow]presence_penalty[/yellow] - Topic diversity\n\n"
    content += "[bold yellow]🎛️ Common Settings[/bold yellow]\n\n"
    content += "[green]Precise code:[/green]\n"
    content += "  temperature: 0.0-0.3\n\n"
    content += "[green]Creative writing:[/green]\n"
    content += "  temperature: 0.7-1.0\n\n"
    content += "[green]Long outputs:[/green]\n"
    content += "  max_tokens: 4096+\n\n"
    content += "[dim]Settings persist per-session[/dim]"

    return content


def slide_complete(trigger_oauth: str | None) -> str:
    """Slide 9: Completion.

    Args:
        trigger_oauth: OAuth provider that was selected ("chatgpt"/"claude"/None).

    Returns:
        Rich markup string for the slide content.
    """
    content = "[bold green]🎉 You're All Set![/bold green]\n\n"
    content += "[white]Code Puppy is ready to help![/white]\n\n"
    content += "[bold cyan]Quick Reference:[/bold cyan]\n\n"
    content += "  [cyan]/model[/cyan]     - Switch models\n"
    content += "  [cyan]/agent[/cyan]     - Switch agents\n"
    content += "  [cyan]/set[/cyan]       - Configure settings\n"
    content += "  [cyan]/add_model[/cyan] - Browse 1500+ models\n"
    content += "  [cyan]/mcp[/cyan]       - MCP server management\n"
    content += "  [cyan]/help[/cyan]      - Full command list\n\n"
    content += "[bold yellow]Press Enter to start coding! 🐶[/bold yellow]\n"
    content += "\n"
    content += "[bold yellow]🐾 Happy Coding![/bold yellow]\n\n"
    content += "[dim]Remember:[/dim]\n"
    content += "• Be specific in prompts\n"
    content += "• Let agents read files first\n"
    content += "• Use planning for complex tasks\n"
    content += "• Check diffs before applying\n\n"
    content += "[green]Community:[/green]\n"
    content += "  GitHub: code-puppy\n"
    content += "  Discord: code-puppy\n"

    if trigger_oauth:
        content += f"\n[bold cyan]Next: {trigger_oauth.title()} OAuth[/bold cyan]"

    return content
