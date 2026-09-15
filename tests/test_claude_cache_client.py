"""Tests for Claude cache client with token refresh on Cloudflare errors."""

import base64
import json
import time
from unittest.mock import Mock, patch

import httpx2
import pytest
from anthropic import AsyncAnthropic

from code_puppy.claude_cache_client import (
    CLAUDE_CLI_USER_AGENT,
    CLAUDE_CODE_SYSTEM_PROMPT,
    TOKEN_MAX_AGE_SECONDS,
    TOOL_PREFIX,
    ClaudeCacheAsyncClient,
)


def _create_jwt(iat: float | None = None, exp: float | None = None) -> str:
    """Create a test JWT with specified claims."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {}
    if iat is not None:
        payload["iat"] = iat
    if exp is not None:
        payload["exp"] = exp

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    signature = "fake_signature"

    return f"{header_b64}.{payload_b64}.{signature}"


@pytest.mark.asyncio
async def test_client_is_accepted_by_anthropic_sdk():
    """Guard the SDK's nominal custom-client compatibility contract."""
    client = ClaudeCacheAsyncClient()
    try:
        sdk = AsyncAnthropic(api_key="test", http_client=client)
        assert sdk._client is client
    finally:
        await client.aclose()


class TestJWTAgeDetection:
    """Test JWT age detection for proactive token refresh."""

    def test_get_jwt_age_with_iat(self):
        """Test that JWT age is calculated from iat claim."""
        # Token issued 30 minutes ago
        iat = time.time() - 1800
        token = _create_jwt(iat=iat)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is not None
        assert 1790 <= age <= 1810  # Allow for timing variance

    def test_get_jwt_age_with_exp_only(self):
        """Test that JWT age is calculated from exp claim when iat is missing."""
        # Token expires in 30 minutes (so it's about 30 mins old if 1hr lifetime)
        exp = time.time() + 1800
        token = _create_jwt(exp=exp)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is not None
        # Age should be TOKEN_MAX_AGE_SECONDS - time_until_exp = 3600 - 1800 = 1800
        assert 1790 <= age <= 1810

    def test_get_jwt_age_prefers_iat(self):
        """Test that iat claim is preferred over exp for age calculation."""
        iat = time.time() - 600  # 10 minutes ago
        exp = time.time() + 3000  # expires in 50 minutes
        token = _create_jwt(iat=iat, exp=exp)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        # Should use iat (10 mins = 600 secs) not exp
        assert age is not None
        assert 590 <= age <= 610

    def test_get_jwt_age_invalid_token(self):
        """Test that invalid tokens return None."""
        client = ClaudeCacheAsyncClient()

        assert client._get_jwt_age_seconds(None) is None
        assert client._get_jwt_age_seconds("") is None
        assert client._get_jwt_age_seconds("not.a.valid.jwt") is None
        assert client._get_jwt_age_seconds("invalid") is None

    def test_get_jwt_age_no_timestamp_claims(self):
        """Test that JWT without timestamp claims returns None."""
        token = _create_jwt()  # No iat or exp

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is None

    def test_should_refresh_token_old(self):
        """Test that old tokens (>1 hour) trigger refresh."""
        # Token issued 2 hours ago
        iat = time.time() - 7200
        token = _create_jwt(iat=iat)

        request = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is True

    def test_should_refresh_token_fresh(self):
        """Test that fresh tokens (<1 hour) don't trigger refresh."""
        # Token issued 30 minutes ago
        iat = time.time() - 1800
        token = _create_jwt(iat=iat)

        request = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is False

    def test_should_refresh_token_exactly_1_hour(self):
        """Test that token exactly 1 hour old triggers refresh."""
        # Token issued exactly 1 hour ago
        iat = time.time() - TOKEN_MAX_AGE_SECONDS
        token = _create_jwt(iat=iat)

        request = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is True

    def test_extract_bearer_token(self):
        """Test bearer token extraction from headers."""
        client = ClaudeCacheAsyncClient()

        request = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": "Bearer my_token_123"},
        )

        token = client._extract_bearer_token(request)
        assert token == "my_token_123"

    def test_extract_bearer_token_missing(self):
        """Test bearer token extraction when header is missing."""
        client = ClaudeCacheAsyncClient()

        request = httpx2.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
        )

        token = client._extract_bearer_token(request)
        assert token is None


