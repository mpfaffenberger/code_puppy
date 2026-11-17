# Model input boundary

`transform_model_messages` is Code Puppy's outbound message guard boundary.
Every conversational model request installs `build_model_message_transform()`
as an innermost `before_model_request` capability. The hook receives the
request-only message list after compaction and other history processing,
immediately before the provider call.

This is a mutable, ordered callback chain:

- callbacks run in registration order;
- each callback sees mutations made by earlier callbacks;
- a callback that raises is logged and ignored, and later callbacks still run;
- inserting, removing, or replacing entries in the callback's message list is
  request-only and is not written back to conversation history;
- message and part objects may be shared with history, so in-place edits can
  persist. A request-only edit must replace the containing message entry with a
  new message and parts list.

Final ordering among outbound policies is intentionally not defined here.
Registration order remains the policy composition rule.

## Entry-point coverage

| Entry point | Boundary | Prompt submission and lifecycle |
| --- | --- | --- |
| Main CLI/frontend runs | Installed by the shared agent builder | Initial prompt, run start, and run end use shared runtime hooks. |
| ACP prompts | Uses the shared builder and runtime | ACP text and attachments follow the same path. |
| Sub-agent tool calls | Installed on each temporary sub-agent | Existing invocation hooks remain the sub-agent audit lifecycle. |
| `/fork` | Delegates to the covered sub-agent implementation | The fork prompt uses `user_prompt_submit`; balanced auxiliary run hooks carry the final session identity and terminal outcome. |
| `/btw` | Installed on its throwaway one-shot agent | The question uses `user_prompt_submit`; balanced auxiliary run hooks carry response, failure, and cancellation outcomes. |
| Background completion reports | Re-enter this boundary as literal model context | Child output bypasses `user_prompt_submit` and attachment/command parsing; it is not a fresh user submission. |
| Queued steers | Re-enter this boundary on the follow-up model call | Queue-mode steers are new user submissions and use `user_prompt_submit`. |
| Mid-run steers | Injected into history before the next request | They bypass prompt submission, but the message boundary sees the final injected message. |
| Hook-requested retries | Re-enter this boundary on the follow-up call | The retry prompt uses `user_prompt_submit` inside `is_hook_retry_prompt_submit()`, so subscribers can continue the current turn. The companion plugins skip UserPromptSubmit shell hooks and preserve the foreground notification preview for retries. |
| Goal judges | Installed on each fresh read-only judge | Generated judge prompts use `user_prompt_submit`; history exposed by the read-only tool is guarded on the next request. |

The `/fork`, `/btw`, and goal-judge rows require a companion plugin build that
uses these core APIs. Older plugin builds may bypass `user_prompt_submit` for
generated side prompts and do not emit the balanced auxiliary lifecycle.

Auxiliary `user_prompt_submit` dispatch for `/btw`, `/fork`, and goal judges
runs in an explicit auxiliary scope; `/btw` and `/fork` lifecycle callbacks use
the same scope.
End metadata includes `auxiliary_model_call: true` and a `status` of `completed`,
`failed`, or `cancelled`. Subscribers that own top-level UI, timing, process,
durable-memory, persistence, or one-shot foreground prompt state should use
`callbacks.is_auxiliary_agent_run()` to ignore that scope. Audit and
authentication subscribers may still observe it.

## Private inference

`run_private_prompt()` is a private, one-shot inference API without agent hooks,
history, or tools. Expanding its contract requires a separate maintainer
decision. New conversational entry points must install the boundary.

## Attachment visibility

The boundary sees provider-ready pydantic-ai message objects, not a text
summary. Inline binary parts expose their bytes and media type. URL parts expose
the URL; an adapter may fetch it later, outside this boundary. A guard that must
inspect content should strip or deny URL parts rather than assume the provider
performs the fetch.

Attachment-free auxiliary and follow-up calls submit their generated text
through the same prompt callbacks as the initial run. Core keeps no
attachment-suppression state or duplicate payload builder for those calls.
