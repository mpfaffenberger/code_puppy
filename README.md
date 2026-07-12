<div align="center">

![Code Puppy](code_puppy.png)

# Code Puppy

**A terminal-first AI coding agent platform—open source, extensible, and delightfully unhousebroken.**

[![PyPI](https://img.shields.io/pypi/v/code-puppy?style=for-the-badge&logo=pypi)](https://pypi.org/project/code-puppy/)
[![Python](https://img.shields.io/pypi/pyversions/code-puppy?style=for-the-badge&logo=python)](https://pypi.org/project/code-puppy/)
[![License](https://img.shields.io/github/license/mpfaffenberger/code_puppy?style=for-the-badge)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/mpfaffenberger/code_puppy?style=for-the-badge&logo=github)](https://github.com/mpfaffenberger/code_puppy/stargazers)

[Documentation](https://code-puppy.dev) · [Discord](https://discord.gg/eAGdE4J7Ca) · [Changelog](https://kittylog.app/c/mpfaffenberger/code_puppy)

*No bloated IDE. No closed-source vendor trap. Just a pack of agents with shell access. What could go wrong?*

</div>

---

Code Puppy works inside your terminal and your repository. It can inspect and edit files, run commands, browse and test web apps, call specialized sub-agents, connect to MCP servers, and keep long-running work organized across sessions.

Use a hosted model, authenticate through a supported OAuth provider, connect a cloud deployment, or point Code Puppy at a local/OpenAI-compatible endpoint. The core is backed by [Pydantic AI](https://github.com/pydantic/pydantic-ai), while most advanced features are implemented as plugins instead of being welded into one enormous CLI hairball.

## Why Code Puppy?

- **Actually works on your code:** targeted file editing, repository search, shell commands, images, and browser automation.
- **Bring your own model:** OpenAI, Anthropic, Gemini, Azure, Cerebras, OpenRouter, Z.ai, Ollama, Bedrock, Azure AI Foundry, custom endpoints, OAuth integrations, and more.
- **A pack, not a singleton:** switch agents, build JSON agents, pin models per agent, and delegate work to sub-agents in parallel.
- **Built for long tasks:** autosaved sessions, branch-aware quick resume, context compaction, pruning, checkpoints, undo, and optional durable execution.
- **Extensible at every layer:** MCP, Agent Skills, Claude-compatible hooks, Markdown commands, and built-in/user/project plugins.
- **Terminal-native:** multiline editing, completion, history search, clipboard images, external editor support, direct shell mode, themes, status lines, and keyboard chords.
- **Open source and local-first:** Code Puppy itself does not require a proprietary IDE or hosted control plane. Your chosen models and integrations still have their own data policies—because networking is, regrettably, real.

## Quick start

Code Puppy requires **Python 3.11–3.14** and credentials or local access for at least one model provider.

Run the latest release without installing it permanently:

```bash
uvx code-puppy
```

Or install it as a tool:

```bash
uv tool install code-puppy
code-puppy
```

Standard `pip` installation works too:

```bash
python -m pip install code-puppy
code-puppy
```

`pup` is available as a shorter alias for `code-puppy`.

### Choose a model

On first run, use the interactive setup or open the model picker:

```text
/model
/add_model
```

You only need credentials for the provider you choose. Put API keys in your environment or `.env`, configure a model interactively, or use one of the built-in authentication flows:

```text
/chatgpt-auth          # ChatGPT/Codex OAuth
/claude-code-auth      # Claude Code OAuth
/grok-auth             # Grok OAuth
/copilot-login         # GitHub Copilot device login
/bedrock-setup         # AWS Bedrock
/foundry-setup         # Azure AI Foundry
/ollama-setup          # Ollama
```

`/add_model` browses [models.dev](https://models.dev) metadata and falls back to a bundled model database when the service is unavailable. Tool-calling support varies by model; Code Puppy warns when a selected model cannot use agent tools.

## Ways to run

```bash
# Interactive terminal UI
code-puppy

# One prompt, then exit
code-puppy -p "Find the flaky tests and fix them"

# Start with a specific agent or configured model
code-puppy --agent planning-agent --model my-model

# Resume the latest session for this path and Git branch
code-puppy --quick-resume

# Text-only mode: disable local tools and MCP
code-puppy --no-tools -p "Summarize this release note"

# Serve the Agent Client Protocol over stdio
code-puppy --acp
```

Useful flags:

| Flag | Purpose |
| --- | --- |
| `-p`, `--prompt TEXT` | Run a one-shot prompt |
| `-a`, `--agent NAME` | Select the starting agent |
| `-m`, `--model NAME` | Select the starting model |
| `-r`, `--resume PATH` | Continue a saved session |
| `-qr`, `--quick-resume [PATH]` | Resume recent work scoped to a path/Git branch |
| `--no-tools` | Disable agent tools and MCP |
| `--yolo true\|false` | Override approval behavior for this run |
| `--acp` | Start the ACP server |
| `-v`, `--version` | Print the installed version |

## What it can do

### Work with files, shells, images, and browsers

Code Puppy can:

- list and search repositories with intelligent filtering;
- read files safely and make targeted replacements;
- create and delete files with permission checks;
- execute shell commands with streaming output, timeouts, cancellation, and backgrounding;
- inspect attached or clipboard images;
- automate browsers with Playwright using accessible roles, text, labels, test IDs, XPath, screenshots, JavaScript, and reusable workflows;
- ask structured multiple-choice questions when a decision genuinely needs a human.

Prefix a prompt with `!` to run it directly in your shell without asking the model:

```text
!git status
!pytest -q
!npm run dev
```

Browser automation requires a compatible Playwright browser runtime in addition to the Python package.

### Use specialized agents

Switch agents at any time:

```text
/agent
/agent planning-agent
```

The packaged catalogue includes general coding, planning, agent creation, construction, and browser-QA agents. Plugins and projects can contribute more, so `/agent` is the authoritative list for your installation.

Agents can invoke other agents, select different models for delegated tasks, and run background forks:

```text
/fork @qa-kitten Test the checkout flow
/forks
/btw What is the likely root cause of this traceback?
```

Use `/pin_model <agent> <model>` to assign a preferred model to an agent.

### Create project or personal agents

JSON agents are discovered from:

```text
~/.code_puppy/agents/          # personal
<CWD>/.code_puppy/agents/      # project; wins on name collisions
```

Create one with the `agent-creator` agent, or add any `*.json` file manually:

```json
{
  "name": "code-reviewer",
  "display_name": "Code Reviewer",
  "description": "Reviews changes for correctness and maintainability",
  "system_prompt": [
    "You are a careful senior code reviewer.",
    "Prioritize correctness, security, and actionable feedback."
  ],
  "tools": ["list_files", "read_file", "grep"]
}
```

Agents may also declare a model, tool configuration, greeting, and bound MCP servers. Keep tool lists minimal: least privilege beats giving your documentation bot a chainsaw.

### Keep sessions under control

Sessions autosave locally. Code Puppy can resume work, compact long histories, remove selected messages, and undo the most recent agent file change.

```text
/session                   # inspect, switch, or create sessions
/autosave_load             # choose an autosaved session
/quick-resume              # resume work for the current project/branch
/compact                   # summarize or truncate old context
/prune                     # interactively remove messages
/pop                       # remove the latest message
/truncate 20               # keep the system message and recent history
/undo                      # undo the latest agent file modification
/dump_context checkpoint   # save a named snapshot
/load_context checkpoint   # load without overwriting the snapshot
```

`--resume` continues saving to the resumed session. `/load_context` treats the loaded context as a snapshot and rotates to a new autosave.

### Steer work while it runs

You do not have to watch an agent confidently sprint toward the wrong tree.

- **Steer** an active run with new instructions.
- **Queue** prompts for later execution.
- **Fork** independent sub-agent work into the background.
- **Ask `/btw`** for a side answer without derailing the main task.
- Cancel or background long-running shell commands with keyboard chords.

### Connect MCP servers

Code Puppy includes MCP server discovery, installation, configuration, lifecycle management, logs, health handling, and per-agent bindings.

```text
/mcp                        # dashboard
/mcp search github          # search the bundled catalogue
/mcp install <id>
/mcp start <name>
/mcp status [name]
/mcp logs <name> [limit]
/mcp stop <name>
```

Custom JSON agents can declare MCP bindings and whether each server should auto-start.

### Add Agent Skills

Skills are reusable instruction packages built around a `SKILL.md` file. Code Puppy searches:

```text
~/.code_puppy/skills/
<CWD>/.code_puppy/skills/
<CWD>/skills/
```

Use `/skills` to discover, install, enable, disable, and refresh Skills. Agents initially receive only Skill metadata, then activate the complete instructions when relevant to a task. See [Agent Skills](docs/AGENT_SKILLS.md) for the format and discovery rules.

### Apply project rules

Code Puppy combines coding instructions from these locations:

1. `~/.code_puppy/AGENTS.md`
2. `.code_puppy/AGENTS.md`
3. `./AGENTS.md`

`AGENT.md` and lowercase filename variants are also supported. Put formatting rules, architecture constraints, test commands, and team conventions there.

### Define commands and hooks

Create reusable slash commands as Markdown prompts in:

```text
~/.code-puppy/commands/
.claude/commands/
.github/prompts/
.agents/commands/
```

For example, `.claude/commands/review.md` becomes `/review`; any supplied arguments are appended to its prompt.

Code Puppy also supports Claude-compatible lifecycle hooks configured in `.claude/settings.json` or `~/.code_puppy/hooks.json`. Hooks can observe, block, or respond to tool and session events. Manage them with `/hooks` and `/create-hook`, and see [Hooks](docs/HOOKS.md) for details.

### Extend everything with plugins

Most advanced functionality ships as a plugin using callbacks from `code_puppy.callbacks`.

| Tier | Location | Behavior |
| --- | --- | --- |
| Built-in | `code_puppy/plugins/<name>/register_callbacks.py` | Ships with Code Puppy |
| User | `~/.code_puppy/plugins/<name>/register_callbacks.py` | Loads for every project |
| Project | `<CWD>/.code_puppy/plugins/<name>/register_callbacks.py` | Requires explicit trust |

Plugins can add agents, tools, Skills, commands, models, MCP entries, CLI flags, UI behavior, policy checks, and lifecycle handlers. Load order is built-in → user → project.

Project plugins execute repository code, so they fail closed until accepted through `/plugins`. Trust is scoped to the project path and a SHA-256 content hash; changing plugin code invalidates prior trust. Accepted plugins hot-load without a restart.

A minimal plugin looks like this:

```python
from code_puppy.callbacks import register_callback


def _on_startup() -> None:
    print("My plugin is awake. This seems fine.")


register_callback("startup", _on_startup)
```

Keep plugin runtime data outside the plugin directory so it does not invalidate its own trust hash.

## Models and integrations

Code Puppy supports several provider styles rather than locking the whole kennel to one vendor:

- OpenAI, Anthropic, Gemini, Cerebras, OpenRouter, and Z.ai APIs;
- Azure OpenAI and Azure AI Foundry;
- AWS Bedrock;
- ChatGPT/Codex, Claude Code, Grok, and GitHub Copilot authentication;
- Ollama and custom OpenAI-, Anthropic-, or Gemini-compatible endpoints;
- round-robin model groups for distributing requests;
- per-model context lengths, temperatures, timeouts, and thinking settings;
- per-agent model pinning.

Availability and tool-calling behavior depend on provider accounts, model capabilities, regions, and upstream APIs.

### ACP editor integration

Run `code-puppy --acp` to expose Code Puppy to an [Agent Client Protocol](https://agentclientprotocol.com/)-capable editor. ACP mode supports persisted sessions, streaming responses and tool calls, images, cancellation, model selection, client-provided MCP servers, delegated file/terminal access, and client-native permission prompts.

Example editor configuration:

```json
{
  "agent_servers": {
    "Code Puppy": {
      "command": "code-puppy",
      "args": ["--acp"],
      "env": {}
    }
  }
}
```

See the [ACP plugin documentation](code_puppy/plugins/acp/README.md) for supported protocol details.

### Local memory with Puppy Kennel

Puppy Kennel provides optional local SQLite/FTS5 memory across repository, agent, and user scopes. It can passively recall relevant context or expose explicit remember, recall, recent, and statistics tools.

```text
/kennel status
/kennel search dependency injection
/kennel wings
/kennel enable
/kennel disable
```

See [Puppy Kennel](code_puppy/plugins/puppy_kennel/README.md) for storage and configuration details.

### Optional durable execution

Install the DBOS extra to make durable workflow support available:

```bash
python -m pip install "code-puppy[durable]"
```

Then inspect or change its effective state:

```text
/dbos status
/dbos on
/dbos off
```

DBOS can persist workflow progress locally or to a configured database. Consult DBOS configuration before enabling its optional remote management integration.

## Terminal workflow

| Key | Action |
| --- | --- |
| `Ctrl+J` | Insert a newline |
| `F2` / `Alt+M` | Toggle multiline mode |
| `Alt+Enter` | Queue the current prompt |
| `Ctrl+R` | Search input history |
| `Ctrl+V` | Paste clipboard text or an image |
| `Ctrl+X Ctrl+E` | Edit the prompt in `$VISUAL` or `$EDITOR` |
| `Ctrl+X Ctrl+X` | Kill running shell commands |
| `Ctrl+X Ctrl+B` | Background running shell commands |

Some modified-key and clipboard behavior depends on your OS and terminal emulator. `Ctrl+X` is a chord prefix: press the second key to choose an action, or `Esc` to cancel.

Customize the UI with `/theme`, `/spinner`, `/statusline`, `/colors`, `/diff`, `/widemenu`, and `/prompt_newline`. Run `/help` for the commands registered by your current plugin set.

## Safety, privacy, and local data

Code Puppy does **not** require project-operated telemetry or a hosted IDE service. It does persist data locally so useful features do not develop goldfish memory. Depending on configuration, local state may include:

- session autosaves and named context snapshots;
- command history and configuration;
- provider credentials or OAuth tokens;
- error logs and ACP session data;
- Puppy Kennel memories;
- DBOS workflow records when installed and enabled.

Prompts, code, and tool results are sent to the model provider you configure. MCP servers, browser navigation, URL attachments, hooks, plugins, model catalogues, and other integrations may also access the network or execute local code. Their policies and behavior are not magically overwritten by a puppy logo.

Safety controls include file approvals, shell policies, destructive-command detection, force-push protection, project-plugin trust, tool-free mode, undo, and a runtime YOLO override. Review commands before approval and audit project plugins before trusting them.

For a network-isolated workflow, use a local model endpoint and disable or avoid every network-capable integration—not just the model provider.

### Configuration locations

By default, Code Puppy stores configuration and state under:

```text
~/.code_puppy/
```

When the corresponding XDG variables are set, Code Puppy uses category-specific paths below `$XDG_CONFIG_HOME/code_puppy`, `$XDG_DATA_HOME/code_puppy`, `$XDG_CACHE_HOME/code_puppy`, and `$XDG_STATE_HOME/code_puppy`.

Common files and directories include `puppy.cfg`, `extra_models.json`, `mcp_servers.json`, `agents/`, `skills/`, `contexts/`, and `autosaves/`.

## Command cheat sheet

| Area | Commands |
| --- | --- |
| Help and setup | `/help`, `/tutorial`, `/show`, `/set`, `/tools` |
| Models and agents | `/model`, `/add_model`, `/model_settings`, `/agent`, `/pin_model`, `/unpin` |
| Sessions | `/session`, `/autosave_load`, `/quick-resume`, `/compact`, `/prune`, `/pop`, `/undo` |
| Orchestration | `/plan`, `/fork`, `/forks`, `/btw`, `/steer`, `/queue` |
| Extensions | `/mcp`, `/skills`, `/plugins`, `/hooks`, `/uc` |
| Repository work | `/cd`, `/review-pr`, `/generate-pr-description` |
| Interface | `/theme`, `/spinner`, `/statusline`, `/context`, `/colors`, `/diff` |

Commands are plugin-driven and evolve faster than README tables. `/help` is the source of truth.

## Development

Clone the repository and install the development environment:

```bash
git clone https://github.com/mpfaffenberger/code_puppy.git
cd code_puppy
uv sync --dev
```

Run the checks:

```bash
uv run ruff check --fix .
uv run ruff format .
uv run pytest
```

New functionality should usually be a plugin under `code_puppy/plugins/` registered through callbacks, not another barnacle on the command-line core. Keep changes focused, test user-visible behavior, fail gracefully, and follow the repository's `AGENTS.md` guidance.

## Documentation

- [Agent Skills](docs/AGENT_SKILLS.md)
- [Hooks](docs/HOOKS.md)
- [ACP integration](code_puppy/plugins/acp/README.md)
- [Puppy Kennel memory](code_puppy/plugins/puppy_kennel/README.md)
- [Themes](code_puppy/plugins/theme/README.md)
- [Spinners](code_puppy/plugins/puppy_spinner/README.md)
- [Sub-agent panel](code_puppy/plugins/subagent_panel/README.md)
- [Azure AI Foundry](code_puppy/plugins/azure_foundry/README.md)
- [Claude Code OAuth](code_puppy/plugins/claude_code_oauth/README.md)

## License

Code Puppy is released under the [MIT License](LICENSE).
