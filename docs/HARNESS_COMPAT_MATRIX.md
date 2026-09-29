# Harness ↔ Code Puppy Feature Compatibility Matrix

Which `pydantic-ai-harness` Capabilities can replace redundant code in Code
Puppy? Originally swept 2025-08-19; refreshed 2026-09-29 against
`pydantic-ai-harness[code-mode]==0.35.0` (a direct dependency) and
`pydantic-ai-slim==2.51.0`.

**Precedent:** `code_puppy/agents/_compaction.py` already ran this playbook:
~600 lines of hand-rolled compaction deleted, replaced by
`pydantic_ai_harness.compaction` (`FallbackCompaction`, `SlidingWindowCompaction`,
`SummarizingCompaction`, `compact_now`) with a thin config-glue layer. That's
the template every row below is measured against: **harness owns the
model-facing mechanics, Code Puppy keeps the TUI/config glue.**

Tiers: **Tier 0** adopted · **Tier 1** adopt now · **Tier 2** adopt with glue ·
**Tier 3** different philosophy, evaluate · **N/A** new feature, nothing
redundant to delete · **Keep ours** app/UI concern, out of harness scope

## Tier 0: Already adopted

| Capability | Code Puppy side | Notes |
|---|---|---|
| `FallbackCompaction` / `SlidingWindowCompaction` / `SummarizingCompaction` | `agents/_compaction.py` (11 KB glue), `capabilities/compaction.py` (`HistoryCompaction`) | Done. Manual `/compact` + `/truncate` drive harness `compact_now`; `HistoryCompaction` wraps it with before/completed/failed events. |
| `ToolOutputLimits` (Spill → Truncate) | `agents/_output_limits.py` (3 KB glue) | Done. Replaced `_history.filter_huge_messages`. Lossless spill to `~/.code_puppy/tool_output_spill` (7-day TTL), read back via `read_tool_result`. Threshold from `tool_output_limit_chars`. |
| `ClampOversizedMessages` | `agents/_output_limits.py` | Done. Head/tail-clamps runaway response parts at 50k tokens instead of dropping the message. |
| `CodeMode` | `agents/_code_mode.py`, `events/bridge.py`, `messaging/speculation_stats.py` | Done. Speculative code mode, surfaced in the TUI via the event bridge. |

## Tier 1: Adopt now (high fit, low UI entanglement)

| Capability | Redundant Code Puppy code | Why it fits | Watch out for |
|---|---|---|---|
| `RepoContext` | `agents/_builder.py` AGENTS.md discovery + `_truncate_agents_md` (~150 lines) + `config.get_agents_md_max_chars` | Loading AGENTS.md/AGENT.md is exactly RepoContext's job. | Verify parity: global `~/.code_puppy/AGENTS.md`, the `.code_puppy/AGENTS.md`-preferred lookup order, per-file char cap with labelled truncation notice, UTF-16 BOM tolerance. Any gap = small upstream PR, not a fork. |
| Compaction stragglers: `DeduplicateFileReads`, `WarnNearLimits` | remainder of `agents/_history.py` (26 KB) | The summarizers, spill and clamp are migrated; dedup/warn logic is still hand-rolled. Finish the job. | `_history` also owns tool-call-id sanitizing + message hashing used elsewhere; split before delete. |

## Tier 2: Adopt with glue (replace the model-facing core, keep the TUI)

