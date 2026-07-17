"""Own independent agent sessions outside any particular UI client."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from code_puppy.agents.agent_manager import load_agent
from code_puppy.branding import DEFAULT_AGENT_NAME
from code_puppy.events import EventEnvelope
from code_puppy.messaging import get_message_bus
from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.messages import AgentResponseMessage, BaseMessage


class SessionState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass(slots=True)
class SessionRecord:
    id: str
    agent_name: str
    agent: Any | None = None
    state: SessionState = SessionState.IDLE
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    error: str | None = None
    sequence: int = 0
    events: deque[EventEnvelope] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[EventEnvelope]] = field(default_factory=set)
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: asyncio.Task[Any] | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "last_event_id": self.sequence,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """Multi-session runtime with replayable, isolated event streams."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        event_limit: int = 1000,
        subscriber_limit: int = 256,
        agent_factory: Callable[[str], Any] = load_agent,
        bus: MessageBus | None = None,
    ) -> None:
        from code_puppy.config import AUTOSAVE_DIR, STATE_DIR

        self.state_dir = Path(state_dir or STATE_DIR)
        self.autosave_dir = (
            self.state_dir / "server_autosaves"
            if state_dir is not None
            else Path(AUTOSAVE_DIR)
        )
        self.registry_path = self.state_dir / "server_sessions.json"
        self.event_limit = max(1, event_limit)
        self.subscriber_limit = max(1, subscriber_limit)
        self.agent_factory = agent_factory
        self.bus = bus or get_message_bus()
        self.sessions: dict[str, SessionRecord] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listener_id = self.bus.add_listener(self._on_bus_message)
        self._restore_registry()

    def close(self) -> None:
        self.bus.remove_listener(self._listener_id)

    def _capture_loop(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

    def _restore_registry(self) -> None:
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return
        for item in raw.get("sessions", []):
            try:
                state = SessionState(item.get("state", "idle"))
                if state is SessionState.RUNNING:
                    state = SessionState.INTERRUPTED
                record = SessionRecord(
                    id=str(item["id"]),
                    agent_name=str(item.get("agent_name") or DEFAULT_AGENT_NAME),
                    state=state,
                    created_at=str(item.get("created_at") or _now()),
                    updated_at=str(item.get("updated_at") or _now()),
                    error=item.get("error"),
                    sequence=int(item.get("last_event_id", 0)),
                    events=deque(maxlen=self.event_limit),
                )
                self.sessions[record.id] = record
            except (KeyError, TypeError, ValueError):
                continue
        self._persist_registry()

    def _persist_registry(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "sessions": [s.public() for s in self.sessions.values()],
        }
        tmp = self.registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.registry_path)

    async def create_session(self, agent_name: str | None = None) -> SessionRecord:
        self._capture_loop()
        name = agent_name or DEFAULT_AGENT_NAME
        record = SessionRecord(
            id=uuid4().hex,
            agent_name=name,
            agent=self.agent_factory(name),
            events=deque(maxlen=self.event_limit),
        )
        self.sessions[record.id] = record
        self._append_event(record, "session.created", {"agent_name": name})
        self._persist_registry()
        return record

    def get_session(self, session_id: str) -> SessionRecord:
        try:
            return self.sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Unknown session: {session_id}") from exc

    def list_sessions(self) -> list[dict[str, Any]]:
        return [record.public() for record in self.sessions.values()]

    def _ensure_agent(self, record: SessionRecord) -> Any:
        if record.agent is None:
            record.agent = self.agent_factory(record.agent_name)
            try:
                from code_puppy.session_storage import load_session

                history = load_session(f"server-{record.id}", self.autosave_dir)
                record.agent.set_message_history(history)
            except (FileNotFoundError, OSError, ValueError):
                pass
        return record.agent

    async def submit(self, session_id: str, prompt: str) -> asyncio.Task[Any]:
        self._capture_loop()
        record = self.get_session(session_id)
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        if record.write_lock.locked() or (record.task and not record.task.done()):
            raise RuntimeError("Session already has a prompt in progress")
        record.task = asyncio.create_task(self._run_prompt(record, prompt))
        return record.task

    async def fork(
        self, session_id: str, *, message_id: str | None = None
    ) -> SessionRecord:
        """Fork a session using the existing append-only tree representation."""
        source = self.get_session(session_id)
        from code_puppy.plugins.tree_sessions.tree import SessionTree

        tree = SessionTree(self.autosave_dir / f"server-{source.id}.jsonl")
        history = tree.history(message_id)
        forked = await self.create_session(source.agent_name)
        self._ensure_agent(forked).set_message_history(history)
        self._save_history(forked)
        self._append_event(
            forked,
            "session.forked",
            {"source_session_id": source.id, "message_id": message_id},
        )
        self._persist_registry()
        return forked

    async def _run_prompt(self, record: SessionRecord, prompt: str) -> Any:
        async with record.write_lock:
            agent = self._ensure_agent(record)
            record.state = SessionState.RUNNING
            record.error = None
            record.updated_at = _now()
            self._append_event(record, "session.running", {"prompt": prompt})
            self._persist_registry()
            token = self.bus.push_session_context(record.id)
            from code_puppy.server.context import (
                push_headless_transport,
                reset_headless_transport,
            )

            headless_token = push_headless_transport()
            try:
                result = await agent.run_with_mcp(prompt)
                if result is not None and getattr(result, "output", None) is not None:
                    self.bus.emit(
                        AgentResponseMessage(
                            content=str(result.output),
                            is_markdown=True,
                            session_id=record.id,
                        )
                    )
                if result is not None and hasattr(result, "all_messages"):
                    agent.set_message_history(list(result.all_messages()))
                record.state = SessionState.IDLE
                self._append_event(record, "session.idle", {})
                return result
            except asyncio.CancelledError:
                record.state = SessionState.INTERRUPTED
                self._append_event(record, "session.interrupted", {})
                raise
            except Exception as exc:
                record.state = SessionState.ERROR
                record.error = str(exc)
                self._append_event(record, "session.error", {"error": str(exc)})
                return None
            finally:
                reset_headless_transport(headless_token)
                self.bus.reset_session_context(token)
                record.updated_at = _now()
                self._save_history(record)
                self._persist_registry()

    async def interrupt(self, session_id: str) -> bool:
        record = self.get_session(session_id)
        task = record.task
        if task is None or task.done():
            return False
        from code_puppy.tools.command_runner import kill_all_running_shell_processes

        kill_all_running_shell_processes()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    def share(self, session_id: str) -> tuple[str, Path]:
        """Create an explicitly requested, redacted, read-only local share."""
        record = self.get_session(session_id)
        agent = self._ensure_agent(record)
        from code_puppy.sharing import export_session_html

        share_id = uuid4().hex
        destination = self.state_dir / "shares" / f"{share_id}.html"
        export_session_html(
            agent.get_message_history(),
            destination,
            title=f"Mist session {session_id[:8]}",
        )
        return share_id, destination

    def _save_history(self, record: SessionRecord) -> None:
        agent = record.agent
        if agent is None:
            return
        try:
            history = list(agent.get_message_history())
            from code_puppy.plugins.tree_sessions.tree import SessionTree
            from code_puppy.session_storage import save_session

            name = f"server-{record.id}"
            save_session(
                history=history,
                session_name=name,
                base_dir=self.autosave_dir,
                timestamp=_now(),
                token_estimator=getattr(
                    agent, "estimate_tokens_for_message", lambda _: 0
                ),
                auto_saved=True,
            )
            SessionTree(self.autosave_dir / f"{name}.jsonl").sync_history(history)
        except Exception:
            # A persistence failure must not turn a completed model run into an error.
            return

    def _on_bus_message(self, message: BaseMessage) -> None:
        if not message.session_id or message.session_id not in self.sessions:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if current is loop:
            self._append_message(message)
        else:
            loop.call_soon_threadsafe(self._append_message, message)

    def _append_message(self, message: BaseMessage) -> None:
        record = self.sessions.get(message.session_id or "")
        if record is None:
            return
        record.sequence += 1
        self._publish(
            record, EventEnvelope.from_message(message, sequence=record.sequence)
        )

    def _append_event(
        self, record: SessionRecord, event_type: str, data: dict[str, Any]
    ) -> EventEnvelope:
        record.sequence += 1
        event = EventEnvelope(
            sequence=record.sequence,
            type=event_type,
            session_id=record.id,
            data=data,
        )
        self._publish(record, event)
        return event

    def _publish(self, record: SessionRecord, event: EventEnvelope) -> None:
        record.events.append(event)
        lagged = 0
        for subscriber in tuple(record.subscribers):
            if subscriber.full():
                try:
                    subscriber.get_nowait()
                    lagged += 1
                except asyncio.QueueEmpty:
                    pass
            subscriber.put_nowait(event)
        if lagged:
            record.sequence += 1
            marker = EventEnvelope(
                sequence=record.sequence,
                type="stream.lagged",
                session_id=record.id,
                data={"lagged_subscribers": lagged, "reconnect_after": event.sequence},
            )
            record.events.append(marker)
            for subscriber in tuple(record.subscribers):
                if subscriber.full():
                    try:
                        subscriber.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                subscriber.put_nowait(marker)

    async def events(
        self, session_id: str, *, after: int = 0
    ) -> AsyncIterator[EventEnvelope]:
        self._capture_loop()
        record = self.get_session(session_id)
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(self.subscriber_limit)
        record.subscribers.add(queue)
        try:
            replay_cutoff = record.sequence
            for event in tuple(record.events):
                if after < event.sequence <= replay_cutoff:
                    yield event
            while True:
                event = await queue.get()
                if event.sequence > replay_cutoff:
                    yield event
        finally:
            record.subscribers.discard(queue)
