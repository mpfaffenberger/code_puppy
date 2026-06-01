# hermes_governance

Hermes-style self-improving-skills governance, ported into Code Puppy as a
plugin. Recreates the budget gate, skill nudges, the `skill_manage` loop, and
the skill curator from NousResearch's Hermes agent.

**Enforcement is opt-in.** The plugin loads quiet and does nothing until armed.

## Control (via `/set` — no standalone slash command)

Every `puppy.cfg` key is exposed in `/set` tab-completion automatically, so
governance is controlled through config:

```
/set hermes_governance_enabled=true     # arm the gate + nudges
/set hermes_governance_enabled=false    # disarm
/set hermes_governance_onboarding_budget=5
/set hermes_governance_max_budget=90
```

## State rides *inside* the conversation

The defining property of this plugin: governance state is **not** kept in
module memory (which dies on restart) or a side file (which doesn't follow a
resumed conversation). Instead it lives in a **carrier message** embedded in
`agent._message_history`:

- pickled with the session on autosave, restored on `--resume`;
- re-pinned into the protected tail every model call via a history processor
  (attached through the `wrap_pydantic_agent` hook), so **context compaction
  never summarises it away**.

This mirrors how Hermes persists durable memory — re-injected each turn, not
held in process memory.

## What it does (when armed)

| Component | Hook(s) | Behaviour |
|-----------|---------|-----------|
| **Budget gate** | `pre_tool_call` / `post_tool_call` | First `onboarding` (5) non-exempt tool calls are free. The next is **blocked** until a *successful* skill action. After that the cap expands to `max` (90). The spent counter **regenerates each turn** (see below), so the cap is a per-turn allowance, not a lifetime lockout. |
| **Carrier** | `wrap_pydantic_agent` | Syncs live state <-> a conversation-embedded carrier; survives compaction, resume, restart. Also self-attaches `skill_manage` to the agent so the gate always has a working escape hatch. |
| **Skill nudges** | `post_tool_call` / `user_prompt_submit` | Every `nudge_interval` (6) calls, a `[SKILL REMINDER]` is injected — but only once the agent has actually **acted** (pure read/analysis turns are never nagged). Post-acting turns get a verify/document nudge. Counters persist in the carrier. |
| **skill_manage** | `register_tools` + `wrap_pydantic_agent` | `create` / `patch` / `view` / `list` / `archive` skills under `~/.code_puppy/skills/`. A **successful** call **unlocks** the budget. Failed skill calls do not unlock and are not recorded as usage. |
| **Curator** | `session_end` | Archives stale agent-created skills (lifecycle active->stale->archived). Never deletes (archive is recoverable), skips pinned + user-authored skills. Only **successful** skill activations feed its `skill_usage` telemetry. |
| **Task enforcement** | `pre_tool_call` | Optional, default **off**. Blocks tools when no task is active. Fails OPEN by default if the task system is unavailable (configurable). |

Exempt tools (never gated, and the escape hatch): the skill tools
(`skill_manage`, `activate_skill`, `list_or_search_skills`), all `task_*`
tools, and **read-only exploration** (`read_file`, `list_files`, `grep`,
`glob`, `find`) — so understanding a codebase never burns the budget; only
mutating/acting calls count.

### Budget semantics (important)

The budget is a **per-turn** allowance by default. At the start of each turn the
spent counter (`used`) is reset to zero, while the one-way `unlocked` transition
and the curator's `skill_usage` telemetry persist in the carrier. This avoids a
monotonic lifetime cap that would eventually lock a long-running agent out for
good. Set `hermes_governance_regenerate_each_turn=false` for the old
lifetime-cap behaviour.

## Config keys

| Key | Default | Meaning |
|-----|---------|---------|
| `hermes_governance_enabled` | `false` | Master arm switch |
| `hermes_governance_onboarding_budget` | `5` | Free calls before the gate |
| `hermes_governance_max_budget` | `90` | Per-turn cap after unlock |
| `hermes_governance_nudge_interval` | `6` | Calls between skill reminders |
| `hermes_governance_regenerate_each_turn` | `true` | Reset `used` each turn (per-turn vs lifetime cap) |
| `hermes_governance_task_enforcement` | `false` | Require an active task |
| `hermes_governance_task_enforcement_fail_open` | `true` | Allow tools if the task system is unavailable |
| `hermes_governance_stale_after_days` | `14` | Inactivity before a skill is stale |
| `hermes_governance_archive_after_days` | `45` | Inactivity before auto-archive |
| `hermes_governance_pinned_skills` | `[]` | Skills the curator never touches |

## How blocking works

`pre_tool_call` returns `{"blocked": True, "error_message": "[BLOCKED] ..."}`.
`code_puppy/pydantic_patches.py` converts that into a clean `ERROR:` tool result
so the model sees the policy message and reacts gracefully (no crash).
