import asyncio
import json
from pathlib import Path

import pytest

from code_puppy.plugins.lsp.client import (
    encode_lsp_message,
    path_to_uri,
    read_lsp_message,
    uri_to_path,
)
from code_puppy.plugins.lsp.manager import LSPManager, load_configs


async def test_lsp_framing_round_trip():
    message = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    encoded = encode_lsp_message(message)
    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    reader.feed_eof()

    assert await read_lsp_message(reader) == message


def test_file_uri_round_trip(tmp_path: Path):
    path = tmp_path / "file with spaces.py"

    assert uri_to_path(path_to_uri(path)) == str(path.resolve())


def test_load_configs_filters_invalid_entries(tmp_path: Path):
    config = tmp_path / "lsp.json"
    config.write_text(
        json.dumps(
            {
                "python": {
                    "command": ["pyright-langserver", "--stdio"],
                    "extensions": [".py"],
                    "language_id": "python",
                },
                "broken": {"command": "not-a-list"},
            }
        )
    )

    loaded = load_configs(config)

    assert len(loaded) == 1
    assert loaded[0].name == "python"
    assert loaded[0].extensions == (".py",)


def test_manager_rejects_unconfigured_extension(tmp_path: Path):
    manager = LSPManager(root=tmp_path, configs=[])

    with pytest.raises(LookupError):
        manager.config_for_path("main.py")


def test_normalized_locations_expose_paths(tmp_path: Path):
    from code_puppy.plugins.lsp.manager import _normalize_locations

    result = _normalize_locations(
        [{"uri": path_to_uri(tmp_path / "a.py"), "range": {"start": {"line": 1}}}]
    )

    assert result[0]["path"] == str((tmp_path / "a.py").resolve())
    assert "uri" not in result[0]
