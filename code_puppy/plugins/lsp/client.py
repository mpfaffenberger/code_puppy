"""Minimal asynchronous LSP 3.17 stdio client."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def path_to_uri(path: Path | str) -> str:
    return Path(path).expanduser().resolve().as_uri()


def uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri
    return unquote(parsed.path)


async def read_lsp_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    headers: dict[str, str] = {}
    while True:
        line = await reader.readline()
        if not line:
            raise EOFError("Language server closed stdout")
        if line in {b"\r\n", b"\n"}:
            break
        key, _, value = line.decode("ascii").partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers["content-length"])
    return json.loads((await reader.readexactly(length)).decode("utf-8"))


def encode_lsp_message(message: dict[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


class LSPClient:
    def __init__(
        self,
        command: list[str],
        root: Path,
        language_id: str,
        *,
        request_timeout: float = 20.0,
    ):
        if not command:
            raise ValueError("Language server command cannot be empty")
        self.command = command
        self.root = root.resolve()
        self.language_id = language_id
        self.request_timeout = request_timeout
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0
        self._opened: set[str] = set()
        self.diagnostics: dict[str, list[dict[str, Any]]] = {}

    async def start(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=str(self.root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": path_to_uri(self.root),
                "capabilities": {
                    "textDocument": {
                        "definition": {},
                        "references": {},
                        "hover": {},
                        "publishDiagnostics": {},
                    },
                    "workspace": {"symbol": {}},
                },
                "clientInfo": {"name": "mist"},
            },
        )
        await self.notify("initialized", {})

    async def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                message = await read_lsp_message(self.process.stdout)
                if "id" in message and message["id"] in self._pending:
                    future = self._pending.pop(message["id"])
                    if "error" in message:
                        future.set_exception(RuntimeError(str(message["error"])))
                    else:
                        future.set_result(message.get("result"))
                elif message.get("method") == "textDocument/publishDiagnostics":
                    params = message.get("params", {})
                    self.diagnostics[params.get("uri", "")] = params.get(
                        "diagnostics", []
                    )
        except (EOFError, asyncio.CancelledError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("Language server stopped"))
            self._pending.clear()

    async def _send(self, message: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Language server is not running")
        self.process.stdin.write(encode_lsp_message(message))
        await self.process.stdin.drain()

    async def request(self, method: str, params: Any) -> Any:
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: Any) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def open_document(self, path: Path | str) -> str:
        await self.start()
        resolved = Path(path).expanduser().resolve()
        uri = path_to_uri(resolved)
        if uri not in self._opened:
            await self.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": self.language_id,
                        "version": 1,
                        "text": resolved.read_text(encoding="utf-8"),
                    }
                },
            )
            self._opened.add(uri)
        return uri

    async def text_request(
        self,
        method: str,
        path: Path | str,
        line: int,
        column: int,
        **extra: Any,
    ) -> Any:
        uri = await self.open_document(path)
        params = {
            "textDocument": {"uri": uri},
            "position": {"line": max(0, line - 1), "character": max(0, column - 1)},
            **extra,
        }
        return await self.request(method, params)

    async def close(self) -> None:
        if self.process is None:
            return
        if self.process.returncode is None:
            try:
                await self.request("shutdown", None)
                await self.notify("exit", None)
                await asyncio.wait_for(self.process.wait(), timeout=2)
            except Exception:
                self.process.terminate()
        if self._reader_task is not None:
            self._reader_task.cancel()
        self.process = None
