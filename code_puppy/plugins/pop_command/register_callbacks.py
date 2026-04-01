"""Plugin: /pop <n>

Deletes the *n* most-recent messages from the conversation history and then
automatically prunes any broken tool-call fragments that would confuse the
model (e.g. a ToolCallPart with no matching ToolReturnPart, or vice-versa).

Usage
-----
    /pop          – pop the single most-recent message
    /pop 1        – same as above
    /pop 3        – pop the 3 most-recent messages
"""

from __future__ import annotations

from typing import List, Any

from code_puppy.command_line.command_registry import register_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_only_tool_returns(message: Any) -> bool:
    """Return True if a ModelRequest contains *only* ToolReturnPart entries.

    Such a message is the follow-up to a tool-call response. If the preceding
    ModelResponse was popped, this orphaned request makes no sense and must be
    pruned as well.
    """
    try:
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        if not isinstance(message, ModelRequest):
            return False
        parts = getattr(message, "parts", [])
        return bool(parts) and all(isinstance(p, ToolReturnPart) for p in parts)
    except Exception:
        return False


def _has_unresolved_tool_calls(message: Any) -> bool:
    """Return True if a ModelResponse ends with unresolved ToolCallParts.

    When a pop lands in the middle of a tool round-trip (i.e. the
    ModelRequest containing the ToolReturnParts was removed), the preceding
    ModelResponse is now the tail and still carries ToolCallParts that will
    never be resolved.  We remove it too.
    """
    try:
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        if not isinstance(message, ModelResponse):
            return False
        parts = getattr(message, "parts", [])
        return any(isinstance(p, ToolCallPart) for p in parts)
    except Exception:
        return False


def _prune_dangling_tool_fragments(history: List[Any]) -> tuple[List[Any], int]:
    """Iteratively strip incomplete tool-call sequences from the tail.

    Returns the cleaned history and the number of extra messages pruned.
    """
    pruned = 0
    while history:
        tail = history[-1]
        if _has_only_tool_returns(tail):
            # Orphaned tool-result block – the call that triggered it was popped.
            history.pop()
            pruned += 1
        elif _has_unresolved_tool_calls(tail):
            # Unresolved tool-call block – esult block was popped.
            history.pop()
            pruned += 1
        else:
            break
    return history, pruned


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------

@register_command(
    name="pop",
    description="Delete the N most-recent messages and auto-prune interrupted tool calls",
    usage="/pop [N]",
    category="session",
    detailed_help="""\
Remove the last N messages from the conversation history (default N=1).

After the deletion the command automatically removes any broken tool-call
fragments so the remaining history stays consistent:

  • A trailing assistant message that contains unresolved tool calls (the
    corresponding tool-result message was just popped) is removed.
  • A trailing user/tool message that contains only ToolReturnParts (the
    assistant message that requested the tool was just popped) is removed.

Both cleanup steps repeat until the tail is clean.

Examples:
  /pop        → remove the last 1 message
  /pop 2      → remove the last 2 messages
  /pop 10     → remove the last 10 messages
""",
)
def handle_pop_command(command: str) -> bool:
    """Handle the /pop [n] command."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

    # ------------------------------------------------------------------ parse
    tokens = command.split()
    n: int = 1
    if len(tokens) >= 2:
        try:
            n = int(tokens[1])
        except ValueError:
            emit_error(f"/pop: '{tokens[1]}' is not a valid integer – usage: /pop [N]")
            return True
        if n < 1:
            emit_error("/pop: N must be a positive integer")
            return True

    # -------------------------------------------------------------- get agent
    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/pop: could not get current agent – {exc}")
        return True

    history: List[Any] = list(agent.get_message_history())

    if not history:
        emit_warning("/pop: conversation history is empty – nothing to remove")
        return True

    # The first message is the system prompt; never touch it.
    # Poppable messages are indices 1 … len-1.
    poppable = len(history) - 1  # how many we *can* remove
    if poppable == 0:
        emit_warning("/pop: only the system prompt is in history – nothing to remove")
        return True

    if n > poppable:
        emit_warning(
            f"/pop: requested {n} but only {poppable} message(s) can be removed "
            f"(the system prompt is always preserved). Removing {poppable}."
        )
        n = poppable

    before_count = len(history)

    # ------------------------------------------------ remove the last n items
    history = history[: len(history) - n]

    # ----------------------------------------- auto-prune broken tool chains
    history, extra_pruned = _prune_dangling_tool_fragments(history)

    after_count = len(history)
    total_removed = before_count - after_count

    # ---------------------------------------------------- apply new history
    try:
        agent.set_message_history(history)
    except Exception as exc:
        emit_error(f"/pop: failed to update message history – {exc}")
        return True

    # ------------------------------------------------------- user feedback
    parts = [f"✂️  Popped {n} message(s)"]
    if extra_pruned:
        parts.append(
            f"and pruned {extra_pruned} extra incomplete tool-call fragment(s)"
        )
    summary = " ".join(parts) + "."

    remaining = after_count - 1  # subtract system prompt from display count
    emit_success(
        f"{summary}\n"
        f"📜 History: {before_count - 1} → {remaining} message(s) "
        f"(excluding system prompt, removed {total_removed} total)"
    )

    if after_count <= 1:
        emit_info("💡 History is now empty (system prompt only). Starting fresh!")

    return True
