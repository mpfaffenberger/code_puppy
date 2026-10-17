# Global Code Puppy rules (sandbox)

These are your user-level rules, seeded by the `code-puppy-config` mixin
into `~/.code_puppy/AGENTS.md`. Project rules in the workspace
(`AGENTS.md` or `.code_puppy/AGENTS.md`) still apply on top of them.

- You run in an isolated Docker sandbox with governed network egress.
  When a host is unreachable, say which host you needed instead of
  retrying or silently degrading.
- Provider API keys are proxy-managed placeholders. Never echo them into
  files, commits, or tool arguments.
- Prefer `uv`/`uvx` for Python work. Do not modify anything under
  `~/.code_puppy/plugins/` with file tools.
- Verify changes with the project's own tests before reporting done.
