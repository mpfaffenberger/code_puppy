"""Tests for the redirect / auth-preservation patch helpers.

The full monkey-patch is exercised via integration (running an MCP server and
hitting it with pydantic-ai). Here we just lock in behaviour of the small
helpers that govern env-var re-expansion and Authorization-header splitting,
because both are subtle and have caused production 401s.
"""

from __future__ import annotations

import os

import pytest

from code_puppy.plugins.walmart_mcp_marketplace.redirect_patch import (
    _PreserveAuthHeader,
    _reexpand_headers,
    _split_auth_from_headers,
)


class TestSplitAuthFromHeaders:
    def test_pops_authorization(self):
        plain, value = _split_auth_from_headers(
            {"Authorization": "Bearer abc", "Content-Type": "application/json"}
        )
        assert plain == {"Content-Type": "application/json"}
        assert value == "Bearer abc"

    def test_case_insensitive(self):
        plain, value = _split_auth_from_headers(
            {"authorization": "Bearer xyz", "X-Foo": "1"}
        )
        assert plain == {"X-Foo": "1"}
        assert value == "Bearer xyz"

    def test_no_auth_header(self):
        h = {"Content-Type": "application/json"}
        plain, value = _split_auth_from_headers(h)
        assert plain == {"Content-Type": "application/json"}
        assert value is None

    def test_empty_input(self):
        assert _split_auth_from_headers(None) == (None, None)
        assert _split_auth_from_headers({}) == ({}, None)


class TestReexpandHeaders:
    def test_expands_env_var(self, monkeypatch):
        monkeypatch.setenv("FOO_TEST_TOKEN", "secret123")
        out = _reexpand_headers({"Authorization": "Bearer $FOO_TEST_TOKEN"})
        assert out == {"Authorization": "Bearer secret123"}

    def test_leaves_literal_strings_alone(self):
        out = _reexpand_headers({"X-Foo": "literal-value"})
        assert out == {"X-Foo": "literal-value"}

    def test_leaves_unknown_envvar_unexpanded(self, monkeypatch):
        # If the env var is genuinely missing, expandvars returns the input.
        monkeypatch.delenv("DEFINITELY_NOT_SET_VAR", raising=False)
        out = _reexpand_headers({"Authorization": "Bearer $DEFINITELY_NOT_SET_VAR"})
        assert out == {"Authorization": "Bearer $DEFINITELY_NOT_SET_VAR"}

    def test_handles_none_and_empty(self):
        assert _reexpand_headers(None) is None
        assert _reexpand_headers({}) == {}


class TestPreserveAuthHeader:
    def test_auth_flow_attaches_header(self):
        import httpx

        auth = _PreserveAuthHeader("Bearer xyz")
        req = httpx.Request("GET", "https://example.com/")
        # auth_flow is a generator that yields the request
        flow = auth.auth_flow(req)
        out = next(flow)
        assert out.headers["Authorization"] == "Bearer xyz"

    def test_overwrites_existing_header(self):
        import httpx

        auth = _PreserveAuthHeader("Bearer NEW")
        req = httpx.Request(
            "GET", "https://example.com/", headers={"Authorization": "Bearer OLD"}
        )
        out = next(auth.auth_flow(req))
        assert out.headers["Authorization"] == "Bearer NEW"
