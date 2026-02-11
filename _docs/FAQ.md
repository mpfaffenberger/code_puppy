# Frequently Asked Questions

## Getting Started

### How do I install Code Puppy?
See the [Installation Guide](Getting-Started/Installation).

### What are the system requirements?
You need Python 3.11+ and at least one AI provider API key (or a ChatGPT/Claude subscription for OAuth). See [Overview](Overview) for full details.

### Do I need to pay for Code Puppy?
No. Code Puppy itself is 100% free and open source. You only pay for the AI provider you choose to connect (OpenAI, Anthropic, etc.). Some providers offer free tiers.

## Common Tasks

### How do I switch AI models?
Use `/model` to open the interactive model picker, or `/model <name>` to switch directly. See [Guide: Switch Models](Guides/SwitchModels).

### How do I add a new AI provider?
Use `/add_model` to browse 65+ providers and add models interactively. See [Guide: Add Models](Guides/AddModels).

### How do I switch agents?
Use `/agent` to see and select available agents, or `/agent <name>` to switch directly. See [Guide: Use Agents](Guides/UseAgents).

### Can I use Code Puppy without an internet connection?
Yes, if you run a local model server (e.g., Ollama, vLLM, llama.cpp). Configure it in `~/.code_puppy/extra_models.json`. With local models, zero data leaves your network.

## Troubleshooting

### I'm getting "API key not found" errors

**Cause:** The AI provider you selected requires an API key that isn't set.

**Fix:**
1. Set the appropriate environment variable (e.g., `export OPENAI_API_KEY=sk-...`)
2. Or use `/set` to configure it: `/set OPENAI_API_KEY=sk-...`
3. See [Environment Variables](Reference/EnvVars) for the full list

### Code Puppy isn't responding to my prompt

**Try these steps:**
1. Check your API key is valid and has credits
2. Try switching to a different model: `/model`
3. Check your internet connection
4. Use `/show` to see current configuration

### My conversation is getting slow or hitting context limits

**Cause:** Long conversations consume more tokens and may exceed model context windows.

**Fix:**
1. Use `/compact` to summarize and shrink the conversation history
2. Use `/truncate 20` to keep only the 20 most recent messages
3. Start a new session with `/session new`
4. See [Understanding Context and Compaction](Concepts/ContextCompaction)

> [!TIP]
> If none of the above works, check the [Discord community](https://discord.gg/eAGdE4J7Ca) or [file an issue on GitHub](https://github.com/mpfaffenberger/code_puppy/issues).

## Configuration

### How do I change settings?
Use `/set <key> <value>`. Run `/set` with no arguments to see all available keys. See [Configuration Reference](Reference/ConfigReference).

### Where are my settings stored?
In `~/.code_puppy/puppy.cfg` by default. Code Puppy also supports XDG Base Directory paths if the corresponding environment variables are set.

### What do the default settings do?
Run `/show` to see all current settings and their values. See [Configuration Reference](Reference/ConfigReference) for what each setting controls.

## Advanced

### Can I create my own agents?
Yes! Create JSON files in `~/.code_puppy/agents/` or use the built-in Agent Creator (`/agent agent-creator`). See [Guide: Create Custom Agents](Guides/CreateCustomAgents).

### Can I extend Code Puppy with external tools?
Yes, via MCP (Model Context Protocol) servers. Use `/mcp install` to browse the catalog. See [Guide: MCP Servers](Guides/MCPServers).

### How do Agent Skills work?
Skills are reusable instruction packs that give agents specialized knowledge. Place them in `~/.code_puppy/skills/` and manage with `/skills`. See [Guide: Agent Skills](Guides/AgentSkills).
