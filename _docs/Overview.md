# Code Puppy

## What Is Code Puppy?

Code Puppy is an AI-powered code generation agent that runs entirely in your terminal. Think of it as having a clever, slightly sassy coding assistant right in your command line — no IDE required. It understands programming tasks, generates high-quality code, edits files, runs shell commands, and explains its reasoning as it works.

Unlike traditional IDE-based AI tools like Cursor or Windsurf, Code Puppy is fully open-source and gives you complete control over which AI models you use. You can connect it to OpenAI, Anthropic, Google Gemini, Cerebras, or any of 65+ providers — even run models locally for full privacy. There's zero telemetry, zero data collection, and zero corporate strings attached.

Code Puppy is for developers who prefer the terminal, want model flexibility, and value privacy. Whether you're fixing a bug, scaffolding a new project, or reviewing code, Code Puppy brings powerful AI assistance to your workflow without leaving the command line.

## Key Features

| Feature | Description |
|---------|-------------|
| Multi-Model Support | Use OpenAI, Anthropic, Google Gemini, Cerebras, and 65+ providers — switch anytime |
| Agent System | Switch between specialized agents for different tasks (coding, planning, reviewing) |
| Custom Agents | Create your own agents with simple JSON files — no coding required |
| MCP Servers | Extend functionality with external tools (GitHub, databases, Slack, and more) |
| Agent Skills | Load reusable skill packs to teach the agent new tricks on demand |
| Session Management | Auto-save conversations, resume later, compact history when it gets long |
| Round Robin Models | Distribute requests across multiple API keys to overcome rate limits |
| Custom Commands | Define reusable prompt commands with simple Markdown files |
| Scheduler | Automate recurring prompts on a scheduleoard Support | Paste screenshots and images directly into your conversation |
| Full Privacy | Zero telemetry, zero tracking — your code stays yours |
| AGENT.md Rules | Define project-specific coding standards the agent follows automatically |

## Requirements

> [!NOTE]
> Only what you need as an end user — not build tools or development dependencies.

| Requirement | Details |
|-------------|----------|
| Python | 3.11 or newer |
| OS | macOS, Linux, or Windows |
| Package Manager | [UV](https://docs.astral.sh/uv/) (recommended) or pip |
| API Key | At least one AI provider key (OpenAI, Anthropic, Google, Cerebras, etc.) — or use OAuth with ChatGPT/Claude subscriptions |

## Getting Started

```bash
# Install UV if you don't have it (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run Code Puppy (installs automatically)
uvx code-puppy

# Or run with the interactive tutorial
uvx code-puppy -i
```

On Windows:
```powershell
# Install UV (PowerShell as Admin)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Run Code Puppy
uvx code-puppy
```

You can also use the short alias `pup` instead of `code-puppy`.

## Next Steps

- [Installation Guide](Getting-Started/Installation) — Detailed setup instructions
- [Quick Start Tutorial](Getting-Started/QuickStart) — Your first coding task in 5 minutes
- [Feature Guides](Guides/_Index) — How to use specific features
- [Command Reference](Reference/Commands) — All slash commands at a glance
