"""ACP Agent implementation for Code Puppy.

Bridges Code Puppy's pydantic-ai agent system to the Agent Client Protocol
using the official ``agent-client-protocol`` Python SDK.

This single module replaces the previous 13+ file infrastructure
(stdio_server, acp_server, session_store, event_store, event_types,
tool_approvals, hitl_bridge, filesystem_ops, terminal_ops,
message_utils, run_engine, uvicorn_compat, commands) by leveraging
what the SDK already provides.

Usage:
    from code_puppy.plugins.acp_gateway.agent import CodePuppyAgent
    await run_agent(CodePuppyAgent())
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, Optional
from uuid import uuid4

from acp import (
    Agent,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    text_block,
    update_agent_message,
    update_agent_thought_text,
    start_tool_call,
    update_tool_call,
    tool_content,
)
from acp.interfaces import Client
from acp.schema import (
    AudioContentBlock,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    HttpMcpServer,
    ImageContentBlock,
    Implementation,
    McpServerStdio,
    ResourceContentBlock,
    SseMcpServer,
    TextContentBlock,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_AGENT_NAME = os.getenv("ACP_AGENT_NAME", "code-puppy")


# ---------------------------------------------------------------------------
# Session state (lightweight — SDK handles transport/protocol)
# ---------------------------------------------------------------------------

class _SessionState:
    """Minimal per-session state for multi-turn conversations.

    Tracks pydantic-ai message history so successive prompts within
    the same ACP session share conversational context.
    """

    __slots__ = ("session_id", "agent_name", "message_history")

    def __init__(self, session_id: str, agent_name: str = DEFAULT_AGENT_NAME) -> None:
        self.session_id = session_id
        self.agent_name = agent_name
        self.message_history: list = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
) -> str:
    """Pull plain text out of ACP content blocks."""
    parts: list[str] = []
    for block in prompt:
        text = (
            block.get("text", "")
            if isinstance(block, dict)
            else getattr(block, "text", "")
        )
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _safe_serialize_args(args: Any) -> dict:
    """Safely serialize tool args for logging / event payloads."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return {
            k: (str(v)[:200] if isinstance(v, str) and len(str(v)) > 200 else v)
            for k, v in args.items()
        }
    try:
        return {"raw": str(args)[:500]}
    except Exception:
        return {}


