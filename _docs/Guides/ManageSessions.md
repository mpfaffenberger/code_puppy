# How to Manage Sessions and History

## What You'll Learn
By the end of this guide, you'll be able to save, load, and manage your conversation history — so you never lose context and can pick up where you left off.

## Prerequisites
- Code Puppy installed and running
- At least one conversation started (so there's history to manage)

## Quick Version

```
/session              # Show current autosave session ID
/session new          # Start a fresh session
/resume               # Load a previous autosave session
/dump_context mywork  # Save current history with a custom name
/load_context mywork  # Restore a previously saved session
/compact              # Shrink history to save tokens
/truncate 20          # Keep only the 20 most recent messages
```

## How Sessions Work

Code Puppy automatically saves your conversation history as you work. Each session gets a unique ID based on the current date and time (e.g., `20250115_143022`). These autosaves happen in the background — you don't need to do anything.

In addition to autosaves, you can manually save and load named sessions for more control.

## Detailed Steps

### 1. Check Your Current Session

To see which autosave session you're in:

```
/session
```

You'll see something like:

```
Autosave Session: 20250115_143022
Files prefix: ~/.cache/code_puppy/autosaves/auto_session_20250115_143022
```

> [!TIP]
> You can also use the short alias `/s` instead of `/session`.

### 2. Start a Fresh Session

When you want a clean slate without losing your current history:

```
/session new
```

This rotates your session ID. Your previous session is preserved as an autosave, and a new session begins.

### 3. Resume a Previous Session

To browse and load a previous autosave:

```
/resume
```

You can also use `/autosave_load`. This opens an interactive browser showing your saved sessions with details like message count and timestamp. Select a session by number or name to restore it.

You'll see a list like:

```
Autosave Sessions Available:
  [1] auto_session_20250115_143022 (24 messages, saved at 2025-01-15T14:35:10)
  [2] auto_session_20250114_091500 (15 messages, saved at 2025-01-14T10:02:33)
  [Enter] Skip loading autosave
```

> [!NOTE]
> When you have more than 5 sessions, use option `[6]` to page through them.

### 4. Save a Named Snapshot

To save your current conversation with a memorable name:

```
/dump_context my_project
```

This creates a named snapshot you can reload anytime. You'll see confirmation like:

```
✅ Context saved: 24 messages (15230 tokens)
📁 Files: ~/.local/share/code_puppy/contexts/my_project.pkl, my_project_meta.json
```

> [!TIP]
> Use descriptive names like `refactor_auth`, `debug_api`, or `feature_search` so you can find sessions later.

### 5. Load a Named Snapshot

To restore a previously saved session:

```
/load_context my_project
```

If the session name doesn't exist, Code Puppy shows you the available sessions:

```
Available contexts: debug_api, feature_search, my_project, refactor_auth
```

> [!WARNING]
> Loading a session replaces your current conversation history. Make sure to save your current work first with `/dump_context` if you want to keep it.

### 6. Compact Your History

Long conversations use a lot of tokens. When things get large, compact your history:

```
/compact
```

This summarizes older messages while keeping recent ones intact. You'll see the reduction:

```
🤔 Compacting 45 messages using summarization strategy... (~32000 tokens)
✨ Done! History: 45 → 12 messages via summarization
🏦 Tokens: 32,000 → 8,500 (73.4% reduction)
```

The compaction strategy is configurable:

| Strategy | How It Works |
|----------|-------------|
| `summarization` (default) | Uses AI to summarize older messages into a concise summary |
| `truncation` | Simply removes the oldest messages, keeping recent ones |

To change the strategy:

```
/set compaction_strategy=truncation
```

### 7. Truncate History Manually

To keep only the N most recent messages:

```
/truncate 20
```

This keeps the system message (always preserved) plus the 19 most recent messages. You'll see:

```
Truncated message history from 45 to 20 messages (keeping system message and 19 most recent)
```

> [!NOTE]
> The system message is always preserved, regardless of how many messages you keep. So `/truncate 10` keeps the system message + 9 recent messages = 10 total.

## Session Commands at a Glance

| Command | Alias | Description |
|---------|-------|-------------|
| `/session` | `/s` | Show current autosave session ID |
| `/session new` | — | Rotate to a new session |
| `/autosave_load` | `/resume` | Browse and load autosave sessions |
| `/dump_context <name>` | — | Save history with a custom name |
| `/load_context <name>` | — | Load a named session |
| `/compact` | — | Summarize/compress history to save tokens |
| `/truncate <N>` | — | Keep only N most recent messages |

## When Sessions Rotate Automatically

Code Puppy automatically rotates your autosave session in certain situations:

- **Switching agents** — When you use `/agent <name>`, the current session is saved and a new one begins
- **Loading a session** — When you load a context, the autosave ID updates to match
- **Starting fresh** — When you use `/session new`

This prevents different conversations from overwriting each other.

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "No history to compact yet" | You haven't started a conversation | Send at least one message before using `/compact` |
| "Context file not found" | Typo in session name | Check available sessions — Code Puppy will list them |
| "No history to truncate" | Empty conversation | Start chatting first, then truncate later |
| History seems lost after restart | Normal behavior | Use `/resume` to load your previous autosave |

## Related Guides
- [How to Switch Models](SwitchModels) — Models are independent of sessions
- [How to Switch and Use Agents](UseAgents) — Agent switches trigger session rotation
- [Reference: Slash Commands](../Reference/Commands) — All available commands
- [Reference: Configuration Options](../Reference/ConfigReference) — Compaction and session settings
