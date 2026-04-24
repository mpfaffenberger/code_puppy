# Continuity Compaction

Continuity is an opt-in compaction strategy for long coding sessions:

```text
/set compaction_strategy continuity
```

The strategy is designed to preserve working state rather than preserve the
entire conversation as a raw transcript. It keeps a recent raw tail, injects a
durable memory snapshot, masks old bulky tool observations, and only falls back
to summarizing or trimming when masking is not enough.

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
