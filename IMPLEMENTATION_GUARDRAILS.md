# Implementation Guardrails

- When the live prompt surface is active, `agent_share_your_reasoning` must render through the structured `AGENT REASONING` path, not as low-level `Calling ... token(s)` tool progress.
- When the live prompt surface is active, mutable tool progress that upstream prints and clears must render in the prompt-local ephemeral status strip, not as transcript output and not via above-prompt prints.
- When the live prompt surface is active, streamed `TextPart` content may appear only in the prompt-local ephemeral preview; the permanent transcript must still come only from the final `AGENT RESPONSE`.
- When the live prompt surface is active, shell output with carriage-return progress must use the prompt-local ephemeral status strip; ordinary shell lines remain on the durable shell output path.
- Durable structured outputs like `AGENT REASONING` and `DIRECTORY LISTING` should still render above the prompt.
- Prompt-surface stream fixes must not duplicate the final `AGENT RESPONSE`.
- The prompt-local ephemeral status/preview is foreground-only; session-tagged sub-agent messages must never write to it or clear it.
- Terminal/emulator-specific behavior must flow through the shared terminal-capability helper in `terminal_utils` rather than adding new scattered env checks.
