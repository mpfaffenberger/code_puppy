"""Pi-style newline-delimited JSON RPC facade over SessionManager."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, TextIO
from uuid import uuid4

from code_puppy.server.session_manager import SessionManager


class RPCServer:
    def __init__(self, manager: SessionManager | None = None) -> None:
        self.manager = manager or SessionManager()
        self._subscriptions: dict[str, asyncio.Task[None]] = {}
        self._write_lock = asyncio.Lock()

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        try:
            if method == "session.create":
                result = (
                    await self.manager.create_session(params.get("agent_name"))
                ).public()
            elif method == "session.list":
                result = self.manager.list_sessions()
            elif method == "session.get":
                result = self.manager.get_session(str(params["session_id"])).public()
            elif method == "session.submit":
                await self.manager.submit(
                    str(params["session_id"]), str(params["prompt"])
                )
                result = {"accepted": True}
            elif method == "session.interrupt":
                result = {
                    "interrupted": await self.manager.interrupt(
                        str(params["session_id"])
                    )
                }
            elif method == "session.fork":
                result = (
                    await self.manager.fork(
                        str(params["session_id"]),
                        message_id=params.get("message_id"),
                    )
                ).public()
            elif method == "session.events":
                record = self.manager.get_session(str(params["session_id"]))
                after = int(params.get("after", 0))
                result = [
                    event.model_dump(mode="json")
                    for event in record.events
                    if event.sequence > after
                ]
            else:
                raise ValueError(f"Unknown method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    async def serve(
        self, input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout
    ) -> None:
        try:
            while True:
                line = await asyncio.to_thread(input_stream.readline)
                if not line:
                    break
                try:
                    request = json.loads(line)
                    if not isinstance(request, dict):
                        raise ValueError("Request must be an object")
                    method = request.get("method")
                    params = request.get("params") or {}
                    if method == "session.subscribe":
                        subscription_id = self.subscribe(
                            str(params["session_id"]),
                            output_stream,
                            after=int(params.get("after", 0)),
                        )
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "result": {"subscription_id": subscription_id},
                        }
                    elif method == "session.unsubscribe":
                        removed = self.unsubscribe(str(params["subscription_id"]))
                        response = {
                            "jsonrpc": "2.0",
                            "id": request.get("id"),
                            "result": {"unsubscribed": removed},
                        }
                    else:
                        response = await self.dispatch(request)
                except Exception as exc:
                    response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": str(exc)},
                    }
                await self._write(output_stream, response)
        finally:
            tasks = list(self._subscriptions.values())
            self._subscriptions.clear()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    def subscribe(
        self, session_id: str, output_stream: TextIO, *, after: int = 0
    ) -> str:
        self.manager.get_session(session_id)
        subscription_id = uuid4().hex
        self._subscriptions[subscription_id] = asyncio.create_task(
            self._stream_events(subscription_id, session_id, after, output_stream)
        )
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        task = self._subscriptions.pop(subscription_id, None)
        if task is None:
            return False
        task.cancel()
        return True

    async def _stream_events(
        self,
        subscription_id: str,
        session_id: str,
        after: int,
        output_stream: TextIO,
    ) -> None:
        try:
            async for event in self.manager.events(session_id, after=after):
                await self._write(
                    output_stream,
                    {
                        "jsonrpc": "2.0",
                        "method": "session.event",
                        "params": {
                            "subscription_id": subscription_id,
                            "event": event.model_dump(mode="json"),
                        },
                    },
                )
        finally:
            self._subscriptions.pop(subscription_id, None)

    async def _write(self, output_stream: TextIO, payload: dict[str, Any]) -> None:
        async with self._write_lock:
            output_stream.write(json.dumps(payload, separators=(",", ":")) + "\n")
            output_stream.flush()
