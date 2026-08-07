# Model System & MCP Integration

> Part of the `code-puppy-agent` skill. Read this when working with model
> selection/config, or external MCP tool servers. See `SKILL.md` for the
> overview and the full reference map.

---

## Model System

### ModelFactory (`model_factory.py`)

Resolves a model-name string into a pydantic-ai `Model` object.
Supports providers: OpenAI, Anthropic, Gemini, Cerebras, OpenRouter,
Azure, and custom OpenAI/Anthropic/Gemini-compatible endpoints.

### Model configuration

Models are defined in three places (merged at runtime):

1. **Built-in defaults** — hardcoded in the factory
2. **`~/.code_puppy/extra_models.json`** — user-defined custom models
3. **Plugin injection** — `load_models_config` callback returns a dict

Example `extra_models.json`:
```json
{
  "my-model": {
    "type": "custom_openai",
    "name": "gpt-4o",
    "custom_endpoint": {
      "url": "https://api.example.com/v1",
      "api_key": "$MY_API_KEY"
    },
    "context_length": 128000
  }
}
```

### Model types

| Type | Provider |
|------|----------|
| `openai` / `openai_responses` | OpenAI |
| `anthropic` | Anthropic (Claude) |
| `gemini` | Google Gemini |
| `cerebras` | Cerebras (via CerebrasProvider) |
| `custom_openai` | Any OpenAI-compatible endpoint |
| `custom_anthropic` | Anthropic-compatible endpoint |
| `round_robin` | Cycle through N models (rate-limit mitigation) |
| Plugin types | Registered via `register_model_type` callback |

### Model selection precedence

For any agent: **runtime override > agent-pinned model > agent's `model`
field (JSON agents) > global model name**.

The global model is set via `/model` and stored in config.

---

## MCP Integration

### MCP Manager (`mcp_/manager.py`)

Code Puppy manages external MCP (Model Context Protocol) servers that
provide additional tools to agents. Key components:

- **Registry** (`mcp_/registry.py`) — server definitions (stdio/SSE/streamable-http)
- **Manager** (`mcp_/manager.py`) — lifecycle: start, stop, health checks
- **Agent bindings** (`mcp_/agent_bindings.py`) — which agents get which servers
- **Circuit breaker** (`mcp_/circuit_breaker.py`) — auto-disables flaky servers

### How MCP servers attach to agents

Servers can be:
1. **Globally started** — available to all agents
2. **Agent-bound** — declared in a JSON agent's `mcp_servers` field, or
   bound via the `/mcp bind` menu
3. **Auto-started** — bound servers with `auto_start: true` start when the
   agent runs

The `pre_mcp_autostart` hook fires before auto-start, letting plugins
refresh tokens or mint credentials.

### Managing MCP servers

Use `/mcp` in the TUI:
- `/mcp list` — show configured servers
- `/mcp start <name>` / `/mcp stop <name>`
- `/mcp status` — health dashboard
- `/mcp bind` — attach servers to agents

### MCP servers as skill providers — a known gap, not yet implemented

Skills today are discovered only by filesystem scan (see
`SKILLS_SYSTEM.md`) or via the `register_skills` callback. There is
currently **no** mechanism for a bound MCP server to advertise skills of
its own (e.g. a hypothetical `skill_provider` capability exposing
`list_skills`/`get_skill`/`search_skills`) — skills served that way would
just look like ordinary tool results, not first-class skills appearing in
`/skills list` or `activate_skill`-able. If you're evaluating whether to
build this, that's new platform work, not something `namespace_skill_search`
or the existing skill-discovery code already covers.
