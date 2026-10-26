---
name: sandbox-basics
description: How this Docker sandbox is put together — governed egress, proxy-managed keys, uv tooling, and where Code Puppy config lives. Use when a command fails on network access, credentials, or missing tools.
---

# Sandbox basics

- You are the `agent` user in a Docker sandbox. Your Code Puppy config
  is in `~/.code_puppy/`; the project workspace is a separate mount.
- Egress is allow-list based. A blocked host fails fast: report the
  exact hostname and why you need it so the user can extend the policy
  (`sbx policy`), instead of working around it.
- Provider keys (`META_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`, `OPENROUTER_API_KEY`) contain placeholders. The host
  proxy swaps in the real key only for that provider's API domain. Code
  that sends a key anywhere else will fail authentication by design.
  `meta-*` models come from the `meta_oauth` plugin; `/meta-status`
  shows which credential source is active.
- Install Python tools with `uvx <tool>` (ephemeral) or
  `uv tool install <tool>` (persistent). PyPI egress is allowed.
- Sandbox config is seeded at creation from the `code-puppy-config`
  kit. Edits you make under `~/.code_puppy/` last for this sandbox's
  lifetime; durable changes belong in the kit on the host.
