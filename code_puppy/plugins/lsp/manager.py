"""Configuration and lifecycle management for language-server clients."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import LSPClient, uri_to_path


@dataclass(frozen=True, slots=True)
class ServerConfig:
    name: str
    command: list[str]
    extensions: tuple[str, ...]
    language_id: str


def config_path() -> Path:
    from code_puppy.config import CONFIG_DIR

    return Path(CONFIG_DIR) / "lsp_servers.json"


def load_configs(path: Path | None = None) -> list[ServerConfig]:
    source = path or config_path()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    configs: list[ServerConfig] = []
    for name, item in raw.items() if isinstance(raw, dict) else ():
        if not isinstance(item, dict) or not isinstance(item.get("command"), list):
            continue
        configs.append(
            ServerConfig(
                name=name,
                command=[str(part) for part in item["command"]],
                extensions=tuple(str(ext) for ext in item.get("extensions", [])),
                language_id=str(item.get("language_id", name)),
            )
        )
    return configs


class LSPManager:
    def __init__(
        self, root: Path | None = None, configs: list[ServerConfig] | None = None
    ):
        self.root = (root or Path.cwd()).resolve()
        self.configs = configs if configs is not None else load_configs()
        self.clients: dict[str, LSPClient] = {}

    def config_for_path(self, path: Path | str) -> ServerConfig:
        suffix = Path(path).suffix.lower()
        matches = [cfg for cfg in self.configs if suffix in cfg.extensions]
        if not matches:
            raise LookupError(f"No language server configured for extension {suffix!r}")
        return matches[0]

    async def client_for_path(self, path: Path | str) -> LSPClient:
        config = self.config_for_path(path)
        if config.name not in self.clients:
            self.clients[config.name] = LSPClient(
                config.command, self.root, config.language_id
            )
        client = self.clients[config.name]
        await client.start()
        return client

    async def definition(self, path: str, line: int, column: int) -> Any:
        client = await self.client_for_path(path)
        return _normalize_locations(
            await client.text_request("textDocument/definition", path, line, column)
        )

    async def references(self, path: str, line: int, column: int) -> Any:
        client = await self.client_for_path(path)
        return _normalize_locations(
            await client.text_request(
                "textDocument/references",
                path,
                line,
                column,
                context={"includeDeclaration": True},
            )
        )

    async def hover(self, path: str, line: int, column: int) -> Any:
        client = await self.client_for_path(path)
        return await client.text_request("textDocument/hover", path, line, column)

    async def diagnostics_for(self, path: str) -> list[dict[str, Any]]:
        client = await self.client_for_path(path)
        uri = await client.open_document(path)
        return client.diagnostics.get(uri, [])

    async def workspace_symbols(self, query: str) -> Any:
        if not self.configs:
            raise LookupError("No language servers configured")
        config = self.configs[0]
        client = self.clients.setdefault(
            config.name, LSPClient(config.command, self.root, config.language_id)
        )
        await client.start()
        return _normalize_locations(
            await client.request("workspace/symbol", {"query": query})
        )

    async def close(self) -> None:
        for client in list(self.clients.values()):
            await client.close()
        self.clients.clear()


def _normalize_locations(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_locations(item) for item in value]
    if isinstance(value, dict):
        result = {key: _normalize_locations(item) for key, item in value.items()}
        if "uri" in result:
            result["path"] = uri_to_path(result.pop("uri"))
        if "targetUri" in result:
            result["targetPath"] = uri_to_path(result.pop("targetUri"))
        return result
    return value


_manager: LSPManager | None = None


def get_manager() -> LSPManager:
    global _manager
    if _manager is None or _manager.root != Path.cwd().resolve():
        _manager = LSPManager()
    return _manager
