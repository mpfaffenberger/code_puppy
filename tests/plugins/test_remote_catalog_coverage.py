"""Tests for agent_skills/remote_catalog.py full coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from code_puppy.plugins.agent_skills.remote_catalog import (
    RemoteCatalogData,
    _cache_is_fresh,
    _fetch_remote_json,
    _parse_catalog,
    _read_cache,
    _safe_bool,
    _safe_int,
    _write_cache,
    fetch_remote_catalog,
)


class TestSafeInt:
    def test_none(self):
        assert _safe_int(None) == 0

    def test_valid(self):
        assert _safe_int("42") == 42

    def test_invalid(self):
        assert _safe_int("abc", 5) == 5

    def test_normal(self):
        assert _safe_int(10) == 10


class TestSafeBool:
    def test_none(self):
        assert _safe_bool(None) is False
        assert _safe_bool(None, True) is True

    def test_truthy(self):
        assert _safe_bool(1) is True

    def test_falsy(self):
        assert _safe_bool(0) is False


class TestCacheIsFresh:
    def test_no_file(self, tmp_path):
        assert _cache_is_fresh(tmp_path / "nope.json", 60) is False

    def test_fresh_file(self, tmp_path):
        p = tmp_path / "cache.json"
        p.write_text("{}")
        assert _cache_is_fresh(p, 9999) is True

    def test_stale_file(self, tmp_path):
        import os
        import time

        p = tmp_path / "cache.json"
        p.write_text("{}")
        # Set mtime to the past
        old_time = time.time() - 10000
        os.utime(p, (old_time, old_time))
        assert _cache_is_fresh(p, 60) is False

    def test_exception(self):
        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.Path.exists",
            side_effect=OSError,
        ):
            assert _cache_is_fresh(Path("/fake"), 60) is False


class TestReadCache:
    def test_no_file(self, tmp_path):
        assert _read_cache(tmp_path / "nope.json") is None

    def test_valid(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"a": 1}))
        assert _read_cache(p) == {"a": 1}

    def test_not_dict(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps([1, 2]))
        assert _read_cache(p) is None

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("not json")
        assert _read_cache(p) is None


class TestWriteCache:
    def test_success(self, tmp_path):
        p = tmp_path / "sub" / "cache.json"
        assert _write_cache(p, {"v": 1}) is True
        assert json.loads(p.read_text()) == {"v": 1}

    def test_failure(self):
        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.Path.mkdir",
            side_effect=OSError,
        ):
            assert _write_cache(Path("/cant/write"), {}) is False


class TestFetchRemoteJson:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"version": "1"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") == {"version": "1"}

    def test_not_dict(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") is None

    def test_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.reason_phrase = "Server Error"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=mock_resp
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") is None

    def test_connect_error(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("fail")

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") is None

    def test_json_decode_error(self):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("err", "doc", 0)
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") is None

    def test_unexpected_error(self):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = RuntimeError("boom")

        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog.httpx.Client",
            return_value=mock_client,
        ):
            assert _fetch_remote_json("http://example.com") is None


class TestParseCatalog:
    def test_full(self):
        raw = {
            "version": "1.0",
            "base_url": "https://example.com/skills/",
            "total_skills": 1,
            "groups": [
                {
                    "slug": "grp",
                    "skills": [
                        {
                            "name": "sk1",
                            "description": "desc",
                            "download_url": "sk1.zip",
                            "zip_size_bytes": 100,
                            "file_count": 3,
                            "contents": {
                                "has_scripts": True,
                                "has_references": False,
                                "has_license": True,
                            },
                        }
                    ],
                }
            ],
        }
        result = _parse_catalog(raw)
        assert result is not None
        assert result.version == "1.0"
        assert len(result.entries) == 1
        assert result.entries[0].name == "sk1"
        assert result.entries[0].has_scripts is True

    def test_missing_groups(self):
        result = _parse_catalog({"version": "1"})
        assert result is not None
        assert len(result.entries) == 0

    def test_non_list_groups(self):
        result = _parse_catalog({"groups": "bad"})
        assert result is not None

    def test_non_dict_group(self):
        result = _parse_catalog({"groups": ["not_a_dict"]})
        assert result is not None
        assert len(result.entries) == 0

    def test_non_list_skills(self):
        result = _parse_catalog({"groups": [{"slug": "g", "skills": "bad"}]})
        assert result is not None
        assert len(result.entries) == 0

    def test_non_dict_skill(self):
        result = _parse_catalog({"groups": [{"slug": "g", "skills": ["bad"]}]})
        assert result is not None
        assert len(result.entries) == 0

    def test_skill_missing_name(self):
        result = _parse_catalog(
            {"groups": [{"slug": "g", "skills": [{"description": "no name"}]}]}
        )
        assert result is not None
        assert len(result.entries) == 0

    def test_no_version_no_base_url(self):
        result = _parse_catalog({"groups": []})
        assert result is not None
        assert result.version == ""
        assert result.base_url == ""

    def test_no_base_url_download(self):
        raw = {
            "groups": [
                {
                    "slug": "g",
                    "skills": [{"name": "s", "download_url": "http://abs.com/s.zip"}],
                }
            ]
        }
        result = _parse_catalog(raw)
        assert result.entries[0].download_url == "http://abs.com/s.zip"

    def test_no_contents(self):
        raw = {"groups": [{"slug": "g", "skills": [{"name": "s"}]}]}
        result = _parse_catalog(raw)
        assert result.entries[0].has_scripts is False

    def test_exception(self):
        with patch(
            "code_puppy.plugins.agent_skills.remote_catalog._safe_int",
            side_effect=RuntimeError,
        ):
            assert _parse_catalog({}) is None


class TestFetchRemoteCatalog:
    def test_fresh_cache(self, tmp_path):
        cache_data = {"version": "1", "groups": []}
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value=cache_data,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                return_value=RemoteCatalogData(
                    version="1", base_url="", total_skills=0, groups=[], entries=[]
                ),
            ),
        ):
            result = fetch_remote_catalog()
            assert result is not None

    def test_fresh_cache_read_fails(self):
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value={"version": "1", "groups": []},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._write_cache",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                return_value=RemoteCatalogData(
                    version="1", base_url="", total_skills=0, groups=[], entries=[]
                ),
            ),
        ):
            result = fetch_remote_catalog()
            assert result is not None

    def test_fresh_cache_parse_fails(self):
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value={"bad": True},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                side_effect=[
                    None,
                    RemoteCatalogData(
                        version="1", base_url="", total_skills=0, groups=[], entries=[]
                    ),
                ],
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value={"version": "1", "groups": []},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._write_cache",
                return_value=True,
            ),
        ):
            result = fetch_remote_catalog()
            assert result is not None

    def test_force_refresh(self):
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value={"v": "1", "groups": []},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._write_cache",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                return_value=RemoteCatalogData(
                    version="1", base_url="", total_skills=0, groups=[], entries=[]
                ),
            ),
        ):
            result = fetch_remote_catalog(force_refresh=True)
            assert result is not None

    def test_stale_cache_remote_fails_fallback(self):
        catalog = RemoteCatalogData(
            version="1", base_url="", total_skills=0, groups=[], entries=[]
        )
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._CACHE_PATH",
                MagicMock(exists=MagicMock(return_value=True)),
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value={"version": "1", "groups": []},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                return_value=catalog,
            ),
        ):
            result = fetch_remote_catalog()
            assert result is not None

    def test_no_cache_remote_fails(self):
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._CACHE_PATH",
                MagicMock(exists=MagicMock(return_value=False)),
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value=None,
            ),
        ):
            result = fetch_remote_catalog()
            assert result is None

    def test_remote_parse_fails_fallback_cache(self):
        catalog = RemoteCatalogData(
            version="1", base_url="", total_skills=0, groups=[], entries=[]
        )
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._CACHE_PATH",
                MagicMock(exists=MagicMock(return_value=True)),
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value={"bad": True},
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._write_cache",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._parse_catalog",
                side_effect=[None, catalog],
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value={"version": "1", "groups": []},
            ),
        ):
            result = fetch_remote_catalog()
            assert result is not None

    def test_fallback_cache_read_fails(self):
        with (
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._cache_is_fresh",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._CACHE_PATH",
                MagicMock(exists=MagicMock(return_value=True)),
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._fetch_remote_json",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.agent_skills.remote_catalog._read_cache",
                return_value=None,
            ),
        ):
            result = fetch_remote_catalog()
            assert result is None
