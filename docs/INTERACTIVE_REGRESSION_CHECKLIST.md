# Interactive Regression Checklist

- Prompt-surface runs show `AGENT REASONING` above the textbox when `agent_share_your_reasoning` is used.
- Prompt-surface runs do not show `Calling agent_share_your_reasoning... N token(s)` above the textbox or in the prompt-local ephemeral status strip.
- Prompt-surface runs show ordinary mutable tool progress in the prompt-local ephemeral status strip without moving the prompt box or adding transcript spam; structured tool outputs like `DIRECTORY LISTING` still render normally.
- Prompt-surface tool progress must not leak raw ANSI or flash the prompt surface on each delta.
- Prompt-surface runs may show live response text only in the prompt-local ephemeral preview, and the final `AGENT RESPONSE` still renders once.
- Prompt-surface shell carriage-return progress updates in place in the prompt-local ephemeral status strip and clears on completion without transcript spam.
- Parallel sub-agents must not overwrite or clear the foreground prompt-local ephemeral status/preview.
- Windows text clipboard fallback must work through `pwsh` first and then Windows PowerShell without changing paste semantics.
- Unknown, CI, or non-interactive terminals must degrade away from risky live CR/ANSI redraw behavior instead of leaking raw control sequences.
