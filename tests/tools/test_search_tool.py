"""Unit tests for search_tool."""

from __future__ import annotations

import json
from urllib import error as url_error

import pytest

from code_puppy.tools import search_tool


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_request_json_success(monkeypatch):
    def fake_urlopen(_req, timeout=0):
        return _FakeResponse({"ok": True})

    monkeypatch.setattr(search_tool.url_request, "urlopen", fake_urlopen)

    result = search_tool._request_json("http://example", {"a": 1}, timeout=1)
    assert result == {"ok": True}


def test_request_json_invalid_json(monkeypatch):
    class BadResponse(_FakeResponse):
        def read(self) -> bytes:
            return b"not-json"

    def fake_urlopen(_req, timeout=0):
        return BadResponse({})

    monkeypatch.setattr(search_tool.url_request, "urlopen", fake_urlopen)

    with pytest.raises(search_tool.UpstreamError, match="Invalid JSON"):
        search_tool._request_json("http://example", {"a": 1}, timeout=1)


def test_request_json_rate_limited(monkeypatch):
    def fake_urlopen(_req, timeout=0):
        raise url_error.HTTPError(
            url="http://example",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(search_tool.url_request, "urlopen", fake_urlopen)
    monkeypatch.setattr(search_tool.time, "sleep", lambda *_args: None)

    with pytest.raises(search_tool.RateLimited):
        search_tool._request_json("http://example", {"a": 1}, timeout=1)


def test_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(search_tool, "CACHE_DIR", str(tmp_path))

    output = search_tool.SearchOutput(
        results=[],
        total=0,
        has_more=False,
        source="tavily",
    )
    cache_key = search_tool._cache_key({"q": "hi"})
    search_tool._save_cache(cache_key, output)

    cached = search_tool._load_cache(cache_key)
    assert cached is not None
    assert cached.total == 0


def test_search_empty_query_returns_empty():
    result = search_tool._search(
        object(),
        "  ",
        params=search_tool.SearchParams(),
    )
    assert result.results == []
    assert result.total == 0
    assert result.has_more is False


def test_sanitize_domains_dedupes_and_truncates():
    domains = [f"example{i}.com" for i in range(search_tool.MAX_DOMAIN_LIST + 5)]
    domains.insert(0, "example1.com")
    cleaned = search_tool._sanitize_domains(domains)
    assert len(cleaned) == search_tool.MAX_DOMAIN_LIST
    assert len(set(cleaned)) == len(cleaned)


def test_params_cache_dict():
    params = search_tool.SearchParams(
        max_results=3,
        safe_search=False,
        include_domains=["example.com"],
    )
    payload = params.to_cache_dict("query", "tavily")
    assert payload["query"] == "query"
    assert payload["provider"] == "tavily"
    assert payload["max_results"] == 3
    assert payload["safe_search"] is False
    assert payload["include_domains"] == ["example.com"]


def test_params_validated_clamps_max_results():
    params = search_tool.SearchParams(max_results=999)
    validated = params.validated()
    assert validated.max_results == search_tool.MAX_RESULTS_LIMIT


def test_params_validated_defaults_invalid_values():
    params = search_tool.SearchParams(
        search_depth="nope",
        topic="unknown",
        time_range="forever",
        include_domains=["EXAMPLE.COM"],
        exclude_domains=["EXAMPLE.COM"],
    )
    validated = params.validated()
    assert validated.search_depth == "basic"
    assert validated.topic is None
    assert validated.time_range is None
    assert validated.include_domains == ["example.com"]
    assert validated.exclude_domains == ["example.com"]
