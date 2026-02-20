# How to Switch and Use Agents

## What You'll Learn
By the end of this guide, you'll be able to browse available agents, switch between them, pin specific models to agents, and clone agents for customization.

## Prerequisites
- Code Puppy installed and running (see [Installation](../Getting-Started/Installation))
- At least one model configured (see [Configuration](../Getting-Started/Configuration))

## Quick Version

```
/agent                    # Open the interactive agent picker
/agent code-puppy         # Switch directly to an agent by name
/a planning-agent         # Short alias for /agent
```

## What Are Agents?

Agents are specialized personalities within Code Puppy, each with their own expertise, system prompt, and set of tools. While the default **Code-Puppy** agent is a general-purpose coding assistant, other agents are tuned for specific tasks like code review, security auditing, test planning, or project planning.

When you switch agents, your conversation history is preserved per-agent — so you can switch away and come back without losing context.

## Available Agents

Code Puppy ships with several built-in agents:

| Agent | Name | Description |
|-------|------|-------------|
| Code-Puppy 🐶 | `code-puppy` | The default all-purpose coding assistant |
| Planning Agent 📋 | `planning-agent` | Breaks down complex tasks into actionable steps and execution roadmaps |
| Code Reviewer 🛡️ | `code-reviewer` | Holistic reviewer for bugs, vulnerabilities, performance, and design debt |
| Python Programmer 🐍 | `python-programmer` | Modern Python specialist (async, data science, web frameworks, type safety) |
| QA Expert 🐾 | `qa-expert` | Risk-based QA planner for coverage, automation, and release readiness |
| QA Kitten 🐱 | `qa-kitten` | Browser automation and testing using Playwright with visual analysis |
| Terminal QA 🖥️ | `terminal-qa` | Terminal and TUI application testing with visual analysis |
| Security Auditor 🛡️ | `security-auditor` | Risk-based security auditor with actionable remediation guidance |
| Prompt Reviewer 📝 | `prompt-reviewer` | Analyzes prompt quality, clarity, specificity, and effectiveness |
| Scheduler Agent 📅 | `scheduler-agent` | Create and manage scheduled automated tasks |
| Agent Creator 🏗️ | `agent-creator` | Helps you create new custom JSON agent configurations |
| Helios ☀️ | `helios` | The Universal Constructor — creates tools and capabilities on the fly |

Additionally, there are **language-specific reviewers** (Python, JavaScript, TypeScript, Go, C, C++) and **Pack agents** (an advanced multi-agent orchestration system).

> [!NOTE]
> **Pack agents** (Pack Leader, Bloodhound, Husky, Shepherd, Terrier, Watchdog, Retriever) are hidden by default. To enable them, set `enable_pack_agents` to `true` in your configuration.
>
> **Helios** requires the Universal Constructor to be enabled (it is enabled by default).

## Detailed Steps

### 1. Browse Agents with the Interactive Picker

Type `/agent` (with no arguments) to open the interactive agent picker:

```
/agent
```

This opens a split-panel terminal UI:
- **Left panel** — List of all available agents, with the current agent marked
- **Right panel** — Details about the highlighted agent (name, description, pinned model, status)

**Navigation keys:**

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate through agents |
| ← / → | Page through agents (if more than 10) |
| Enter | Select the highlighted agent and switch to it |
| P | Pin a model to the highlighted agent |
| C | Clone the highlighted agent |
| D | Delete a cloned agent |
| Ctrl+C | Cancel and close the picker |

### 2. Switch to an Agent Directly

If you already know the agent name, switch directly:

```
/agent planning-agent
```

Or use the short alias:

```
/a code-reviewer
```

You should see:
```
✓ Switched to agent: Code Reviewer 🛡️
Holistic reviewer hunting bugs, vulnerabilities, perf traps, and design debt
```

> [!TIP]
> Agent names are case-insensitive. `/agent Planning-Agent` and `/agent planning-agent` both work.

### 3. Pin a Model to an Agent

By default, every agent uses whatever model you have currently active. You can **pin** a specific model to an agent so it always uses that model, regardless of your global model setting.

To pin a model:

1. Open the agent picker with `/agent`
2. Navigate to the agent you want to configure
3. Press **P** to open the model picker
4. Select the model to pin

Once pinned, the agent picker shows the pinned model next to the agent name with an arrow (→).

To **unpin** a model (revert to the default), follow the same steps and select **(unpin)** from the model list.

> [!TIP]
> Pinning is great when you want your code reviewer to always use a powerful reasoning model while your general coding agent uses a faster, cheaper model.

### 4. Clone an Agent

Cloning creates a copy of an agent that you can customize independently:

1. Open the agent picker with `/agent`
2. Navigate to the agent you want to clone
3. Press **C**

You should see:
```
✓ Cloned 'code-puppy' to 'code-puppy-clone-1'.
```

The clone is saved as a JSON file in your agents directory and appears in the agent list immediately. You can then:
- Pin a different model to the clone
- Edit the clone's JSON file to customize its system prompt, tools, or description

> [!NOTE]
> Clone files are stored in your Code Puppy data directory under the `agents/` folder (typically `~/.local/share/code-puppy/agents/` on Linux/macOS or the equivalent on your platform).

### 5. Delete a Cloned Agent

To remove a clone you no longer need:

1. Open the agent picker with `/agent`
2. Navigate to the clone (clones have names ending in `-clone-N`)
3. Press **D**

> [!WARNING]
> You can only delete cloned agents, not built-in ones. You also cannot delete the agent that is currently active — switch to a different agent first.

### 6. Set a Default Agent

By default, Code Puppy starts with the `code-puppy` agent. You can change the default startup agent using the configuration:

```
/set default_agent planning-agent
```

This sets which agent loads when you start a new Code Puppy session.

> [!NOTE]
> Each terminal session remembers which agent you last switched to. The `default_agent` setting is only used when opening a brand-new session.

## How Agent Switching Works

When you switch agents:

1. **Your current conversation history is saved** for the agent you're leaving
2. **A new auto-save session is created** so your work is preserved
3. **The new agent loads** with its own system prompt, tools, and any previously saved conversation history
4. If the new agent has a **pinned model**, that model is used; otherwise, the global model applies

This means you can freely switch between agents during a work session without losing any context.

## Example

**Scenario:** You're writing code and want a review before committing.

```
> Write a REST API endpoint for user registration

... (Code Puppy writes the code) ...

/agent code-reviewer

> Review the user registration endpoint I just wrote in app/routes/auth.py

... (Code Reviewer analyzes the code) ...

/agent code-puppy

> Apply the security fixes the reviewer suggested
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Agent not found | Typo in agent name | Run `/agent` with no args to see all available agent names |
| Pack agents not showing | Pack agents are disabled by default | Run `/set enable_pack_agents true` |
| Helios not showing | Universal Constructor is disabled | Run `/set enable_universal_constructor true` |
| Can't delete an agent | It's a built-in agent or currently active | Only clones can be deleted; switch to another agent first |
| Pinned model not taking effect | Agent needs to reload | The agent reloads automatically when you pin — if issues persist, switch away and back |

## Related Guides
- [How to Create Custom Agents](CreateCustomAgents) — Build your own agent from scratch
- [How to Switch Models](SwitchModels) — Change which AI model powers your agents
- [How to Add Models from the Catalog](AddModels) — Get more models to pin to agents
