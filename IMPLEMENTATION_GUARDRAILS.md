# Implementation Guardrails

Read this before making changes in this repo.

## Protected Behavior

- Keep the always-on composer fixed at the bottom.
- Keep the composer usable while the agent is running.
- Keep the composer usable while a foreground shell command is running.
- Do not reintroduce a read-only or suspended prompt during shell execution.
- `/exit` and `/quit` must bypass queue/interject handling and win immediately.
- `Ctrl+C` from the composer must interrupt foreground shell work immediately.
- Busy submit must stay inline: `Enter` stores the prompt and shows `[i]nterject or [q]ueue`.
- Do not bring back a second prompt surface for interject decisions.
- Interject must aggressively cancel current work and run before normal queued prompts.
- Queued/interjected prompts must echo into the transcript before dispatch.
- Interjected prompts must echo the user's exact text into the transcript before any apply/start lifecycle lines.
- Direct prompts submitted from erasable prompt sessions must echo once into the transcript before any response or tool output.
- Normal direct follow-up prompts after queue/interject cycles must remain visible in the transcript.
- Interject injection text must tell the agent to continue the interrupted task after acknowledging the interjection.
- Auto-save must fire after each successfully completed interactive agent response, including queued and interjected turns, before the next queued turn launches.
- Cancelled turns, slash commands, and OAuth/background interactive commands must not trigger auto-save.
- Queue preview must stay above the composer, max 3 visible rows, scroll when over 3, and cap at 25 prompts.
- Queued prompt preview rows must stay one line, truncated, and never wrap.
- Keep the composer at a fixed two-line viewport with internal scrolling for long prompts.

## Rendering Guardrails

- Do not stream Rich/ANSI/termflow output directly into the mounted prompt surface.
- Final `AGENT RESPONSE` output must render as a proper banner above the prompt.
- Structured banners like `AGENT REASONING`, listings, and tool blocks must use the prompt-safe render path.
- Shell output with the prompt mounted must stay plain text. Do not reintroduce Rich dim styling or raw ANSI fragments there.
- Above-prompt Rich blocks and transcript notices must share one serialized render path and must never interleave at the byte level.
- Do not reintroduce the shell warning line in the prompt header if typing is still enabled.
- Legacy slash-command output emitted through `emit_info`, `emit_warning`, `emit_error`, `emit_success`, and divider output must remain visible in interactive mode.
- Rich slash-command renderables like `Text`, `Table`, and `Markdown` must still render above the mounted composer.

## Queue Transcript Rules

- Keep queued-save transcript copy compact: `[Queued][N] {text}`.
- Keep queued-launch transcript copy as `[QUEUE TRIGGERED] {text}` and print it before the echoed queued prompt.
- Keep `list_agents` output visible in the transcript before downstream sub-agent invocation output.
- Do not reintroduce visible interject `applying now` lines.
- Do not reintroduce late launched-item `finished`, `applied`, or `run_cancelled` transcript noise.
- Keep transcript polish presentation-only; do not change queue/interject runtime semantics when adjusting these lines.

## Spinner And Context Rules

- The spinner is a visual heartbeat only. It should not control real work or real redraw priority.
- Spinner redraws must stay low-priority and yield behind real prompt/state redraws.
- Token/context updates should invalidate promptly on their own and should not wait on spinner timing.
- Seed the token/context line at run start so it does not show stale data from the previous run.
- Keep seeded token/context estimation parity-safe: active-agent token estimates, context length, and attachment/link overhead must still feed the top-level prompt status line.
- Keep sub-agent token accumulation in the sub-agent console path; do not collapse it into the top-level prompt status line.
- Keep the prompt-native spinner; do not bring back the old Rich live spinner for interactive runs.

## Command And OAuth Rules

- OAuth setup flows (`/antigravity-auth`, `/antigravity-add`, `/claude-code-auth`, `/chatgpt-auth`, tutorial/onboarding auth handoff) are core functionality and must remain working.
- During OAuth callback waits, `/exit`, `/quit`, and the configured cancel key must still work.
- Cancelling auth must not half-apply model switches, reloads, or config changes.
- Queueing or interjecting during auth or other cooperative external waits must never crash; cancel/cleanup races must be harmless.
- While work is active, only `/exit` and `/quit` keep slash-command semantics.
- Busy slash-prefixed text other than `/exit` and `/quit` must remain literal user text if queued or interjected.
- The chooser state must not show slash-command menus or execute slash commands.
- While the chooser is visible, `e` must restore the saved drafted prompt back into the composer.
- `Up Arrow` may remain as a compatibility alias for restore, but chooser copy should advertise `e`.
- While the chooser is visible, `Esc` must drop the saved drafted prompt and leave the composer empty.
- While the chooser is visible, non-chooser typing must be inert; the chooser buffer should be effectively read-only except for the explicit chooser keys and immediate cancel/exit paths.
- Keep chooser hint copy concise; do not turn the inline chooser row into a sentence-length help block.
- Keep `@` as attachment/path completion, not as a picker-style command menu.
- Bare `@` should continue to offer current-directory completion candidates.
- `@` completion must keep prompt_toolkit-style semantics: `Tab` only cycles/advances completions, prompt_toolkit accept-completion keys remain available, and `Enter` keeps submit semantics.
- Typing a space after an `@` path is normal text continuation, not a special acceptance action.
- Busy `@` attachment completion is allowed while the always-on composer is open, but the chooser state must stay modal and must not show `@` completions or attachment placeholder transforms.
- Chooser typing must not mutate the stored pending submission.
- `Ctrl+C` from the composer must remain the universal busy-state cancel path: shell interrupt, background command cancel, or agent cancel as appropriate.
- Manual cancel from the composer (`Ctrl+C` or configured cancel key) must stop current work without auto-launching queued prompts; queued items should remain queued until the user explicitly submits something new.
- Manual shell interrupt from the composer must follow the same queue-pause rule: interrupt the shell, keep queued items intact, and stop there until explicit user input resumes flow.
- When queue autodrain is paused and the runtime is idle, pressing `Enter` on an empty composer should recall the next queued prompt into the composer for editing; it must not auto-run the queued item.
- Hook commands and hook-engine behavior must remain functional in the mounted-composer fork; preserve their legacy command output path rather than rewriting them.

## Wiggum Rules

- When Wiggum mode is active, ordinary queued work must not drain before the next Wiggum rerun starts.
- Only interject items may bypass an active Wiggum loop; ordinary queued prompts must wait until Wiggum is no longer active.
- Interjecting during Wiggum must affect only the current iteration; it must not stop the stored Wiggum loop prompt from continuing afterward.
- Busy slash-prefixed text queued during Wiggum must remain literal agent text, not execute as a slash command when it later drains.
- `Ctrl+C` during Wiggum must stop future reruns cleanly, without emitting duplicate stop/cancel lines or a stray `Input cancelled` afterward.
- Manually stopping Wiggum must not auto-trigger ordinary queued prompts; they should remain queued and paused until explicit user input resumes flow.

## Config And Runtime Notes

- Use `./.cp-local/run-code-puppy-local.sh` when you need isolated local setup/auth for this repo.
- Treat `/Users/nateoswalt/code-puppy-interject-queue-v2` as the rewrite repo.
- Treat `/Users/nateoswalt/code-puppy` as the older baseline repo.

## Pre-Implementation Check

- Read this file.
- Read `docs/INTERACTIVE_REGRESSION_CHECKLIST.md`.
- Check for prompt/render/runtime side effects before editing.
- If a change touches interactive runtime, prompt rendering, shell integration, queue/interject flow, or spinner behavior, run focused tests and do a real terminal smoke pass afterward.
