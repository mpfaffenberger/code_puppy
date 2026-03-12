# Interactive Regression Checklist

Run this before merging changes that touch the interactive runtime, prompt surface, queue/interject flow, slash commands, or OAuth setup.

## Transcript And Rendering

- Run `/help` and confirm normal slash-command output appears above the composer.
- Run `/show`, `/cd` with no args, `/tools`, and `/skills list` and confirm `Text`, `Table`, and `Markdown` output still render cleanly above the composer.
- Trigger one invalid command such as a bad `/set` value and confirm warning/error text is visible above the composer.
- Confirm no raw ANSI fragments or prompt corruption appear while command output is printed.
- Interject during repeated directory listings or other multi-line tool output and confirm listings/notice text do not interleave or leak raw `?[32m`-style fragments.
- Repeat the directory-listing/interject check on a second machine or terminal when possible, since the bug is timing-sensitive.

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
- While the inline chooser is visible, press `e` and confirm the saved draft returns to the composer exactly as written.
- If `Up Arrow` is still supported as an alias, confirm it also restores the saved draft.
- While the inline chooser is visible, press `Esc` and confirm the saved draft is dropped and the composer is empty.
- Confirm the chooser hint stays compact and readable while still exposing `i`, `q`, `e`, and `Esc`.
- In the idle composer, type bare `@` and confirm current-directory file/path completions appear.
- Confirm `@` completion behaves like prompt_toolkit completion, not a picker: `Tab` should only cycle/advance candidates, the prompt_toolkit accept-completion keys should still work, and `Enter` should still submit the buffer.
- After an `@` path is in the buffer, confirm typing space just continues the prompt normally; it is not a special acceptance key.
- While active work is running and the chooser is not visible yet, type `@` and confirm file/document completion still works for composing a future prompt.
- Once the chooser is visible, confirm `@` completion does not appear and attachment placeholder rendering does not activate for chooser typing.
- Queue or interject a prompt that already includes `@...` before the chooser opens, then confirm attachments still resolve when that stored prompt later runs.

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

## Tokens And Hooks

- Run a normal prompt with a link or document attachment and confirm the top-level token/context line still seeds sensibly before the response starts.
- Invoke a sub-agent and confirm token counting still updates in the sub-agent console path rather than corrupting the top-level prompt line.
- Run `/hooks`, `/hook list`, and `/hooks status` and confirm they still execute and render above the composer in the mounted-composer fork.
- Re-run the hook-engine regression slice if hook-related code or command output wiring changes.

## Wiggum

- Start `/wiggum hello`, queue a normal follow-up, and confirm the queued turn runs before the next Wiggum rerun.
- After that queued turn completes, confirm Wiggum resumes its stored loop prompt.
- While Wiggum is active, queue a slash-prefixed prompt such as `/agent` and confirm it is treated as literal agent text, not executed as a slash command.

## Autosave

- Submit a normal prompt and confirm `Auto-saved session` appears after the completed response.
- Queue multiple prompts and confirm each completed response auto-saves before the next queued turn starts.
- Interject during a run and confirm the completed interjected response auto-saves.
- Cancel a run and confirm no autosave fires for that cancelled turn.
- Run an OAuth/background interactive command and confirm it does not auto-save on its own.