| Capability | Redundant Code Puppy code | Gains | Blockers / gaps |
|---|---|---|---|
| `SubAgents` | `tools/subagent_invocation.py` (37 KB), `subagent_context.py`, `subagent_usage_metrics.py` | Per-delegate usage budgets, wall-clock timeouts, soft-steering failure messages: all things we hand-roll or lack. | Our `invoke_agent` has session-id continuity and the subagent stream panel; harness delegates are stateless per call. Needs a session-memory shim or upstream proposal. |
| `Shell` | `tools/command_runner.py` (59 KB) + `shell_backgrounding.py` | `start_command`/`check_command`/`stop_command` background processes, allow/deny lists (subsumes `shell_safety` + `destructive_command_guard` plugins), auto-cleanup at run end. | Deepest TUI entanglement in the codebase: streaming output rendering, Ctrl+X chords (kill/background), `run_shell_command` callback hooks with `fail_closed`. The harness toolset would be the *executor core*; every UI affordance must re-attach via events. Highest effort, highest payoff. |
| `FileSystem` | `tools/file_operations.py` (55 KB) + `file_modifications.py` (44 KB) | Battle-tested read/write/edit toolset, `READ_ONLY_TOOL_NAMES` split. | Harness FileSystem has **no undo recording** (`UndoManager` hooks), **no permission-callback seam** (`file_permission` hook), **no pluggable backend** (our `fs_access` facade backs ACP host filesystems). Three real gaps, candidates for upstream proposals before we can swap. |
| `StepPersistence` (+ `ConversationSearch`) | `session_storage.py`, `session_lifecycle.py`, `session_format_migration.py`, `session_migration.py`, `session_surrogate_unpickler.py` (~60 KB total) | Per-step snapshots give crash-resume *mid-run* (`continue_run(include_interrupted=True)`) and `fork_run`, strictly stronger than our end-of-turn JSON envelope. ConversationSearch comes along free. | Session naming/browsing UX and the legacy `.pkl` migration path stay app-side. Storage format changes = migration number 3; sequence carefully. |
| `Guardrails` (`ToolGuardrail`) | `hook_engine/` (8 modules) + guard plugins' block logic | One blessed pre/post tool interception model instead of our `pre_tool_call` + `fail_closed` special-casing. | `hook_engine` speaks Claude Code hook config (matchers, aliases); that translation layer is Code Puppy value-add and stays. Guardrails becomes the enforcement backend. |

## Tier 3: Different philosophy; evaluate, don't rush

| Capability | Code Puppy counterpart | Tension |
|---|---|---|
| `BrowserUse` | `tools/browser/` (13 Playwright modules) | Harness wraps the `browser-use` library as a sub-agent; ours is a direct Playwright toolset the main model drives. Swapping changes behavior and dependencies, not just implementation. Bench before deciding. |
| `Planning` | `agents/agent_planning.py` | Ours is a prompt-shaped planning agent; harness has a real plan store + granular tools + events. Adopting gets us live plan-progress UI (bottom bar!), attractive but additive rather than deletive. |
| `Researcher` / `ExaSearch` | `agents/agent_web_retriever.py` | Overlapping intent, different search backends. Low urgency. |
| `CapabilityCreation` / runtime authoring | `tools/universal_constructor.py` (32 KB) | UC builds Code Puppy tools/plugins at runtime; CapabilityCreation builds harness capabilities. Conceptual cousins, different artifacts. Revisit if Code Puppy agents become harness-capability-native. |
| `SystemReminders` | `timestamp_heartbeat` plugin, steer-queue nudges | Harness does cadence/conditional reminders without cache busts. Nice-to-have consolidation. |

## N/A: no redundancy; adoption would be a new feature

`Memory`, `Advisor`, `DynamicWorkflow`, `SpendLimits`,
`WarnOnCacheBusts`, `PromptInjectionDefender`, `ModalSandbox`, `LocalStack`,
`StackOne`, `Macroscope`, `PydanticAIDocs`, `ManagedPrompt`.
Zero Code Puppy code deleted by adopting these; evaluate on their own merits.

## Keep ours: app/UI concerns out of harness scope

- `messaging/`, `tui/`, `command_line/`: the entire terminal UX.
- `mcp_/`: dashboard, config wizard, health monitor, circuit breaker (core MCP
  transport already comes from pydantic-ai).
- `model_factory.py`, OAuth clients (`claude_cache_client`, `chatgpt_codex_client`,
  `gemini_*`), `round_robin_model.py`, `secret_store*`: model transport & credentials.
- `token_usage.py` / `status_display.py`: context badge UI (could someday *feed
  from* `ReportContextUsage`, but the rendering is ours).
- `undo_manager.py` + `/undo`: CLI-side file rewind (currently has no dedicated
  test file).

## Suggested attack order

1. **`RepoContext`**: small, self-contained, finishes with a parity checklist.
2. **Compaction stragglers** (`DeduplicateFileReads`, `WarnNearLimits`):
   completes a migration that's now mostly done.
3. **`SubAgents`**: after upstreaming a session-continuity story.
4. **`StepPersistence`**: biggest UX win (mid-run crash resume), needs a
   migration plan.
5. **`FileSystem` / `Shell`**: the big ones; each needs 1-3 upstream gap
   proposals (undo seam, permission callbacks, backend facade; UI event taps)
   through pydantic-ai-notes first.
