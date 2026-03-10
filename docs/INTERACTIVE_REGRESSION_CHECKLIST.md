# Interactive Regression Checklist

Run this before merging changes that touch the interactive runtime, prompt surface, queue/interject flow, slash commands, or OAuth setup.

## Transcript And Rendering

- Run `/help` and confirm normal slash-command output appears above the composer.
- Run `/show`, `/cd` with no args, `/tools`, and `/skills list` and confirm `Text`, `Table`, and `Markdown` output still render cleanly above the composer.
- Trigger one invalid command such as a bad `/set` value and confirm warning/error text is visible above the composer.
- Confirm no raw ANSI fragments or prompt corruption appear while command output is printed.

## OAuth Setup And Escape Paths

- Start `/antigravity-add` and confirm browser/callback status text appears above the composer.
- While waiting for callback, verify `/exit` exits immediately.
- Rerun the auth flow and verify `Ctrl+C` cancels the auth wait cleanly.
- Rerun the auth flow and verify interject cancels the active auth wait first, then proceeds.
- Rerun the auth flow and verify queue saves cleanly while waiting, then drains after the wait ends.
- After cancel, confirm there is no timeout/failure spam and no half-applied model/config change.
- After queueing or interjecting during the auth wait, confirm there is no traceback even if cancel completes immediately.
- Verify a successful auth path still completes normally when not cancelled.
- Verify `/tutorial` auth handoff still routes into the same cancellable auth path.

## Busy Slash-Command Gating

- While an agent run is active, type `/model` and confirm slash-command completion does not open.
- While active work is running, submit `/model` and queue it; confirm it is treated as literal text for the agent, not executed as a command.
- While active work is running, submit `/model` and interject it; confirm it is treated as literal text for the agent, not executed as a command.
- While active work is running, verify `/exit` and `/quit` still bypass queue/interject handling immediately.
- While the inline chooser is visible, confirm slash-command menus do not appear and stray typing does not replace the stored pending prompt.

## Cancel Behavior

- During a foreground shell command, press `Ctrl+C` and confirm the shell is interrupted without tearing down the outer session.
- During a background interactive command or sub-agent action, press `Ctrl+C` and confirm the inner work cancels and control returns cleanly.
- During a normal active agent run, press `Ctrl+C` and confirm the run cancels and the prompt becomes usable again.
- If the chooser is visible during active work, press `Ctrl+C` and confirm the active work cancels and the chooser/input state clears.

## Queue And Prompt Stability

- Queue a normal follow-up while shell output is still streaming and confirm the save line appears immediately.
- Verify queued and interjected prompts still echo into the transcript before dispatch.
- Verify `[QUEUE TRIGGERED]` still prints before the echoed queued prompt.
- Verify a normal direct prompt after a queue/interject cycle still appears in the transcript once.
- Confirm the composer stays fixed, the shell output remains plain text, and the queue/interject visuals do not regress.

## Autosave

- Submit a normal prompt and confirm `Auto-saved session` appears after the completed response.
- Queue multiple prompts and confirm each completed response auto-saves before the next queued turn starts.
- Interject during a run and confirm the completed interjected response auto-saves.
- Cancel a run and confirm no autosave fires for that cancelled turn.
- Run an OAuth/background interactive command and confirm it does not auto-save on its own.
