"""Read-only views of the files Code Puppy 0.0.x wrote.

Nothing here writes, renames or deletes: 0.0.x keeps working beside 1.0.
Unreadable or malformed files read as empty and are reported by the caller.
"""

from __future__ import annotations

import configparser
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_puppy import identity

CONFIG_SECTION = "puppy"
MODEL_FILES = ("models.json", "extra_models.json")


@dataclass(frozen=True, kw_only=True)
class LegacyFiles:
    """Where 0.0.x kept the state worth carrying over."""

    config: Path
    mcp_servers: Path
    models: tuple[Path, ...]

    def existing(self) -> list[Path]:
        return [
            path
            for path in (self.config, self.mcp_servers, *self.models)
            if path.is_file()
        ]

    def fingerprint(self) -> str:
        """A hash of every existing file's bytes; ``''`` when there are none."""
        files = self.existing()
        if not files:
            return ""
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.name.encode())
            digest.update(b"\0")
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
            digest.update(b"\0")
        return digest.hexdigest()


def legacy_files() -> LegacyFiles:
    config, data = identity.config_dir(), identity.data_dir()
    return LegacyFiles(
        config=config / "puppy.cfg",
        mcp_servers=config / "mcp_servers.json",
        models=tuple(data / name for name in MODEL_FILES),
    )


def read_config(path: Path) -> dict[str, str]:
    """The ``[puppy]`` section of ``puppy.cfg``; option names are lowercase."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}
    if not parser.has_section(CONFIG_SECTION):
        return {}
    return dict(parser.items(CONFIG_SECTION))


def read_json_object(path: Path) -> dict[str, Any]:
    """The JSON object in ``path``; ``{}`` when it is missing, broken, or not an object.

    0.0.x files are read, never repaired, so anything unreadable is simply not
    carried over. ``legacy_sessions`` reads its envelopes through this too, so
    the two cannot drift apart.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_mcp_servers(path: Path) -> dict[str, dict[str, Any]]:
    """Servers by name, from either wrapper key 0.0.x accepted."""
    data = read_json_object(path)
    servers = data.get("mcp_servers")
    if servers is None:
        servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return {}
    return {str(name): raw for name, raw in servers.items() if isinstance(raw, dict)}


def read_models(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    """The 0.0.x model catalog: later files override earlier ones by name."""
    catalog: dict[str, dict[str, Any]] = {}
    for path in paths:
        for name, entry in read_json_object(path).items():
            if isinstance(entry, dict):
                catalog[str(name)] = entry
    return catalog