def _extract_plan_steps(thinking_content: str) -> list[dict]:
    """Try to extract structured plan steps from agent thinking."""
    steps: list[dict] = []
    patterns = [
        r"(?:^|\n)\s*(\d+)[.)]+\s+(.+)",
        r"(?:^|\n)\s*[Ss]tep\s+(\d+)[:.]+\s*(.+)",
        r"(?:^|\n)\s*[-*]\s+(.+)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, thinking_content)
        if len(matches) >= 2:
            for i, match in enumerate(matches):
                if isinstance(match, tuple):
                    step_num = match[0] if match[0].isdigit() else str(i + 1)
                    desc = match[-1].strip()
                else:
                    step_num = str(i + 1)
                    desc = match.strip()
                steps.append({"step": int(step_num), "description": desc[:200]})
            break
    return steps


# ---------------------------------------------------------------------------
# CodePuppyAgent — the only class you need
# ---------------------------------------------------------------------------

class CodePuppyAgent(Agent):
    """ACP Agent that bridges to Code Puppy's pydantic-ai agent system.

    Implements the full Agent protocol.  The SDK handles all transport
    concerns (stdio JSON-RPC, session lifecycle, content blocks, etc.).
    This class only contains the *business logic*: loading a Code Puppy
    agent, running a prompt through pydantic-ai, and streaming results
    back through the SDK's ``Client`` interface.
    """

    def __init__(self, default_agent: str = DEFAULT_AGENT_NAME) -> None:
        self._conn: Optional[Client] = None
        self._default_agent = default_agent
        self._sessions: Dict[str, _SessionState] = {}
        # Track running tasks for cancellation
        self._running_tasks: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # ACP lifecycle
    # ------------------------------------------------------------------

    def on_connect(self, conn: Client) -> None:
        """Called by the SDK when the transport is established."""
        self._conn = conn
        logger.info("ACP connection established")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Handshake — return supported protocol version."""
        logger.info(
            "ACP initialize: protocol_version=%d, client=%s",
            protocol_version,
            client_info,
        )
        return InitializeResponse(protocol_version=protocol_version)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Create a new conversation session."""
        session_id = uuid4().hex
        self._sessions[session_id] = _SessionState(
            session_id=session_id,
            agent_name=self._default_agent,
        )
        logger.info("New session: %s (cwd=%s)", session_id, cwd)
        return NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """Run a Code Puppy agent on the user's prompt.

        Extracts text from the ACP content blocks, loads the
        appropriate pydantic-ai agent, executes the prompt, and
        streams results back via ``session_update``.
        """
        text = _extract_text(prompt)
        if not text:
            await self._send_text(session_id, "No prompt text found in the request.")
            return PromptResponse(stop_reason="end_turn")

        session = self._sessions.get(session_id)
        if session is None:
            # Auto-create session for convenience
            session = _SessionState(session_id=session_id, agent_name=self._default_agent)
            self._sessions[session_id] = session

        logger.info(
            "[%s] prompt (agent=%s): %s",
            session_id,
            session.agent_name,
            text[:120],
        )

        try:
            result_text, tool_events = await self._run_agent(session, text)

            # Stream tool events as thoughts for visibility
            await self._stream_tool_events(session_id, tool_events)

            # Send the final agent response
            await self._send_text(session_id, result_text)

            return PromptResponse(stop_reason="end_turn")

        except asyncio.CancelledError:
            logger.info("[%s] prompt cancelled", session_id)
            return PromptResponse(stop_reason="cancelled")

        except Exception:
            logger.exception("[%s] prompt failed", session_id)
            await self._send_text(
                session_id,
                f"[error] Agent '{session.agent_name}' encountered an error. "
                f"Check server logs for details.",
            )
            return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel a running prompt."""
        task = self._running_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
            logger.info("[%s] cancellation requested", session_id)

    # ------------------------------------------------------------------
    # Extension methods (custom Code Puppy features)
    # ------------------------------------------------------------------

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle custom extension methods.

        Supported extensions:
            - ``x/list-agents``: List available Code Puppy agents.
            - ``x/set-agent``:   Switch the agent for a session.
            - ``x/agent-info``:  Get metadata for a specific agent.
        """
        if method == "x/list-agents":
            return await self._ext_list_agents()
        elif method == "x/set-agent":
            return self._ext_set_agent(params)
        elif method == "x/agent-info":
            return await self._ext_agent_info(params)
        else:
            return {"error": f"Unknown extension method: {method}"}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle custom extension notifications (fire-and-forget)."""
        logger.debug("Extension notification: %s %s", method, params)

    # ------------------------------------------------------------------
    # Core execution bridge to pydantic-ai
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        session: _SessionState,
        prompt_text: str,
    ) -> tuple[str, list[dict]]:
        """Load a Code Puppy agent and execute the prompt through pydantic-ai.

        Headless execution — no signal handlers, no spinners, no keyboard
        listeners.  Restores and persists message history for multi-turn
        conversations within the ACP session.

        Returns:
            ``(result_text, tool_events)``
        """
        from code_puppy.agents import load_agent

        agent = load_agent(session.agent_name)

        # Build (or reuse) the underlying pydantic-ai Agent
        pydantic_agent = (
            agent.code_generation_agent or agent.reload_code_generation_agent()
        )

        # Restore session history (empty list on first turn)
        agent.set_message_history(session.message_history)
        history = agent.get_message_history()

        # Prepend system prompt on first turn only, mirroring
        # BaseAgent.run_with_mcp behaviour.
        if len(history) == 0:
            from code_puppy.model_utils import prepare_prompt_for_model

            system_prompt = agent.get_full_system_prompt()
            puppy_rules = agent.load_puppy_rules()
            if puppy_rules:
                system_prompt += f"\n{puppy_rules}"

            prepared = prepare_prompt_for_model(
                model_name=agent.get_model_name() or "default",
                system_prompt=system_prompt,
                user_prompt=prompt_text,
                prepend_system_to_user=True,
            )
            prompt_text = prepared.user_prompt

        # Run the agent (headless)
        result = await pydantic_agent.run(
            prompt_text,
            message_history=history,
        )

        # Persist updated conversation for future turns
        if hasattr(result, "all_messages"):
            session.message_history = list(result.all_messages())
        else:
            session.message_history = agent.get_message_history()

        logger.debug(
            "[%s] session %s now has %d messages",
            session.agent_name,
            session.session_id,
            len(session.message_history),
        )

        text = self._extract_result_text(result)
        tool_events = self._extract_tool_events(result)
        return text, tool_events

    # ------------------------------------------------------------------
    # Result extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_result_text(result: Any) -> str:
        """Pull text from a pydantic-ai RunResult."""
        if result is None:
            return ""
        # pydantic-ai >= 0.1 uses .output, older uses .data
        output = getattr(result, "output", None)
        if output is not None:
            return str(output)
        data = getattr(result, "data", None)
        if data is not None:
            return str(data)
        return str(result)

    @staticmethod
    def _extract_tool_events(result: Any) -> list[dict]:
        """Extract tool-call events from a pydantic-ai result for ACP visibility."""
        events: list[dict] = []
        try:
            from pydantic_ai.messages import (
                ModelRequest,
                ModelResponse,
                ThinkingPart,
                ToolCallPart,
                ToolReturnPart,
            )

            all_messages_fn = getattr(result, "all_messages", None)
            if all_messages_fn is None:
                return events

            for msg in all_messages_fn():
                if isinstance(msg, ModelResponse):
                    for part in msg.parts:
                        if isinstance(part, ToolCallPart):
                            events.append({
                                "type": "tool_call",
                                "tool_name": part.tool_name,
                                "tool_call_id": getattr(part, "tool_call_id", None),
                                "args": _safe_serialize_args(part.args),
                            })
                        elif isinstance(part, ThinkingPart):
                            content = part.content or ""
                            events.append({
                                "type": "thinking",
                                "content": content[:500],
                            })
                            plan_steps = _extract_plan_steps(content)
                            if plan_steps:
                                events.append({
                                    "type": "plan",
                                    "steps": plan_steps,
                                })
                elif isinstance(msg, ModelRequest):
                    for part in msg.parts:
                        if isinstance(part, ToolReturnPart):
                            events.append({
                                "type": "tool_result",
                                "tool_call_id": getattr(part, "tool_call_id", None),
                                "tool_name": getattr(part, "tool_name", None),
                                "content": str(part.content)[:1000] if part.content else "",
                            })
        except ImportError:
            logger.debug("pydantic_ai messages not available for tool extraction")
        except Exception:
            logger.exception("Error extracting tool events")
        return events

    # ------------------------------------------------------------------
    # Streaming helpers (send updates back to the ACP client)
    # ------------------------------------------------------------------

    async def _send_text(self, session_id: str, text: str) -> None:
        """Send a text message chunk to the client."""
        if self._conn is None:
            logger.warning("No connection — cannot send text")
            return
        chunk = update_agent_message(text_block(text))
        await self._conn.session_update(session_id=session_id, update=chunk)

    async def _send_thought(self, session_id: str, text: str) -> None:
        """Send a thought/reasoning chunk to the client."""
        if self._conn is None:
            return
        chunk = update_agent_thought_text(text)
        await self._conn.session_update(session_id=session_id, update=chunk)

    async def _stream_tool_events(self, session_id: str, events: list[dict]) -> None:
        """Stream tool events as thoughts so the client sees agent activity."""
        if self._conn is None or not events:
            return

        for event in events:
            event_type = event.get("type", "")

            if event_type == "thinking":
                content = event.get("content", "")
                if content:
                    await self._send_thought(session_id, content)

            elif event_type == "tool_call":
                tool_name = event.get("tool_name", "unknown")
                args = event.get("args", {})
                try:
                    chunk = start_tool_call(tool_name)
                    await self._conn.session_update(
                        session_id=session_id, update=chunk
                    )
                except Exception:
                    # Fallback: send as thought if start_tool_call fails
                    await self._send_thought(
                        session_id,
                        f"[tool] {tool_name}({args})",
                    )

            elif event_type == "tool_result":
                tool_name = event.get("tool_name", "unknown")
                content = event.get("content", "")
                try:
                    chunk = update_tool_call(tool_content(content[:500]))
                    await self._conn.session_update(
                        session_id=session_id, update=chunk
                    )
                except Exception:
                    # Fallback: send as thought
                    await self._send_thought(
                        session_id,
                        f"[result] {tool_name}: {content[:200]}",
                    )

            elif event_type == "plan":
                steps = event.get("steps", [])
                if steps:
                    plan_text = "\n".join(
                        f"  {s['step']}. {s['description']}" for s in steps
                    )
                    await self._send_thought(session_id, f"Plan:\n{plan_text}")

    # ------------------------------------------------------------------
    # Extension method implementations
    # ------------------------------------------------------------------

    async def _ext_list_agents(self) -> dict[str, Any]:
        """List all available Code Puppy agents."""
        from code_puppy.plugins.acp_gateway.agent_adapter import discover_agents

        agents = await discover_agents()
        return {
            "agents": [
                {
                    "name": a.name,
                    "display_name": a.display_name,
                    "description": a.description,
                }
                for a in agents
            ]
        }

    def _ext_set_agent(self, params: dict[str, Any]) -> dict[str, Any]:
        """Switch the agent for a given session."""
        session_id = params.get("session_id", "")
        agent_name = params.get("agent_name", "")

        if not session_id or not agent_name:
            return {"error": "session_id and agent_name are required"}

        session = self._sessions.get(session_id)
        if session is None:
            return {"error": f"Unknown session: {session_id}"}

        session.agent_name = agent_name
        logger.info("[%s] agent switched to '%s'", session_id, agent_name)
        return {"status": "ok", "agent_name": agent_name}

    async def _ext_agent_info(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get metadata for a specific agent."""
        from code_puppy.plugins.acp_gateway.agent_adapter import build_agent_metadata

        agent_name = params.get("agent_name", self._default_agent)
        metadata = build_agent_metadata(agent_name)
        if metadata is None:
            return {"error": f"Agent not found: {agent_name}"}
        return metadata


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

async def run_code_puppy_agent(agent_name: str = DEFAULT_AGENT_NAME) -> None:
    """Start the Code Puppy ACP agent over stdio.

    This is the primary entry point. The SDK handles the entire
    stdio JSON-RPC transport — we just provide the Agent implementation.
    """
    logger.info("Starting Code Puppy ACP agent (default_agent=%s)", agent_name)
    await run_agent(CodePuppyAgent(default_agent=agent_name))