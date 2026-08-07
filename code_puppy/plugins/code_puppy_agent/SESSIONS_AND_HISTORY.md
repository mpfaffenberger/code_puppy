# Session & History System

> Part of the `code-puppy-agent` skill. Read this when debugging context
> window / compaction issues, or working with session save/load. See
> `SKILL.md` for the overview and the full reference map.

---

## Message history

Each `BaseAgent` maintains `_message_history` — a list of pydantic-ai
`ModelMessage` objects (alternating `ModelRequest`/`ModelResponse`).
History is the conversation context sent to the LLM on each turn.

## Context window management

When the conversation grows too large:
1. **Token estimation** (`_history.py`) — estimates tokens per message
2. **Compaction** (`_compaction.py`) — summarizes older messages using a
   dedicated summarization agent, preserving recent messages
3. **Protected tokens** — the most recent N tokens are never compacted
   (configurable via `protected_token_count`)

## Session persistence

Sessions are saved as pickle files in the state directory:
- `session_storage.py` handles serialization
- `/save <name>` and `/load <name>` commands
- Auto-save on exit

## Useful history commands

| Command | Effect |
|---------|--------|
| `/save <name>` | Save current session |
| `/load <name>` | Load a saved session |
| `/pop [N]` | Remove N most recent messages |
| `/truncate <N>` | Keep only N most recent messages |
| `/prune` | Interactive context pruning UI |
