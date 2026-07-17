"""Small async SDK for Mist's HTTP and embedded session APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

import httpx

from code_puppy.events import EventEnvelope
from code_puppy.server.session_manager import SessionManager


class SessionBackend(Protocol):
    async def create_session(self, agent_name: str | None = None) -> dict[str, Any]: ...
    async def list_sessions(self) -> list[dict[str, Any]]: ...
    async def get_session(self, session_id: str) -> dict[str, Any]: ...
    async def submit(self, session_id: str, prompt: str) -> None: ...
    async def interrupt(self, session_id: str) -> bool: ...
    async def fork(
        self, session_id: str, message_id: str | None = None
    ) -> dict[str, Any]: ...
    def events(
        self, session_id: str, *, after: int = 0
    ) -> AsyncIterator[EventEnvelope]: ...


class AgentClient:
    """HTTP client for a running Mist server."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(timeout, read=None),
        )

    async def __aenter__(self) -> "AgentClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def create_session(self, agent_name: str | None = None) -> dict[str, Any]:
        response = await self._http.post("/session", json={"agent_name": agent_name})
        response.raise_for_status()
        return response.json()

    async def list_sessions(self) -> list[dict[str, Any]]:
        response = await self._http.get("/sessions")
        response.raise_for_status()
        return response.json()["sessions"]

    async def get_session(self, session_id: str) -> dict[str, Any]:
        response = await self._http.get(f"/session/{session_id}")
        response.raise_for_status()
        return response.json()

    async def submit(self, session_id: str, prompt: str) -> None:
        response = await self._http.post(
            f"/session/{session_id}/message", json={"prompt": prompt}
        )
        response.raise_for_status()

    async def interrupt(self, session_id: str) -> bool:
        response = await self._http.post(f"/session/{session_id}/interrupt")
        response.raise_for_status()
        return bool(response.json()["interrupted"])

    async def fork(
        self, session_id: str, message_id: str | None = None
    ) -> dict[str, Any]:
        response = await self._http.post(
            f"/session/{session_id}/fork", json={"message_id": message_id}
        )
        response.raise_for_status()
        return response.json()

    async def events(
        self, session_id: str, *, after: int = 0
    ) -> AsyncIterator[EventEnvelope]:
        headers = {"Last-Event-ID": str(after)} if after else None
        async with self._http.stream(
            "GET", f"/session/{session_id}/events", headers=headers
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    yield EventEnvelope.model_validate_json(line[6:])

    async def session(self, agent_name: str | None = None) -> "Session":
        data = await self.create_session(agent_name)
        return Session(self, data["id"])


class InProcessAgentClient:
    """SDK backend that skips HTTP while preserving the same contract."""

    def __init__(self, manager: SessionManager | None = None) -> None:
        self.manager = manager or SessionManager()

    async def close(self) -> None:
        self.manager.close()

    async def create_session(self, agent_name: str | None = None) -> dict[str, Any]:
        return (await self.manager.create_session(agent_name)).public()

    async def list_sessions(self) -> list[dict[str, Any]]:
        return self.manager.list_sessions()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return self.manager.get_session(session_id).public()

    async def submit(self, session_id: str, prompt: str) -> None:
        await self.manager.submit(session_id, prompt)

    async def interrupt(self, session_id: str) -> bool:
        return await self.manager.interrupt(session_id)

    async def fork(
        self, session_id: str, message_id: str | None = None
    ) -> dict[str, Any]:
        return (await self.manager.fork(session_id, message_id=message_id)).public()

    async def events(
        self, session_id: str, *, after: int = 0
    ) -> AsyncIterator[EventEnvelope]:
        async for event in self.manager.events(session_id, after=after):
            yield event

    async def session(self, agent_name: str | None = None) -> "Session":
        data = await self.create_session(agent_name)
        return Session(self, data["id"])


@dataclass(slots=True)
class Session:
    client: SessionBackend
    id: str

    async def submit(self, prompt: str) -> AsyncIterator[EventEnvelope]:
        current = await self.client.get_session(self.id)
        after = int(current.get("last_event_id", 0))
        await self.client.submit(self.id, prompt)
        async for event in self.client.events(self.id, after=after):
            yield event
            if event.type in {
                "session.idle",
                "session.error",
                "session.interrupted",
                "session.done",
            }:
                break

    async def interrupt(self) -> bool:
        return await self.client.interrupt(self.id)

    async def fork(self, message_id: str | None = None) -> "Session":
        data = await self.client.fork(self.id, message_id)
        return Session(self.client, data["id"])

    async def history(self) -> list[EventEnvelope]:
        """Return the currently retained replay window."""
        events: list[EventEnvelope] = []
        async for event in self.client.events(self.id):
            events.append(event)
            if event.sequence >= int(
                (await self.client.get_session(self.id))["last_event_id"]
            ):
                break
        return events


def event_to_json(event: EventEnvelope) -> str:
    """Compatibility helper for JSONL consumers."""
    return json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
