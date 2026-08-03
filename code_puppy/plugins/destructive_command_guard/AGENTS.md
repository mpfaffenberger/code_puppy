# AGENTS.md — Destructive Command Guard

> Scope: **this plugin only** (`code_puppy/plugins/destructive_command_guard/`).
> It intercepts destructive shell commands (`rm -rf /`, `git reset --hard`,
> `docker prune`, `diskpart`, ...) and prompts/blocks before they run.
> Force-push blocking is a **separate sibling plugin** (`force_push_guard/`) —
> out of scope here, but the two share the allowlist (see below).

## What lives here

| File | Responsibility |
|------|----------------|
| `detector.py` | Pure-regex detection. No LLM, no I/O, no config reads. Returns a `DestructiveCommandMatch(pattern_name, description)` or `None`. |
| `register_callbacks.py` | The `run_shell_command` hook: legacy disable flag → detect → allowlist → interactive prompt (TTY) / hard-block (non-interactive). |
| `__init__.py` | Docstring inventory of covered patterns. Keep it in sync when you add patterns. |

Config knobs live in `code_puppy/config.py` (NOT here):
- `disable_dangerous_command_guard` — legacy all-or-nothing kill-switch (also disables force-push guard). `get_disable_dangerous_command_guard()`.
- `dangerous_command_guard_allow` — granular per-pattern allowlist, shared with the force-push guard. `get_dangerous_command_guard_allowlist()` / `is_dangerous_command_allowlisted()`.

Tests: `tests/plugins/test_destructive_command_detector.py` (detector) and
`tests/plugins/test_command_guard_allowlist.py` (allowlist + callback).

## Callback precedence (do not reorder without cause)

1. `get_disable_dangerous_command_guard()` → if True, allow (full legacy bypass).
2. `detect_destructive_command(command)` → if `None`, allow.
3. `is_dangerous_command_allowlisted(match.pattern_name)` → if True, allow silently.
4. Interactive TTY → prompt the user (approve / reject).
5. Non-interactive (CI, sub-agent, piped) → **hard-block** with an error dict.

Return `None` to allow, `{"blocked": True, "reasoning": ..., "error_message": ...}` to deny.

## Recipe: add a new destructive pattern

1. **Add the regex tuple** to the right list in `detector.py`
   (`_UNIX_DESTRUCTIVE_PATTERNS`, `_POWERSHELL_...`, or `_CMD_...`):
   `(re.compile(r"..."), "short-name", "human description")`.
   Order matters — **first match wins**; put more-specific patterns first.
2. **Add a pre-filter substring** to `_PREFILTER_SUBSTRINGS` if your keyword
   isn't already there. Detection bails early unless a cheap substring hits,
   so a missing prefilter = your pattern never fires.
3. **Add tests** in `tests/plugins/test_destructive_command_detector.py`.
   Use the `_hits(cmd)` / `_miss(cmd)` helpers (they prefix `&& ` so
   `_is_real_command` passes). Add at least one positive AND one
   false-positive/negative case (e.g. the same word inside `echo '...'`).
4. **Update the `__init__.py` docstring** inventory.
5. `ruff check --fix` and `ruff format .`, then run the tests.

## Non-negotiable conventions

- **`pattern_name` is an API contract.** It is (a) shown to the user and
  (b) the exact key users put in `dangerous_command_guard_allow`. Renaming one
  silently breaks people's allowlists. Treat renames as breaking changes.
- **Detector stays pure.** No config reads, no `emit_*`, no network, no
  filesystem. All side effects belong in `register_callbacks.py`. This keeps
  the detector trivially unit-testable and fast.
- **False positives are worse than they look.** A too-greedy regex trains
  users to reflexively approve prompts, which defeats the guard. Anchor
  carefully (`\b`, end-of-string `$`), and always add a `_miss` test proving
  safe look-alikes (`rm -i`, `git reset --soft`, `echo 'rm -rf /'`) don't fire.
- **Fail closed on ambiguity, fail open on our own errors.** If a command
  looks destructive, block/prompt. But never let the guard crash the app —
  the `run_shell_command` hook must degrade gracefully.
- **Cross-platform.** Patterns cover Unix, PowerShell, and CMD. New coverage
  should consider all three where the operation exists.
- **Emojis in prompt strings are intentional** in `register_callbacks.py`
  (the panel UI). Don't strip them when editing nearby lines.
- **600-line hard cap per file**; split into submodules if a file outgrows it.
- Run `ruff check --fix` and `ruff format .` before committing.
- **Never add a Claude / AI co-author trailer to commits.**

## Quick test commands

```bash
# detector + allowlist + callback behavior
pytest tests/plugins/test_destructive_command_detector.py \
       tests/plugins/test_command_guard_allowlist.py -o addopts="" -q
```
