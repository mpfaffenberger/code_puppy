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
- Interject injection text must tell the agent to continue the interrupted task after acknowledging the interjection.
- Queue preview must stay above the composer, max 3 visible rows, scroll when over 3, and cap at 25 prompts.
- Queued prompt preview rows must stay one line, truncated, and never wrap.
- Keep the composer at a fixed two-line viewport with internal scrolling for long prompts.

## Rendering Guardrails

- Do not stream Rich/ANSI/termflow output directly into the mounted prompt surface.
- Final `AGENT RESPONSE` output must render as a proper banner above the prompt.
- Structured banners like `AGENT REASONING`, listings, and tool blocks must use the prompt-safe render path.
- Shell output with the prompt mounted must stay plain text. Do not reintroduce Rich dim styling or raw ANSI fragments there.
- Do not reintroduce the shell warning line in the prompt header if typing is still enabled.

## Spinner And Context Rules

- The spinner is a visual heartbeat only. It should not control real work or real redraw priority.
- Spinner redraws must stay low-priority and yield behind real prompt/state redraws.
- Token/context updates should invalidate promptly on their own and should not wait on spinner timing.
- Seed the token/context line at run start so it does not show stale data from the previous run.
- Keep the prompt-native spinner; do not bring back the old Rich live spinner for interactive runs.

## Config And Runtime Notes

- Use `./.cp-local/run-code-puppy-local.sh` when you need isolated local setup/auth for this repo.
- Treat `/Users/nateoswalt/code-puppy-interject-queue-v2` as the rewrite repo.
- Treat `/Users/nateoswalt/code-puppy` as the older baseline repo.

## Pre-Implementation Check

- Read this file.
- Check for prompt/render/runtime side effects before editing.
- If a change touches interactive runtime, prompt rendering, shell integration, queue/interject flow, or spinner behavior, run focused tests and do a real terminal smoke pass afterward.