class TestToolPrefixing:
    """Test tool name prefixing/unprefixing for Claude Code OAuth compatibility."""

    def test_prefix_tool_names_basic(self):
        """Test that tool names are prefixed correctly."""
        body = json.dumps(
            {
                "model": "claude-3",
                "tools": [
                    {"name": "read_file", "description": "Read a file"},
                    {"name": "edit_file", "description": "Edit a file"},
                ],
                "messages": [{"role": "user", "content": "Hello"}],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is not None
        data = json.loads(result)
        assert data["tools"][0]["name"] == f"{TOOL_PREFIX}read_file"
        assert data["tools"][1]["name"] == f"{TOOL_PREFIX}edit_file"

    def test_prefix_tool_names_already_prefixed(self):
        """Test that already-prefixed tools are not double-prefixed."""
        body = json.dumps(
            {
                "tools": [
                    {"name": f"{TOOL_PREFIX}read_file", "description": "Read a file"},
                ],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        # Should return None since nothing was modified
        assert result is None

    def test_prefix_tool_names_no_tools(self):
        """Test that bodies without tools return None."""
        body = json.dumps(
            {
                "model": "claude-3",
                "messages": [{"role": "user", "content": "Hello"}],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is None

    def test_prefix_tool_names_invalid_json(self):
        """Test that invalid JSON returns None."""
        body = b"not valid json"

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is None

    def test_apply_claude_code_prefix_defaults_to_false(self):
        """Default constructor must NOT opt into Claude Code OAuth prefixing.

        This is the regression guard for the bug where custom_anthropic models
        were having tool names mangled with ``cp_`` even though they're not
        talking to the Claude Code OAuth endpoint.
        """
        client = ClaudeCacheAsyncClient()
        assert client._apply_claude_code_prefix is False

    def test_apply_claude_code_prefix_opt_in(self):
        """Plugins (claude_code_oauth) opt in explicitly via constructor flag."""
        client = ClaudeCacheAsyncClient(apply_claude_code_prefix=True)
        assert client._apply_claude_code_prefix is True


class TestClaudeCodeSystemPrompt:
    """The first system block must be the Claude Code fingerprint string.

    Regression guard for harness-driven summarization compaction: the
    summarizer builds its own internal Agent whose instructions bypass the
    ``prepare_model_prompt`` hook entirely, so the transport must enforce
    the invariant instead.
    """

    def test_string_system_prompt_demoted_to_second_block(self):
        """A foreign string system prompt is kept, but demoted to block two."""
        body = json.dumps(
            {
                "model": "claude-sonnet-4-5",
                "system": "You are a context summarization assistant.",
                "messages": [{"role": "user", "content": "Summarize this"}],
            }
        ).encode()

        result = ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(body)

        assert result is not None
        data = json.loads(result)
        assert data["system"][0] == {"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT}
        assert data["system"][1] == {
            "type": "text",
            "text": "You are a context summarization assistant.",
        }

    def test_string_system_prompt_already_compliant(self):
        """A compliant string system prompt is left untouched (None = no-op)."""
        body = json.dumps(
            {"system": CLAUDE_CODE_SYSTEM_PROMPT, "messages": []}
        ).encode()

        assert ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(body) is None

    def test_block_list_system_prompt_gets_prefix_block(self):
        """A block-list system prompt gains the fingerprint as block zero."""
        original_block = {"type": "text", "text": "Summarize stuff."}
        body = json.dumps({"system": [original_block], "messages": []}).encode()

        result = ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(body)

        assert result is not None
        data = json.loads(result)
        assert data["system"][0] == {"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT}
        assert data["system"][1] == original_block

    def test_block_list_already_compliant(self):
        """A block list already led by the fingerprint is left untouched."""
        body = json.dumps(
            {
                "system": [
                    {"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT},
                    {"type": "text", "text": "real system prompt"},
                ],
                "messages": [],
            }
        ).encode()

        assert ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(body) is None

    def test_missing_system_prompt_is_injected(self):
        """No system prompt at all still gets the fingerprint string."""
        body = json.dumps({"model": "claude-3", "messages": []}).encode()

        result = ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(body)

        assert result is not None
        assert json.loads(result)["system"] == CLAUDE_CODE_SYSTEM_PROMPT

    def test_invalid_json_returns_none(self):
        """Garbage bodies are passed through untouched."""
        assert (
            ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(b"not json")
            is None
        )


class TestHeaderTransformation:
    """Test header transformation for Claude Code OAuth compatibility."""

    def test_transform_headers_sets_user_agent(self):
        """Test that user-agent is set correctly."""
        headers = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert headers["user-agent"] == CLAUDE_CLI_USER_AGENT

    def test_transform_headers_adds_oauth_beta(self):
        """Test that oauth beta is always added."""
        headers = {}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "oauth-2025-04-20" in headers["anthropic-beta"]
        assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]

    def test_transform_headers_keeps_claude_code_beta_if_present(self):
        """Test that claude-code beta is kept if it was in the incoming headers."""
        headers = {
            "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14"
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "claude-code-20250219" in headers["anthropic-beta"]

    def test_transform_headers_excludes_claude_code_beta_if_not_present(self):
        """Test that claude-code beta is not added if it wasn't requested."""
        headers = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "claude-code-20250219" not in headers["anthropic-beta"]

    def test_transform_headers_removes_x_api_key(self):
        """Test that x-api-key is removed."""
        headers = {
            "x-api-key": "secret",
            "anthropic-beta": "interleaved-thinking-2025-05-14",
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "x-api-key" not in headers
        assert "X-API-Key" not in headers

    def test_transform_headers_preserves_extra_betas(self):
        """Extra betas (e.g. context-1m) should survive the transform."""
        headers = {
            "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14,context-1m-2025-08-07"
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "context-1m-2025-08-07" in headers["anthropic-beta"]
        assert "oauth-2025-04-20" in headers["anthropic-beta"]
        assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]

    def test_transform_headers_no_duplicate_required_betas(self):
        """Required betas should not be duplicated in the output."""
        headers = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        beta_str = headers["anthropic-beta"]
        assert beta_str.count("oauth-2025-04-20") == 1
        assert beta_str.count("interleaved-thinking-2025-05-14") == 1


class TestUrlBetaParam:
    """Test URL beta query parameter addition."""

    def test_add_beta_query_param(self):
        """Test that beta=true is added to URL."""
        url = httpx2.URL("https://api.anthropic.com/v1/messages")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        assert "beta=true" in str(new_url)

    def test_add_beta_query_param_preserves_existing(self):
        """Test that existing query params are preserved."""
        url = httpx2.URL("https://api.anthropic.com/v1/messages?foo=bar")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        assert "foo=bar" in str(new_url)
        assert "beta=true" in str(new_url)

    def test_add_beta_query_param_not_duplicated(self):
        """Test that beta param is not duplicated if already present."""
        url = httpx2.URL("https://api.anthropic.com/v1/messages?beta=true")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        # Should be unchanged
        assert str(new_url).count("beta") == 1


class TestSendAppliesPrefixConditionally:
    """End-to-end: ``send()`` only prefixes tool names when the flag is on.

    These tests are the actual regression guard for the bug: custom_anthropic
    routes through ``ClaudeCacheAsyncClient`` without ``apply_claude_code_prefix``
    set, so tool names sent over the wire must remain verbatim.
    """

    @pytest.mark.asyncio
    async def test_send_does_not_prefix_when_flag_off(self):
        """custom_anthropic path: tool names go out clean (no ``cp_`` prefix)."""
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            captured["url"] = str(request.url)
            response = Mock(spec=httpx2.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx2.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            # Default: apply_claude_code_prefix=False (custom_anthropic case)
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"}
            )
            request = httpx2.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "tools": [
                            {"name": "read_file", "description": "read"},
                            {"name": "edit_file", "description": "edit"},
                        ],
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ).encode(),
            )

            await client.send(request)

        assert "body" in captured, "send did not run our fake transport"
        sent = json.loads(captured["body"])
        tool_names = [t["name"] for t in sent["tools"]]
        assert tool_names == ["read_file", "edit_file"], (
            f"custom_anthropic path must not prefix tool names, got {tool_names}"
        )
        assert TOOL_PREFIX not in captured["body"].decode("utf-8")

    @pytest.mark.asyncio
    async def test_send_does_prefix_when_flag_on(self):
        """claude_code OAuth path: tool names get the ``cp_`` prefix."""
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            response = Mock(spec=httpx2.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx2.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"},
                apply_claude_code_prefix=True,
            )
            request = httpx2.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "tools": [
                            {"name": "read_file", "description": "read"},
                        ],
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        tool_names = [t["name"] for t in sent["tools"]]
        assert tool_names == [f"{TOOL_PREFIX}read_file"]

    @pytest.mark.asyncio
    async def test_send_enforces_system_prompt_when_flag_on(self):
        """claude_code OAuth path: a foreign system prompt is demoted, not led with.

        This is the harness-summarizer regression: SummarizingCompaction's
        internal Agent sends its own instructions as the system prompt.
        """
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            response = Mock(spec=httpx2.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx2.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"},
                apply_claude_code_prefix=True,
            )
            request = httpx2.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "system": "You are a context summarization assistant.",
                        "messages": [{"role": "user", "content": "summarize"}],
                    }
                ).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        assert sent["system"][0] == {"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT}
        assert sent["system"][1]["text"] == "You are a context summarization assistant."

    @pytest.mark.asyncio
    async def test_send_leaves_system_prompt_alone_when_flag_off(self):
        """custom_anthropic path: system prompts go out verbatim."""
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            response = Mock(spec=httpx2.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx2.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"}
            )
            request = httpx2.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "system": "You are a summarizer.",
                        "messages": [{"role": "user", "content": "summarize"}],
                    }
                ).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        assert sent["system"] == "You are a summarizer."
