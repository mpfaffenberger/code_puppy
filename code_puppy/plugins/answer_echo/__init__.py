"""Echo ask_user_question answers to scrollback after the TUI exits.

The ``ask_user_question`` tool runs in a full-screen alt-screen TUI. When
the user submits (or cancels), the alt screen is restored and the original
scrollback is unchanged — meaning the questions and the user's selections
disappear from view. This is confusing: the agent's next response references
choices the user can no longer see in their terminal history.

This plugin hooks ``post_tool_call`` and, when the tool is
``ask_user_question`` and the result is a successful ``AskUserQuestionOutput``,
prints a compact one-line-per-question summary to scrollback using the
shared messaging bus. Bounded so it can't dominate the viewport:

    ▸ User answered: Database → PostgreSQL; Cache → Redis

Cancelled / timed-out / errored runs are surfaced as a single dim line so
the agent can see the user rejected the prompt.
"""
