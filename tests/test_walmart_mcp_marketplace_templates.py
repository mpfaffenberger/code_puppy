"""Tests for the Walmart MCP marketplace plugin's pure template builder.

These tests deliberately avoid the network — they exercise only the
JSON-→-MCPServerTemplate conversion which is the most likely thing to drift
when the BFF schema changes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.plugins.walmart_mcp_marketplace.templates import (
    IMPERSONATED_EDITOR,
    PINGFED_ENV_VAR,
    WALMART_CATEGORY,
    WalmartMCPServerTemplate,
    _normalize_url,
    _split_tags,
    _transport_to_type,
    build_templates,
)

# The placeholder consumer id baked into templates pre-install. It gets
# swapped for the real BFF-resolved value by ``to_server_config``.
PLACEHOLDER_CONSUMER_ID = "<resolved-from-registry-on-install>"


class TestHelpers:
    @pytest.mark.parametrize(
        "base,endpoint,expected",
        [
            ("https://x.walmart.com", "/mcp/", "https://x.walmart.com/mcp"),
            ("x.walmart.com", "/mcp", "https://x.walmart.com/mcp"),
            ("https://x.walmart.com/", "mcp", "https://x.walmart.com//mcp"),
            ("https://x.walmart.com", "", "https://x.walmart.com"),
            ("x.walmart.com", "sse", "https://x.walmart.com/sse"),
            # Regression: trailing slash on path triggers HTTPS→HTTP 307s on
            # some Walmart servers (e.g. shelly), causing httpx to strip auth.
            ("https://shelly.walmart.com", "/mcp/", "https://shelly.walmart.com/mcp"),
            # Bare host trailing slash must NOT be eaten
            ("https://x.walmart.com/", "", "https://x.walmart.com/"),
        ],
    )
    def test_normalize_url(self, base, endpoint, expected):
        assert _normalize_url(base, endpoint) == expected

    @pytest.mark.parametrize(
        "transport,expected",
        [
            ("Streamable-HTTP", "http"),
            ("streamable_http", "http"),
            ("HTTP", "http"),
            ("SSE", "sse"),
            ("stdio", None),
            ("", None),
            (None, None),
        ],
    )
    def test_transport_to_type(self, transport, expected):
        assert _transport_to_type(transport) == expected

    def test_split_tags_csv(self):
        assert _split_tags("foo, bar ,baz") == ["foo", "bar", "baz"]

    def test_split_tags_list(self):
        assert _split_tags(["a", "b"]) == ["a", "b"]

    def test_split_tags_empty(self):
        assert _split_tags("") == []
        assert _split_tags(None) == []


class TestBuildTemplates:
    def _entry(self, **overrides):
        base = {
            "id": "uuid",
            "key": "ARK-MCP",
            "name": "ark-mcp",
            "description": "Ark stuff",
            "teamName": "Compute",
            "tags": "ark,packages",
            "githubUrl": "https://gec.example/ark",
            "environments": [
                {
                    "name": "prod",
                    "type": "PROD",
                    "mcpCapability": {
                        "displayName": "Ark",
                        "url": "https://ark-mcp.walmart.com",
                        "endpoint": "/mcp/",
                        "auth": {"type": "PingFed Token"},
                        "protocol": {"transport": "Streamable-HTTP"},
                    },
                }
            ],
        }
        base.update(overrides)
        return base

    def test_happy_path_pingfed_http(self):
        tpls = build_templates([self._entry()])
        assert len(tpls) == 1
        t = tpls[0]
        assert isinstance(t, WalmartMCPServerTemplate)
        assert t.id == "wmt-ark-mcp"
        assert t.type == "http"
        assert t.category == WALMART_CATEGORY
        assert t.config["url"] == "https://ark-mcp.walmart.com/mcp"
        # Walmart Istio routing headers + auth header are stacked together.
        # Routing headers carry placeholders pre-install; the real values
        # are pulled from the BFF detail endpoint at install time.
        headers = t.config["headers"]
        assert headers["Authorization"] == f"Bearer ${PINGFED_ENV_VAR}"
        assert headers["WM_SVC.NAME"] == "ARK-MCP"  # mirrors entry['key']
        assert headers["WM_SVC.ENV"] == "prod"
        assert headers["WM_CONSUMER.ID"] == PLACEHOLDER_CONSUMER_ID
        # Only the auth env var should be required — the consumer id is
        # resolved automatically from the BFF.
        env_vars = t.get_environment_vars()
        assert PINGFED_ENV_VAR in env_vars
        assert "WMT_CONSUMER_ID" not in env_vars
        assert t.registry_key == "ARK-MCP"
        assert "walmart" in t.tags
        assert "Compute" in t.tags

    def test_sse_no_auth(self):
        entry = self._entry()
        entry["environments"][0]["mcpCapability"]["protocol"]["transport"] = "SSE"
        entry["environments"][0]["mcpCapability"]["endpoint"] = "/sse"
        entry["environments"][0]["mcpCapability"]["auth"] = {"type": "none"}
        tpls = build_templates([entry])
        assert len(tpls) == 1
        t = tpls[0]
        assert t.type == "sse"
        # Even without auth, the Istio routing headers are still required.
        headers = t.config["headers"]
        assert "Authorization" not in headers
        assert headers["WM_SVC.NAME"] == "ARK-MCP"
        assert headers["WM_SVC.ENV"] == "prod"
        assert headers["WM_CONSUMER.ID"] == PLACEHOLDER_CONSUMER_ID
        # No env vars required at all — the consumer id is resolved from BFF
        # at install time.
        assert t.get_environment_vars() == []

    def test_schemeless_url_gets_https(self):
        entry = self._entry()
        entry["environments"][0]["mcpCapability"]["url"] = "savant.prod.walmart.com"
        tpls = build_templates([entry])
        assert tpls[0].config["url"].startswith("https://savant.prod.walmart.com")

    def test_unknown_transport_skipped(self):
        entry = self._entry()
        entry["environments"][0]["mcpCapability"]["protocol"]["transport"] = "carrier-pigeon"
        assert build_templates([entry]) == []

    def test_missing_environments_skipped(self):
        entry = self._entry()
        entry["environments"] = []
        assert build_templates([entry]) == []

    def test_missing_url_skipped(self):
        entry = self._entry()
        entry["environments"][0]["mcpCapability"].pop("url")
        assert build_templates([entry]) == []

    def test_dedupes_by_id(self):
        a = self._entry()
        b = self._entry()  # same key → same id
        tpls = build_templates([a, b])
        assert len(tpls) == 1

    def test_bad_entry_doesnt_crash_others(self):
        good = self._entry()
        bad = {"name": "broken"}  # no environments
        tpls = build_templates([bad, good])
        assert len(tpls) == 1
        assert tpls[0].name == "ark-mcp"

    def test_results_sorted_by_display_name(self):
        e1 = self._entry(key="ZEBRA", name="zebra")
        e1["environments"][0]["mcpCapability"]["displayName"] = "Zebra"
        e2 = self._entry(key="ALPHA", name="alpha")
        e2["environments"][0]["mcpCapability"]["displayName"] = "Alpha"
        tpls = build_templates([e1, e2])
        assert [t.display_name for t in tpls] == ["Alpha", "Zebra"]


# ---------------------------------------------------------------------------
# Personalization-header injection at install time
# ---------------------------------------------------------------------------


def _entry(**overrides):
    base = {
        "id": "uuid",
        "key": "APM0001365-MCP-CONFLUENCE",
        "name": "mcp-confluence",
        "description": "Confluence",
        "teamName": "Atlassian",
        "tags": "docs",
        "environments": [
            {
                "name": "prod",
                "type": "PROD",
                "mcpCapability": {
                    "displayName": "Confluence",
                    "url": "https://mcp-confluence.walmart.com",
                    "endpoint": "/mcp/",
                    "auth": {"type": "PingFed Token"},
                    "protocol": {"transport": "Streamable-HTTP"},
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _bff_detail(**header_overrides):
    """Build a fake BFF detail payload with customHeadersByEditor."""
    cursor_headers = {
        "WM_CONSUMER.ID": "cursor-consumer-uuid",
        "WM_SVC.ENV": "prod",
        "WM_SVC.NAME": "APM0001365-MCP-CONFLUENCE",
    }
    cursor_headers.update(header_overrides)
    return {
        "key": "APM0001365-MCP-CONFLUENCE",
        "personalization": {
            "customHeadersByEditor": [
                {"editor": "cursor", "headers": cursor_headers},
                {
                    "editor": "intellij",
                    "headers": {
                        "WM_CONSUMER.ID": "intellij-consumer-uuid",
                        "WM_SVC.ENV": "prod",
                        "WM_SVC.NAME": "APM0001365-MCP-CONFLUENCE",
                    },
                },
            ]
        },
    }


class TestPersonalizationInjection:
    """``WalmartMCPServerTemplate.to_server_config`` swaps placeholder
    routing headers for the real BFF-resolved values for the impersonated
    editor (cursor by default).
    """

    def test_to_server_config_injects_real_headers(self):
        tpl = build_templates([_entry()])[0]
        with patch(
            "code_puppy.plugins.walmart_mcp_marketplace.templates.fetch_marketplace_detail",
            return_value=_bff_detail(),
        ):
            cfg = tpl.to_server_config("mcp-confluence-test")

        h = cfg["headers"]
        # Real consumer id baked in \u2014 placeholder gone
        assert h["WM_CONSUMER.ID"] == "cursor-consumer-uuid"
        # Other routing headers also resolved (they were already correct, but
        # the BFF response wins so we don't drift if the registry changes).
        assert h["WM_SVC.NAME"] == "APM0001365-MCP-CONFLUENCE"
        assert h["WM_SVC.ENV"] == "prod"
        # Auth header preserved \u2014 BFF doesn't know about it.
        assert h["Authorization"] == f"Bearer ${PINGFED_ENV_VAR}"

    def test_uses_impersonated_editor(self):
        """Default editor is ``cursor`` per DISCOVERY_NOTES.md."""
        assert IMPERSONATED_EDITOR == "cursor"

    def test_no_personalization_keeps_placeholder(self):
        """Caller can spot the bad config easily \u2014 no silent 502s."""
        tpl = build_templates([_entry()])[0]
        with patch(
            "code_puppy.plugins.walmart_mcp_marketplace.templates.fetch_marketplace_detail",
            return_value={"key": "APM0001365-MCP-CONFLUENCE"},
        ):
            cfg = tpl.to_server_config("test")
        # Placeholder remains \u2014 user gets an obviously-broken value to debug
        # rather than a server that talks to the wrong upstream.
        assert cfg["headers"]["WM_CONSUMER.ID"] == PLACEHOLDER_CONSUMER_ID

    def test_bff_failure_keeps_placeholder(self):
        """Network errors during install must not crash the install flow."""
        tpl = build_templates([_entry()])[0]
        with patch(
            "code_puppy.plugins.walmart_mcp_marketplace.templates.fetch_marketplace_detail",
            side_effect=RuntimeError("BFF down"),
        ):
            cfg = tpl.to_server_config("test")
        assert cfg["headers"]["WM_CONSUMER.ID"] == PLACEHOLDER_CONSUMER_ID

    def test_no_registry_key_skips_fetch(self):
        """Defensive: a hand-constructed template without a registry key
        shouldn't trigger a pointless BFF call."""
        tpl = WalmartMCPServerTemplate(
            id="wmt-test",
            name="test",
            display_name="Test",
            description="d",
            category=WALMART_CATEGORY,
            tags=["walmart"],
            type="http",
            config={"url": "https://x.walmart.com/mcp", "headers": {"x": "y"}},
            registry_key="",  # \u2190 the thing under test
        )
        with patch(
            "code_puppy.plugins.walmart_mcp_marketplace.templates.fetch_marketplace_detail",
        ) as m:
            cfg = tpl.to_server_config("test")
        m.assert_not_called()
        # Headers untouched
        assert cfg["headers"] == {"x": "y"}

    def test_no_headers_in_config_skips_fetch(self):
        """No headers → nothing to inject into."""
        tpl = WalmartMCPServerTemplate(
            id="wmt-noh",
            name="noheaders",
            display_name="No Headers",
            description="d",
            category=WALMART_CATEGORY,
            tags=["walmart"],
            type="http",
            config={"url": "https://x.walmart.com/mcp"},
            registry_key="SOMETHING",
        )
        with patch(
            "code_puppy.plugins.walmart_mcp_marketplace.templates.fetch_marketplace_detail",
        ) as m:
            tpl.to_server_config("test")
        m.assert_not_called()


