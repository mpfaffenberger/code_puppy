# Slack Integration

Connect Code Puppy to a Slack workspace so anyone can run prompts from any channel or DM — on desktop or mobile.

## How it works

```
Slack message / /pup command
        ↓
Slack Bolt (Socket Mode)
        ↓
WebSocket → /ws/terminal (existing PTY backend)
        ↓
Code Puppy agent runs
        ↓
Output streamed back → posted to Slack thread
```

Each **Slack thread** maps to one persistent PTY session, so follow-up replies in the same thread have full context.

---

## Setup

### 1. Create a Slack App

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **Settings → Socket Mode** → enable it → generate an **App-Level Token** with `connections:write` scope. Save as `SLACK_APP_TOKEN`.
3. Under **OAuth & Permissions → Bot Token Scopes**, add:
   - `app_mentions:read`
   - `chat:write`
   - `channels:history`
   - `groups:history`
   - `im:history`
   - `commands`
4. Under **Slash Commands** → **Create New Command**:
   - Command: `/pup`
   - Request URL: `https://example.com` (ignored in Socket Mode)
   - Short description: `Ask Code Puppy`
5. Under **Event Subscriptions** → enable, then **Subscribe to bot events**: add `app_mention` and `message.im`
6. **Install to Workspace** → copy the **Bot User OAuth Token**. Save as `SLACK_BOT_TOKEN`.

### 2. Install the Slack extra

```bash
pip install "code-puppy[slack]"
```

### 3. Set environment variables

```bash
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...
export CODE_PUPPY_WS_URL=ws://localhost:8765/ws/terminal   # default
```

### 4. Start the Code Puppy API server

```bash
pup --api   # or however you start the FastAPI server
```

### 5. Start the Slack bot

```bash
python -m code_puppy.integrations.slack_bot
```

---

## Usage

| How | What to do |
|-----|------------|
| **Mention** | `@CodePuppy fix the login bug in auth.py` |
| **DM** | Send any message directly to the bot |
| **Slash command** | `/pup explain the retry logic in circuit_breaker.py` |
| **Thread reply** | Reply in the same thread — session is preserved |

---

## Notes

- Responses are collected for up to **3 seconds of idle output**, then posted. For long-running tasks the bot will post partial output if the hard timeout (120 s) is reached.
- Output longer than ~2 800 characters is truncated with a notice.
- Code fences (` ``` `) in the output are rendered as Slack code blocks.
- The bot ignores its own messages and edited/deleted message events to avoid loops.
