"""Tests for code_puppy.atomic_json -- the JSON counterpart to config_file's
corruption resilience, per the PUP-605 follow-up review (Andrew Tilson's
comment on #757 flagged mcp_servers.json / extra_models.json / spinners.json
as sharing the same unbounded-read / torn-write / no-lock failure modes)."""

import glob
import threading
from unittest.mock import patch

import pytest

from code_puppy import atomic_json


@pytest.fixture
def json_path(tmp_path):
    return tmp_path / "state.json"


class TestLoadJson:
    def test_missing_file_returns_default(self, json_path):
        assert atomic_json.load_json(str(json_path), default={}) == {}

    def test_missing_file_returns_none_without_default(self, json_path):
        assert atomic_json.load_json(str(json_path)) is None

    def test_loads_valid_json(self, json_path):
        json_path.write_text('{"mcp_servers": {"foo": {"type": "stdio"}}}')

        data = atomic_json.load_json(str(json_path), default={})

        assert data == {"mcp_servers": {"foo": {"type": "stdio"}}}

    def test_malformed_json_raises_corrupt_not_silently_discarded(self, json_path):
        """Unlike the INI config, a hand-edited JSON file with one typo must
        not be silently reset -- that would destroy the user's other edits."""
        json_path.write_text('{"mcp_servers": {oops not json')

        with pytest.raises(atomic_json.JsonFileCorrupt):
            atomic_json.load_json(str(json_path), default={})

        # And, critically, the file itself must still be there untouched.
        assert json_path.exists()
        assert not glob.glob(f"{json_path}.corrupted-*")

    def test_oversized_file_raises_corrupt_without_full_parse(self, json_path):
        json_path.write_text('{"k": "' + "x" * 4096 + '"}')

        with pytest.raises(atomic_json.JsonFileCorrupt):
            atomic_json.load_json(str(json_path), default={}, max_bytes=1024)

    def test_transient_os_error_propagates_not_treated_as_corrupt(self, json_path):
        json_path.write_text('{"ok": true}')

        with patch("builtins.open", side_effect=PermissionError("locked by AV")):
            with pytest.raises(PermissionError):
                atomic_json.load_json(str(json_path), default={})


class TestMutateJson:
    def test_creates_file_from_default_when_missing(self, json_path):
        result = atomic_json.mutate_json(
            str(json_path), lambda d: {**d, "added": True}, default={}
        )

        assert result == {"added": True}
        assert atomic_json.load_json(str(json_path), default={}) == {"added": True}

    def test_mutates_existing_content(self, json_path):
        json_path.write_text('{"mcp_servers": {"foo": {"type": "stdio"}}}')

        def _add_bar(data):
            data["mcp_servers"]["bar"] = {"type": "sse"}
            return data

        result = atomic_json.mutate_json(str(json_path), _add_bar, default={})

        assert set(result["mcp_servers"]) == {"foo", "bar"}
        persisted = atomic_json.load_json(str(json_path), default={})
        assert set(persisted["mcp_servers"]) == {"foo", "bar"}

    def test_corrupt_existing_file_raises_and_does_not_overwrite_it(self, json_path):
        """Mutating a file with one hand-edit typo must fail loudly rather
        than silently clobbering the rest of the user's config with just
        the new key."""
        json_path.write_text('{"mcp_servers": {oops not json')

        with pytest.raises(atomic_json.JsonFileCorrupt):
            atomic_json.mutate_json(
                str(json_path), lambda d: {**d, "added": True}, default={}
            )

        assert json_path.read_text() == '{"mcp_servers": {oops not json'

    def test_write_failure_leaves_original_untouched(self, json_path):
        json_path.write_text('{"mcp_servers": {}}')

        with patch("os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_json.mutate_json(
                    str(json_path), lambda d: {**d, "added": True}, default={}
                )

        assert json_path.read_text() == '{"mcp_servers": {}}'

    def test_concurrent_mutations_do_not_lose_updates(self, json_path):
        """This is exactly Andrew's Tier 1 scenario: two wizard flows (or a
        wizard + /mcp remove) racing mcp_servers.json must not stomp each
        other's server entry."""
        json_path.write_text('{"mcp_servers": {}}')

        def _add_server(name):
            def _mutate(data):
                data["mcp_servers"][name] = {"type": "stdio"}
                return data

            atomic_json.mutate_json(str(json_path), _mutate, default={})

        threads = [
            threading.Thread(target=_add_server, args=(f"server_{i}",))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        final = atomic_json.load_json(str(json_path), default={})
        assert set(final["mcp_servers"]) == {f"server_{i}" for i in range(8)}