class TestExtractPersonalizationHeaders:
    """Cover the ``extract_personalization_headers`` helper directly."""

    def test_picks_requested_editor(self):
        from code_puppy.plugins.walmart_mcp_marketplace.client import (
            extract_personalization_headers,
        )
        h = extract_personalization_headers(_bff_detail(), editor="cursor")
        assert h["WM_CONSUMER.ID"] == "cursor-consumer-uuid"

    def test_falls_back_to_other_editor(self):
        """Missing editor \u2192 returns first non-empty entry. Beats nothing."""
        from code_puppy.plugins.walmart_mcp_marketplace.client import (
            extract_personalization_headers,
        )
        # Only intellij is present; ask for cursor
        detail = {
            "personalization": {
                "customHeadersByEditor": [
                    {"editor": "intellij", "headers": {"WM_CONSUMER.ID": "ij"}},
                ]
            }
        }
        h = extract_personalization_headers(detail, editor="cursor")
        assert h == {"WM_CONSUMER.ID": "ij"}

    def test_empty_detail(self):
        from code_puppy.plugins.walmart_mcp_marketplace.client import (
            extract_personalization_headers,
        )
        assert extract_personalization_headers(None) == {}
        assert extract_personalization_headers({}) == {}
        assert extract_personalization_headers({"personalization": {}}) == {}
