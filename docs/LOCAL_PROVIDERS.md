# 🐶 Using Your Local CLI Tools as Code Puppy Providers

Code Puppy can drive the AI CLIs you already have installed — **Ollama**,
**Claude Code**, and the **Gemini / Antigravity CLI** — as interchangeable
model providers, all switchable from a single `/model` picker. In most cases
you **don't need to paste any API keys**: Code Puppy reuses the logins those
tools already set up on your machine.

This guide covers all three.

---

## 1. Ollama (local models, no key)

[Ollama](https://ollama.com) serves models locally over an OpenAI-compatible
API at `http://localhost:11434`. Code Puppy has a built-in `ollama` model type.

**Prereqs:** `ollama serve` running, and at least one *tool-capable* model
pulled. Older models like `llama3:8b` do **not** support function calling and
will fail on agent tasks — prefer `llama3.1`, `qwen2.5`, `mistral-nemo`, etc.

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5:7b
```

Add them to `~/.code_puppy/extra_models.json`:

```json
{
  "ollama-llama3.1": {
    "type": "ollama",
    "name": "llama3.1:8b",
    "description": "Local Ollama: Llama 3.1 8B (supports tools)",
    "context_length": 131072
  },
  "ollama-qwen2.5": {
    "type": "ollama",
    "name": "qwen2.5:7b",
    "description": "Local Ollama: Qwen 2.5 7B (supports tools)",
    "context_length": 32768
  }
}
```

The `ollama` type auto-detects `OLLAMA_HOST` and falls back to
`localhost:11434`. No API key needed (a placeholder is sent automatically).

### Optional: an Ollama pool

Rotate across several local models with a round-robin pool so you can switch
the whole group with one name:

```json
{
  "ollama-pool": {
    "type": "round_robin",
    "description": "Local Ollama pool: rotates Llama 3.1 and Qwen 2.5",
    "models": ["ollama-llama3.1", "ollama-qwen2.5"],
    "rotate_every": 1
  }
}
```

```text
/model ollama-pool
```

---

## 2. Claude Code (reuse your Claude CLI / claude.ai login)

The built-in `claude_code_oauth` plugin runs its own browser OAuth flow and
discovers every Claude model your account can use — no API key.

Inside Code Puppy:

```text
/claude-code-auth
```

Complete the browser sign-in. Models then appear prefixed as
`claude-code-claude-sonnet-4-6`, `claude-code-claude-opus-4-8`, etc.

```text
/claude-code-status     # verify auth + list discovered models
/model claude-code-claude-sonnet-4-6
```

Tokens refresh automatically in the background. See
[`code_puppy/plugins/claude_code_oauth/`](../code_puppy/plugins/claude_code_oauth/)
for details.

---

## 3. Gemini / Antigravity (reuse your Gemini CLI login)

> **"Antigravity" = Gemini.** Google has been rebranding its Gemini CLI
> tooling as *Antigravity*. Both write OAuth credentials to `~/.gemini/`, so
> the same plugin handles either name.

The `gemini_oauth` plugin reuses the token the **Gemini CLI** stores at
`~/.gemini/oauth_creds.json` and calls the Code Assist API — **no API key**,
often on a free tier.

**Prereq:** sign in to the Gemini CLI once so the token file exists:

```bash
gemini    # complete the browser sign-in
```

Add Gemini models to `~/.code_puppy/extra_models.json`:

```json
{
  "antigravity-flash": {
    "type": "gemini_oauth",
    "name": "gemini-2.5-flash",
    "description": "Gemini 2.5 Flash via Code Assist OAuth",
    "context_length": 1000000
  },
  "antigravity-pro": {
    "type": "gemini_oauth",
    "name": "gemini-2.5-pro",
    "description": "Gemini 2.5 Pro via Code Assist OAuth",
    "context_length": 1000000
  }
}
```

```text
/model antigravity-flash
```

Full details and troubleshooting:
[`code_puppy/plugins/gemini_oauth/README.md`](../code_puppy/plugins/gemini_oauth/README.md).

---

## Switching between them

Once configured, everything lives in one picker:

```text
/model                       # interactive picker across ALL providers
/model ollama-pool           # local
/model antigravity-flash     # Gemini via CLI OAuth
/model claude-code-claude-sonnet-4-6   # Claude via CLI OAuth
```

The active model is saved to `~/.code_puppy/puppy.cfg` and restored next launch.

## Notes

- `extra_models.json` lives in `~/.code_puppy/`, **not** in the repo — your
  model list is personal and never committed.
- All providers get the **same tools** when running as the main agent; tool
  access depends on the active *agent*, not the model.
- Editable installs (`pip install -e .`) pick up source changes on the next
  launch — a running session must be restarted to see them.
