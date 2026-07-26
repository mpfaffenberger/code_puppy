"""``EventBridge`` — translate Code Puppy runtime events into ACP updates.

While Code Puppy runs a turn, pydantic-ai's ``event_stream_handler`` fires the
``stream_event`` callback for each streamed text/thinking delta, and the tool
layer fires ``pre_tool_call`` / ``post_tool_call``. This bridge registers those
hooks (the same seam the shipping ``frontend_emitter`` plugin uses) and maps
each event to a ``session/update`` notification sent through the SDK's
``AgentSideConnection.session_update``.

We use hooks rather than consuming the ``MessageBus`` because the bus is
single-consumer and buffers until a renderer attaches, and agent text does not
arrive there as clean deltas. See ``README.md`` → *Event source*.

Tool calls get human-friendly titles ("Edit foo.py", "Run: pytest"), a ``kind``
so the client picks the right icon, file ``locations``, and — on completion —
the unified diff as inline content so edits are visible in the client's UI.

Routing/run-context (which session is active, whether text streamed, the
open-tool-call stack) lives in ``state`` so the permission and I/O backends can
share it. This bridge is pure translation.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from acp.helpers import (
    start_tool_call,
    text_block,
    tool_content,
    update_agent_message_text,
    update_agent_thought_text,
    update_tool_call,
)
from acp.schema import ToolCallLocation

from code_puppy.callbacks import register_callback, unregister_callback
from code_puppy.plugins.acp import state
from code_puppy.tools.common import resolve_path

logger = logging.getLogger(__name__)

# Map Code Puppy tool names to ACP tool-call ``kind`` values so the client
# picks the right icon/affordance. Unknown tools fall back to "other".
_TOOL_KINDS = {
    "read_file": "read",
    "list_files": "read",
    "grep": "search",
    "edit_file": "edit",
    "create_file": "edit",
    "replace_in_file": "edit",
    "delete_snippet": "edit",
    "delete_file": "delete",
    "agent_run_shell_command": "execute",
    "agent_share_your_reasoning": "think",
}

# Human-readable verbs for building tool-call titles like "Edit foo.py".
_TOOL_VERBS = {
    "read_file": "Read",
    "list_files": "List",
    "grep": "Search",
    "edit_file": "Edit",
    "create_file": "Create",
    "replace_in_file": "Edit",
    "delete_snippet": "Edit",
    "delete_file": "Delete",
}

# Tool-arg keys that commonly carry the target file path, in priority order.
_PATH_ARG_KEYS = ("file_path", "path", "target_file", "filename")

# Cap on inline diff/output content so a huge edit never floods the client.
_MAX_DIFF_CHARS = 8000

# Interactive TUI tools that can't run headless over ACP (they'd render a
# terminal picker + read stdin, which is the JSON-RPC pipe). Until ACP ratifies
# structured elicitation (currently an RFD), we block these and steer the model
# to ask the user in plain text instead — which the client shows as a normal
# assistant message. See README → *Interactive tools*.
_INTERACTIVE_TOOLS = {"ask_user_question"}
_INTERACTIVE_BLOCK = {
    "blocked": True,
    "error_message": (
        "[BLOCKED] Interactive pickers aren't available over ACP. Ask the user "
        "your question(s) directly in your normal text response and wait for "
        "their reply — do not call this tool."
    ),
}


class EventBridge:
    """Forward Code Puppy runtime hook events to the client as updates."""

    def register(self) -> None:
        """Register the runtime hooks. Call once when the connection opens."""
        register_callback("stream_event", self._on_stream_event)
        register_callback("pre_tool_call", self._on_pre_tool_call)
        register_callback("post_tool_call", self._on_post_tool_call)

    def unregister(self) -> None:
        """Remove the runtime hooks. Call on teardown so no callbacks leak.

        Mirrors ``register`` so a closed connection leaves no dangling bridge
        callbacks wired into the global registry (which would double-emit if a
        second connection opened in the same process).
        """
        for phase, handler in (
            ("stream_event", self._on_stream_event),
            ("pre_tool_call", self._on_pre_tool_call),
            ("post_tool_call", self._on_post_tool_call),
        ):
            try:
                unregister_callback(phase, handler)
            except Exception:  # noqa: BLE001
                logger.debug(
                    "ACP: bridge unregister failed for %s", phase, exc_info=True
                )

    # ---- Hook handlers ----------------------------------------------------
    async def _on_stream_event(
        self, event_type: str, event_data: Any, agent_session_id: Optional[str] = None
    ) -> None:
        """Map streamed text/thinking to message/thought chunks.

        Two event shapes carry visible content and BOTH must be forwarded:

        * ``part_start`` -- a new text/thinking part whose *initial* content
          (``part.content``) is the opening of the message. pydantic-ai often
          packs the first token(s) here rather than in the first delta.
        * ``part_delta`` -- each subsequent chunk (``delta.content_delta``).

        Start-content and delta-content are disjoint (deltas are only the
        *additions* after the start), so emitting both reconstructs the full
        message with no overlap. Forwarding only ``part_delta`` -- as this
        bridge used to -- silently drops the opening chunk whenever the model
        front-loads it into the start event.

        The per-run ``state`` session id wins over ``agent_session_id``: the
        former is a ``ContextVar`` isolated to this prompt's task, whereas
        ``agent_session_id`` is derived from the process-wide message-bus
        session context, which a concurrent prompt on the same connection can
        overwrite. We only fall back to it when no run is active in this context.
        """
        session_id = state.get_active_session_id() or agent_session_id
        if session_id is None:
            return
        data = event_data if isinstance(event_data, dict) else {}
        if event_type == "part_start":
            part = data.get("part")
            content = getattr(part, "content", None)
            is_thinking = "Thinking" in (data.get("part_type", "") or "")
        elif event_type == "part_delta":
            delta = data.get("delta")
            content = (
                getattr(delta, "content_delta", None) if delta is not None else None
            )
            is_thinking = "Thinking" in (data.get("delta_type", "") or "")
        else:
            return
        if not content:
            return
        if is_thinking:
            update = update_agent_thought_text(content)
        else:
            state.note_streamed_text()
            update = update_agent_message_text(content)
        await self._send(session_id, update)

    async def _on_pre_tool_call(
        self, tool_name: str, tool_args: Dict[str, Any], context: Any = None
    ) -> Any:
        """Announce a tool call starting (status ``in_progress``).

        Interactive TUI tools that can't run over ACP are blocked here (via the
        ``pre_tool_call`` blocking contract) *before* we open a tool-call entry,
        so the client never sees a dangling in-progress call.
        """
        session_id = state.get_active_session_id()
        if session_id is None:
            return None
        if tool_name in _INTERACTIVE_TOOLS:
            return dict(_INTERACTIVE_BLOCK)
        tool_call_id = state.push_tool_call(tool_name)
        update = start_tool_call(
            tool_call_id,
            self._title_for(tool_name, tool_args),
            kind=_TOOL_KINDS.get(tool_name, "other"),
            status="in_progress",
            locations=self._locations_for(tool_args) or None,
            raw_input=tool_args if isinstance(tool_args, dict) else {},
        )
        await self._send(session_id, update)

    async def _on_post_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        duration_ms: float,
        context: Any = None,
    ) -> None:
        """Report a tool call finishing (status ``completed`` / ``failed``)."""
        session_id = state.get_active_session_id()
        if session_id is None:
            return
        tool_call_id = state.pop_tool_call(tool_name)
        if tool_call_id is None:
            return
        status = "completed" if self._is_success(result) else "failed"
        update = update_tool_call(
            tool_call_id,
            status=status,
            content=self._content_for(result) or None,
            raw_output=self._summarize(result),
        )
        await self._send(session_id, update)

    # ---- Helpers ----------------------------------------------------------
    @staticmethod
    def _title_for(tool_name: str, tool_args: Any) -> str:
        """Build a human-friendly tool-call title (e.g. ``Edit foo.py``)."""
        if tool_name == "agent_run_shell_command" and isinstance(tool_args, dict):
            command = str(tool_args.get("command", "")).strip()
            if command:
                short = command if len(command) <= 60 else command[:57] + "..."
                return f"Run: {short}"
        verb = _TOOL_VERBS.get(tool_name)
        path = EventBridge._first_path(tool_args)
        if verb and path:
            return f"{verb} {os.path.basename(path)}"
        return tool_name

    @staticmethod
    def _first_path(tool_args: Any) -> Optional[str]:
        if not isinstance(tool_args, dict):
            return None
        for key in _PATH_ARG_KEYS:
            value = tool_args.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _locations_for(tool_args: Any) -> List[ToolCallLocation]:
        """Extract ACP ``locations`` (files this tool touches) from its args.

        Lets the client highlight the affected file in the agent panel.
        Best-effort: empty list when no recognizable path arg is present.

        Uses ``resolve_path`` (not ``os.path.abspath``) so a relative tool-arg
        path is absolutized against the *session's* cwd -- the same base the
        tools themselves resolve against -- rather than the ACP process cwd,
        which would point the client at the wrong file.
        """
        path = EventBridge._first_path(tool_args)
        return [ToolCallLocation(path=resolve_path(path))] if path else []

    @staticmethod
    def _content_for(result: Any) -> list:
        """Attach the unified diff (if any) as an inline content block.

        File-edit tools return a ``diff`` (unified diff text). We surface it as
        a fenced ``diff`` code block so the change is visible inline in the
        client's tool-call entry, in every ACP client — independent of whether
        filesystem delegation is rendering a native diff too.
        """
        if not isinstance(result, dict):
            return []
        diff = result.get("diff")
        if not isinstance(diff, str) or not diff.strip():
            return []
        if len(diff) > _MAX_DIFF_CHARS:
            diff = diff[: _MAX_DIFF_CHARS - 3] + "..."
        return [tool_content(text_block(f"```diff\n{diff}\n```"))]

    async def _send(self, session_id: str, update: Any) -> None:
        """Emit one ``session/update`` notification, swallowing failures.

        A translation/transport hiccup on one event must never abort the agent
        run, so we log and move on.
        """
        connection = state.get_connection()
        if connection is None:
            return
        try:
            await connection.session_update(session_id, update)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to emit session/update")

    @staticmethod
    def _is_success(result: Any) -> bool:
        """Best-effort success check mirroring frontend_emitter's heuristic."""
        if isinstance(result, dict):
            if result.get("error"):
                return False
            if result.get("success") is False:
                return False
        return True

    @staticmethod
    def _summarize(result: Any) -> Any:
        """Return a JSON-safe, size-bounded view of a tool result."""
        if result is None or isinstance(result, (str, int, float, bool, dict, list)):
            if isinstance(result, str) and len(result) > 4000:
                return result[:3997] + "..."
            return result
        rendered = str(result)
        return rendered[:3997] + "..." if len(rendered) > 4000 else rendered
