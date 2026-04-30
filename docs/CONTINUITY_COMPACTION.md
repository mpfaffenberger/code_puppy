# Continuity Compaction

Continuity is an opt-in compaction strategy for long coding sessions:

```text
/set compaction_strategy continuity
```

It is implemented as a built-in plugin under
`code_puppy/plugins/continuity_compaction/`. Core only exposes generic
callbacks for strategy registration, config-key discovery, and message-history
compaction.

The strategy is designed to preserve working state rather than preserve the
entire conversation as a raw transcript. It keeps a recent raw tail, injects a
durable memory snapshot, masks old bulky tool observations, and only falls back
to summarizing or trimming when masking is not enough.

## Trigger Behavior

Continuity uses a soft trigger plus predicted next-turn growth, but prediction
does not fire from very low context usage. By default:

- `continuity_compaction_soft_trigger_ratio`: `82.5%`
- `continuity_compaction_predictive_trigger_min_ratio`: `72.5%`
- `continuity_compaction_target_ratio`: `35%`
- `continuity_compaction_emergency_trigger_ratio`: `90%`

That means an automatic predictive compaction can happen below the soft trigger
only when the current context is already at least `72.5%` full and the predicted
next turn would cross the soft trigger. Manual `/compact` still forces
compaction regardless of the predictive trigger floor.

The target ratio is the post-compaction ceiling Continuity tries to hit. With
the default settings, compaction targets `35%` full context, then fills back
toward that target with older compacted messages when they still fit safely.
Target trimming also pins the newest raw tail first, using
`continuity_compaction_recent_raw_floor_ratio` (`20%` by default), so the final
trim phase does not undercut the recent raw conversation just to hit target.

## Configuration

Continuity is opt-in:

```text
/set compaction_strategy=continuity
```

The plugin registers its own config keys, so they appear in `/set` help and can
be changed the same way as core settings:

```text
/set continuity_compaction_semantic_model=gpt-5.4
/set continuity_compaction_semantic_timeout_seconds=60
/set continuity_compaction_soft_trigger_ratio=0.825
/set continuity_compaction_predictive_trigger_min_ratio=0.725
/set continuity_compaction_target_ratio=0.35
/set continuity_compaction_recent_raw_floor_ratio=0.20
/set continuity_compaction_emergency_trigger_ratio=0.90
```

`continuity_compaction_semantic_model` controls the semantic memory LLM call.
If it is unset, Continuity uses the same active chat model that is handling the
current Code Puppy session. If no active chat model is available for a direct
utility call, it falls back to the existing `summarization_model` setting.
Fallback summarization uses Code Puppy's existing summarization path, so users
can tune fallback summaries with `summarization_model`.

Useful inspection commands:

```text
/continuity
/continuity tasks
/continuity archives search <query>
/continuity archives show <id>
/continuity diagnostics
```

## Practical Tradeoffs

| Scenario | Truncation Risk | Summarization Risk | Continuity Behavior |
|---|---|---|---|
| A long coding session starts with OAuth work, then switches to dashboard work. | Early OAuth constraints can be deleted completely. | The summary may flatten task boundaries and make old constraints look current. | Keeps the original root, active task, task ledger, and task-scoped constraints separately. |
| The agent reads huge files and test logs many times. | Old observations vanish, including useful failure signals. | Large outputs are compressed into prose that may omit exact status, tool name, or archive location. | Archives bulky raw observations locally and leaves deterministic capsules with tool name, status, checksum, token count, and signals. |
| A later bug depends on an old failed test or invalidated hypothesis. | The failure may be outside the retained tail. | A summary can accidentally keep stale hypotheses as if still valid. | Tracks validation status, accepted decisions, invalidated hypotheses, and archive retrieval hints. |
| The session runs through many compactions. | Repeated hard cuts can erase the roots of the session. | Repeated summaries can compound drift and lose task lifecycle. | Refreshes one bounded durable memory snapshot and preserves recent raw context separately. |
| The model is about to perform a large next turn. | Compaction can happen too late, after context is already tight. | Same threshold issue unless manually compacted. | Predicts next-turn growth and compacts when the projected turn would cross the soft trigger. |
| The user needs control over behavior. | Mostly controlled by global threshold/protected token settings. | Mostly controlled by summarization model/settings. | Exposes plugin-owned trigger, target, raw-tail, archive, retention, timeout, and semantic-model knobs. |

## Practical Before/After Example

Imagine a session starts with "add OAuth login," inspects many files, runs
tests, fixes bugs, and later switches to "improve the dashboard." After several
continuity compactions, the model should not need every raw command output from
the OAuth work. It should need the state that matters for continuing safely.

Before compaction, the live message history might look like this:

```text
- User: Add OAuth login and keep existing CLI behavior.
- Assistant: Plan.
- Tool read: huge auth.py contents.
- Tool read: huge config.py contents.
- Tool run: massive failing test log.
- User: Also preserve legacy token refresh behavior.
- Assistant: Fixes code.
- Tool run: passing tests.
- User: Now switch to dashboard improvements.
- Tool read: huge dashboard files.
- Tool run: lint output.
- User: Make the dashboard denser.
```

After continuity compaction, the live message history is closer to this:

```text
- System prompt.
- Durable memory:
  - Original root task: Add OAuth login.
  - Current task: Dashboard improvements.
  - Global/current constraints: preserve CLI behavior; preserve token refresh
    behavior if still relevant.
  - Decisions: used existing auth config path.
  - Validation: OAuth tests passed; dashboard lint last ran.
  - Active files: dashboard files, config files.
  - Task ledger: OAuth login completed/superseded; dashboard active.
  - Next action: continue dashboard density changes.
- Older tool returns replaced with masked observation capsules.
- Optional structured summary of the oldest masked region if masking alone is
  not enough.
- Older compacted history trimmed toward the displayed target if masking and
  summary still leave the context above target.
- Recent raw tail:
  - latest dashboard-related user messages
  - latest assistant/tool messages
  - latest errors/signals
```

## What Can Be Removed From Live Context

Continuity can remove or transform old live context such as:

- full old tool outputs
- full old file contents from earlier reads
- huge old test logs
- repetitive assistant explanations
- old user prompts that are no longer in the recent raw tail and have been
  represented in durable memory
- already-masked regions that later become structured summaries

The raw transcript is intentionally not preserved forever. The goal is to keep
the session resumable while making room for future work.

## What Is Retained

Continuity tries to retain:

- the latest user request as raw context
- the recent raw tail, scaled as a percentage of the active model context window
- one durable memory snapshot
- the original root task
- the current active task
- task ledger entries with lifecycle status
- global constraints and current-task constraints
- active files
- accepted decisions and invalidated hypotheses
- validation status
- next action
- short archive signals for old bulky observations
- valid pydantic-ai tool-call/tool-return ordering

## PR Note

When this feature is submitted upstream, include the before/after example above
in the PR description or link to this document. It gives reviewers a practical
mental model for what continuity compaction preserves, what it removes from live
context, and why the behavior differs from transcript-preserving summarization.
