"""Slack bot integration for Code Puppy.

Bridges Slack messages/slash commands to the Code Puppy backend via
the existing WebSocket terminal API. Each Slack thread maps to one
PTY session so conversations have context.

Setup
-----
1. Install extras:  pip install "code-puppy[slack]"
2. Create a Slack app at https://api.slack.com/apps
   - Enable Socket Mode (Settings → Socket Mode)
   - Add Bot Token Scopes: app_mentions:read, chat:write,
     channels:history, groups:history, im:history, commands
   - Add Slash Command: /pup  →  any request URL (Socket Mode ignores it)
   - Install to workspace → copy Bot Token + App Token
3. Set env vars:
      SLACK_BOT_TOKEN=xoxb-...
      SLACK_APP_TOKEN=xapp-...
      CODE_PUPPY_WS_URL=ws://localhost:8765/ws/terminal  (default)
4. Run:
      python -m code_puppy.integrations.slack_bot

Usage in Slack
--------------
- Mention the bot:   @CodePuppy fix the login bug in auth.py
- Slash command:     /pup explain the retry logic in circuit_breaker.py
- Reply in thread:   just reply — same session resumes
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI / terminal noise stripping
# ---------------------------------------------------------------------------

# Covers CSI sequences (colours, cursor moves, etc.) and OSC sequences
_ANSI_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-9;?]*[A-Za-z]"   # CSI
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC
    r"|[@-_][0-9;]*[A-Za-z]?"  # other Fe sequences
    r"|\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]"  # param + final
    r")"
)
# Carriage returns, backspaces, and other control characters except \n and \t
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]")
# Collapse duplicate blank lines
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_ansi(raw: bytes) -> str:
    """Decode bytes, strip ANSI escape sequences and control chars."""
    text = raw.decode("utf-8", errors="replace")
    text = _ANSI_RE.sub("", text)
    text = _CTRL_RE.sub("", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# PTY session client  (wraps /ws/terminal)
# ---------------------------------------------------------------------------

# How long to wait after the last output chunk before declaring the
# response "done" and returning it to Slack.
_OUTPUT_IDLE_TIMEOUT = 3.0
# Hard upper limit per message
_OUTPUT_HARD_TIMEOUT = 120.0
# Maximum chars of output to post back (Slack block limit ~3000)
_MAX_OUTPUT_CHARS = 2800


class PtySession:
    """Manages a single code_puppy PTY WebSocket session."""

    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._ws: Any = None
        self._session_id: str | None = None

    async def connect(self) -> None:
        try:
            import websockets  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "websockets package is required: pip install websockets"
            ) from exc

        self._ws = await websockets.connect(self._ws_url)
        # First message is always the session handshake
        msg = await self._ws.recv()
        import json

        data = json.loads(msg)
        if data.get("type") == "session":
            self._session_id = data["id"]
        logger.info("PTY session connected: %s", self._session_id)

    async def send_prompt(self, text: str) -> str:
        """Send *text* to the PTY and collect output until idle."""
        import json

        if self._ws is None:
            raise RuntimeError("Not connected — call connect() first")

        # Send input + newline
        await self._ws.send(json.dumps({"type": "input", "data": text + "\n"}))

        chunks: list[str] = []
        deadline = asyncio.get_event_loop().time() + _OUTPUT_HARD_TIMEOUT

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw_msg = await asyncio.wait_for(
                    self._ws.recv(), timeout=min(_OUTPUT_IDLE_TIMEOUT, remaining)
                )
                msg = json.loads(raw_msg)
                if msg.get("type") == "output":
                    raw_bytes = base64.b64decode(msg["data"])
                    chunks.append(strip_ansi(raw_bytes))
            except asyncio.TimeoutError:
                # No new output for _OUTPUT_IDLE_TIMEOUT → response is done
                break

        output = "\n".join(chunks).strip()
        # Truncate if too long
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n…(truncated)"
        return output

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None


# ---------------------------------------------------------------------------
# Session registry  (thread_ts → PtySession)
# ---------------------------------------------------------------------------


class SessionRegistry:
    """Maps Slack thread timestamps to persistent PTY sessions."""

    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._sessions: dict[str, PtySession] = {}

    async def get_or_create(self, thread_ts: str) -> PtySession:
        if thread_ts not in self._sessions:
            session = PtySession(self._ws_url)
            await session.connect()
            self._sessions[thread_ts] = session
            logger.info("New PTY session for thread %s", thread_ts)
        return self._sessions[thread_ts]

    async def close_all(self) -> None:
        for session in self._sessions.values():
            await session.close()
        self._sessions.clear()


# ---------------------------------------------------------------------------
# Slack app
# ---------------------------------------------------------------------------


def _format_response(text: str) -> list[dict]:
    """Wrap response in Slack Block Kit blocks."""
    if not text:
        text = "_(no output)_"

    # Split into code and prose blocks heuristically
    blocks: list[dict] = []
    code_re = re.compile(r"(```[\s\S]*?```)", re.MULTILINE)
    parts = code_re.split(text)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("```") and part.endswith("```"):
            inner = part[3:-3].strip()
            blocks.append(
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_preformatted",
                            "elements": [{"type": "text", "text": inner}],
                        }
                    ],
                }
            )
        else:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": part}})

    if not blocks:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "_(no output)_"}}
        )
    return blocks


def create_slack_app(ws_url: str) -> Any:
    """Build and return a configured Slack Bolt App."""
    try:
        from slack_bolt import App  # type: ignore[import]
        from slack_bolt.adapter.socket_mode import SocketModeHandler  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "slack-bolt is required: pip install 'code-puppy[slack]'"
        ) from exc

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if not bot_token or not app_token:
        raise RuntimeError(
            "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables."
        )

    app = App(token=bot_token)
    registry = SessionRegistry(ws_url)

    async def _handle(text: str, thread_ts: str, say: Any) -> None:
        """Core handler: route text to PTY, post response."""
        try:
            session = await registry.get_or_create(thread_ts)
            thinking = await say(
                text=":hourglass_flowing_sand: Working on it…",
                thread_ts=thread_ts,
            )
            output = await session.send_prompt(text)
            blocks = _format_response(output)
            await say(
                blocks=blocks,
                text=output[:200],  # fallback text for notifications
                thread_ts=thread_ts,
            )
            # Delete the "thinking" placeholder
            try:
                await app.client.chat_delete(
                    channel=thinking["channel"],
                    ts=thinking["ts"],
                )
            except Exception:
                pass
        except Exception as exc:
            logger.exception("Error handling Slack message")
            await say(
                text=f":x: Error: {exc}",
                thread_ts=thread_ts,
            )

    # --- app_mention handler ---
    @app.event("app_mention")
    def handle_mention(event: dict, say: Any) -> None:
        text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
        thread_ts = event.get("thread_ts") or event["ts"]
        asyncio.run(_handle(text, thread_ts, say))

    # --- direct message handler ---
    @app.event("message")
    def handle_dm(event: dict, say: Any) -> None:
        # Ignore bot messages and subtypes (edits, deletes, etc.)
        if event.get("bot_id") or event.get("subtype"):
            return
        # Only handle DMs (channel_type == "im") or thread replies
        channel_type = event.get("channel_type", "")
        if channel_type not in ("im",) and not event.get("thread_ts"):
            return
        text = event.get("text", "").strip()
        thread_ts = event.get("thread_ts") or event["ts"]
        asyncio.run(_handle(text, thread_ts, say))

    # --- /pup slash command ---
    @app.command("/pup")
    def handle_slash_pup(ack: Any, respond: Any, command: dict) -> None:
        ack()
        text = command.get("text", "").strip()
        if not text:
            respond(text="Usage: `/pup <your prompt>`")
            return
        # Use command ts as thread key (each slash command is its own thread)
        thread_ts = str(command.get("trigger_id", "global"))

        async def _run() -> None:
            try:
                session = await registry.get_or_create(thread_ts)
                output = await session.send_prompt(text)
                blocks = _format_response(output)
                respond(blocks=blocks, text=output[:200])
            except Exception as exc:
                logger.exception("Error handling /pup command")
                respond(text=f":x: Error: {exc}")

        asyncio.run(_run())

    return app, app_token, registry


def main() -> None:
    """Entry point: start the Slack bot in Socket Mode."""
    logging.basicConfig(level=logging.INFO)
    ws_url = os.environ.get(
        "CODE_PUPPY_WS_URL", "ws://localhost:8765/ws/terminal"
    )

    try:
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as exc:
        raise SystemExit(
            "Install slack extras first: pip install 'code-puppy[slack]'"
        ) from exc

    app, app_token, registry = create_slack_app(ws_url)

    logger.info("🐶 Code Puppy Slack bot starting (Socket Mode)…")
    handler = SocketModeHandler(app, app_token)
    try:
        handler.start()
    finally:
        asyncio.run(registry.close_all())


if __name__ == "__main__":
    main()
