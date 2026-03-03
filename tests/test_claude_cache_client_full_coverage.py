"""Full coverage tests for code_puppy/claude_cache_client.py."""

import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest

from code_puppy.claude_cache_client import (
    CLAUDE_CLI_USER_AGENT,
    TOKEN_MAX_AGE_SECONDS,
    TOOL_PREFIX,
    ClaudeCacheAsyncClient,
    _inject_cache_control_in_payload,
    patch_anthropic_client_messages,
)


def _create_jwt(iat=None, exp=None):
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
    return f"{header_b64}.{payload_b64}.fake_signature"


# --- JWT age ---


class TestJWTAge:
    def test_none_token(self):
        c = ClaudeCacheAsyncClient()
        assert c._get_jwt_age_seconds(None) is None

    def test_empty_token(self):
        c = ClaudeCacheAsyncClient()
        assert c._get_jwt_age_seconds("") is None

    def test_invalid_parts(self):
        c = ClaudeCacheAsyncClient()
        assert c._get_jwt_age_seconds("only.two") is None
        assert c._get_jwt_age_seconds("a.b.c.d") is None

    def test_bad_base64(self):
        c = ClaudeCacheAsyncClient()
        # Valid 3-part but bad base64
        assert c._get_jwt_age_seconds("a.!!!.c") is None

    def test_with_iat(self):
        token = _create_jwt(iat=time.time() - 600)
        c = ClaudeCacheAsyncClient()
        age = c._get_jwt_age_seconds(token)
        assert 590 <= age <= 610

    def test_with_exp_only(self):
        token = _create_jwt(exp=time.time() + 1800)
        c = ClaudeCacheAsyncClient()
        age = c._get_jwt_age_seconds(token)
        assert 1790 <= age <= 1810

    def test_exp_negative_age(self):
        # exp far in future -> age would be negative, clamped to 0
        token = _create_jwt(exp=time.time() + TOKEN_MAX_AGE_SECONDS + 1000)
        c = ClaudeCacheAsyncClient()
        age = c._get_jwt_age_seconds(token)
        assert age == 0

    def test_no_claims(self):
        token = _create_jwt()
        c = ClaudeCacheAsyncClient()
        assert c._get_jwt_age_seconds(token) is None


# --- Bearer token extraction ---


class TestExtractBearer:
    def test_with_auth(self):
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"Authorization": "Bearer tok123"}
        )
        assert c._extract_bearer_token(req) == "tok123"

    def test_lowercase(self):
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"authorization": "bearer tok"}
        )
        # httpx normalizes headers
        token = c._extract_bearer_token(req)
        assert token is not None

    def test_missing(self):
        c = ClaudeCacheAsyncClient()
        req = httpx.Request("POST", "https://x.com")
        assert c._extract_bearer_token(req) is None

    def test_non_bearer(self):
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"Authorization": "Basic abc"}
        )
        assert c._extract_bearer_token(req) is None


# --- Should refresh ---


class TestShouldRefresh:
    def test_no_token(self):
        c = ClaudeCacheAsyncClient()
        req = httpx.Request("POST", "https://x.com")
        assert c._should_refresh_token(req) is False

    def test_old_token(self):
        token = _create_jwt(iat=time.time() - 7200)
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"Authorization": f"Bearer {token}"}
        )
        assert c._should_refresh_token(req) is True

    def test_fresh_token(self):
        token = _create_jwt(iat=time.time() - 100)
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"Authorization": f"Bearer {token}"}
        )
        assert c._should_refresh_token(req) is False

    def test_falls_back_to_stored_expiry(self):
        """When JWT can't be decoded, falls back to stored token."""
        token = _create_jwt()  # no iat/exp
        c = ClaudeCacheAsyncClient()
        req = httpx.Request(
            "POST", "https://x.com", headers={"Authorization": f"Bearer {token}"}
        )
        with patch.object(
            ClaudeCacheAsyncClient, "_check_stored_token_expiry", return_value=True
        ):
            assert c._should_refresh_token(req) is True


# --- Check stored token expiry ---


class TestCheckStoredExpiry:
    def test_with_tokens_expired(self):
        mock_module = MagicMock()
        mock_module.load_stored_tokens = MagicMock(return_value={"access_token": "x"})
        mock_module.is_token_expired = MagicMock(return_value=True)
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            assert ClaudeCacheAsyncClient._check_stored_token_expiry() is True

    def test_with_no_tokens(self):
        mock_module = MagicMock()
        mock_module.load_stored_tokens = MagicMock(return_value=None)
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            assert ClaudeCacheAsyncClient._check_stored_token_expiry() is False

    def test_exception(self):
        mock_module = MagicMock()
        mock_module.load_stored_tokens = MagicMock(side_effect=Exception("fail"))
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            assert ClaudeCacheAsyncClient._check_stored_token_expiry() is False


# --- Prefix tool names ---


class TestPrefixToolNames:
    def test_basic(self):
        body = json.dumps({"tools": [{"name": "read_file"}]}).encode()
        result = ClaudeCacheAsyncClient._prefix_tool_names(body)
        assert result is not None
        data = json.loads(result)
        assert data["tools"][0]["name"] == f"{TOOL_PREFIX}read_file"

    def test_already_prefixed(self):
        body = json.dumps({"tools": [{"name": f"{TOOL_PREFIX}read_file"}]}).encode()
        assert ClaudeCacheAsyncClient._prefix_tool_names(body) is None

    def test_no_tools(self):
        body = json.dumps({"messages": []}).encode()
        assert ClaudeCacheAsyncClient._prefix_tool_names(body) is None

    def test_empty_tools(self):
        body = json.dumps({"tools": []}).encode()
        assert ClaudeCacheAsyncClient._prefix_tool_names(body) is None

    def test_invalid_json(self):
        assert ClaudeCacheAsyncClient._prefix_tool_names(b"not json") is None

    def test_non_dict(self):
        assert ClaudeCacheAsyncClient._prefix_tool_names(b'"string"') is None

    def test_tool_without_name(self):
        body = json.dumps({"tools": [{"description": "no name"}]}).encode()
        assert ClaudeCacheAsyncClient._prefix_tool_names(body) is None

    def test_tool_empty_name(self):
        body = json.dumps({"tools": [{"name": ""}]}).encode()
        assert ClaudeCacheAsyncClient._prefix_tool_names(body) is None


# --- Header transformation ---


class TestHeaderTransform:
    def test_sets_user_agent(self):
        h = {}
        ClaudeCacheAsyncClient._transform_headers_for_claude_code(h)
        assert h["user-agent"] == CLAUDE_CLI_USER_AGENT

    def test_removes_x_api_key_variants(self):
        h = {"x-api-key": "s", "X-API-Key": "s", "X-Api-Key": "s"}
        ClaudeCacheAsyncClient._transform_headers_for_claude_code(h)
        assert "x-api-key" not in h
        assert "X-API-Key" not in h
        assert "X-Api-Key" not in h

    def test_claude_code_beta_kept(self):
        h = {"anthropic-beta": "claude-code-20250219"}
        ClaudeCacheAsyncClient._transform_headers_for_claude_code(h)
        assert "claude-code-20250219" in h["anthropic-beta"]


# --- URL beta param ---


class TestAddBetaParam:
    def test_adds(self):
        url = httpx.URL("https://api.com/v1/messages")
        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)
        assert "beta=true" in str(new_url)

    def test_no_duplicate(self):
        url = httpx.URL("https://api.com/v1/messages?beta=true")
        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)
        assert str(new_url).count("beta") == 1


# --- Inject cache control ---


class TestInjectCacheControl:
    def test_basic(self):
        body = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "hi"}]}
                ]
            }
        ).encode()
        result = ClaudeCacheAsyncClient._inject_cache_control(body)
        assert result is not None
        data = json.loads(result)
        assert data["messages"][0]["content"][0]["cache_control"] == {
            "type": "ephemeral"
        }

    def test_already_has_cache_control(self):
        body = json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "cache_control": {"type": "ephemeral"}}
                        ],
                    }
                ]
            }
        ).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_no_messages(self):
        body = json.dumps({"model": "claude"}).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_empty_messages(self):
        body = json.dumps({"messages": []}).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_invalid_json(self):
        assert ClaudeCacheAsyncClient._inject_cache_control(b"not json") is None

    def test_non_dict(self):
        assert ClaudeCacheAsyncClient._inject_cache_control(b'"string"') is None

    def test_content_not_list(self):
        body = json.dumps(
            {"messages": [{"role": "user", "content": "just text"}]}
        ).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_empty_content_list(self):
        body = json.dumps({"messages": [{"role": "user", "content": []}]}).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_last_block_not_dict(self):
        body = json.dumps(
            {"messages": [{"role": "user", "content": ["just a string"]}]}
        ).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None

    def test_last_message_not_dict(self):
        body = json.dumps({"messages": ["not a dict"]}).encode()
        assert ClaudeCacheAsyncClient._inject_cache_control(body) is None


# --- _inject_cache_control_in_payload ---


class TestInjectCacheControlInPayload:
    def test_basic(self):
        payload = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        }
        _inject_cache_control_in_payload(payload)
        assert payload["messages"][0]["content"][0]["cache_control"] == {
            "type": "ephemeral"
        }

    def test_already_present(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "cache_control": {"type": "x"}}],
                }
            ]
        }
        _inject_cache_control_in_payload(payload)
        assert payload["messages"][0]["content"][0]["cache_control"] == {"type": "x"}

    def test_no_messages(self):
        payload = {}
        _inject_cache_control_in_payload(payload)  # should not raise

    def test_empty_messages(self):
        payload = {"messages": []}
        _inject_cache_control_in_payload(payload)

    def test_content_not_list(self):
        payload = {"messages": [{"role": "user", "content": "text"}]}
        _inject_cache_control_in_payload(payload)

    def test_empty_content(self):
        payload = {"messages": [{"role": "user", "content": []}]}
        _inject_cache_control_in_payload(payload)

    def test_last_block_not_dict(self):
        payload = {"messages": [{"role": "user", "content": ["str"]}]}
        _inject_cache_control_in_payload(payload)

    def test_last_message_not_dict(self):
        payload = {"messages": ["not a dict"]}
        _inject_cache_control_in_payload(payload)


# --- patch_anthropic_client_messages ---


class TestPatchAnthropic:
    def test_none_client(self):
        patch_anthropic_client_messages(None)  # should not raise

    def test_non_anthropic_client(self):
        patch_anthropic_client_messages("not a client")  # should not raise

    @pytest.mark.asyncio
    async def test_patches_create(self):
        """Test monkey-patching when AsyncAnthropic is available."""
        # We need to simulate AsyncAnthropic being available
        mock_messages = MagicMock()
        original_create = AsyncMock(return_value="result")
        mock_messages.create = original_create

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        # Patch AsyncAnthropic to make isinstance check pass
        with patch("code_puppy.claude_cache_client.AsyncAnthropic", type(mock_client)):
            patch_anthropic_client_messages(mock_client)

        # Now create should be wrapped
        assert mock_messages.create is not original_create

        # Call the wrapped version with kwargs
        result = await mock_messages.create(
            model="claude-3",
            messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        )
        assert result == "result"

    @pytest.mark.asyncio
    async def test_patches_create_with_args(self):
        mock_messages = MagicMock()
        original_create = AsyncMock(return_value="ok")
        mock_messages.create = original_create

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        with patch("code_puppy.claude_cache_client.AsyncAnthropic", type(mock_client)):
            patch_anthropic_client_messages(mock_client)

        # Call with positional dict arg
        payload = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
        }
        result = await mock_messages.create(payload)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_patches_create_with_non_dict_args(self):
        mock_messages = MagicMock()
        original_create = AsyncMock(return_value="ok")
        mock_messages.create = original_create

        mock_client = MagicMock()
        mock_client.messages = mock_messages

        with patch("code_puppy.claude_cache_client.AsyncAnthropic", type(mock_client)):
            patch_anthropic_client_messages(mock_client)

        # Call with non-dict positional arg
        result = await mock_messages.create("not a dict")
        assert result == "ok"

    def test_no_messages_attr(self):
        mock_client = MagicMock(spec=[])
        with patch("code_puppy.claude_cache_client.AsyncAnthropic", type(mock_client)):
            patch_anthropic_client_messages(mock_client)  # should not raise


# --- Extract body bytes ---


class TestExtractBodyBytes:
    def test_from_content(self):
        req = httpx.Request("POST", "https://x.com", content=b"hello")
        assert ClaudeCacheAsyncClient._extract_body_bytes(req) == b"hello"

    def test_no_content(self):
        req = httpx.Request("GET", "https://x.com")
        result = ClaudeCacheAsyncClient._extract_body_bytes(req)
        # GET has empty content
        assert result is None or result == b""

    def test_content_property_raises(self):
        """Test fallback to _content when .content raises."""
        req = MagicMock()
        type(req).content = property(lambda s: (_ for _ in ()).throw(Exception("no")))
        req._content = b"fallback"
        assert ClaudeCacheAsyncClient._extract_body_bytes(req) == b"fallback"

    def test_both_raise(self):
        req = MagicMock()
        type(req).content = property(lambda s: (_ for _ in ()).throw(Exception("no")))
        del req._content  # Make getattr return None
        result = ClaudeCacheAsyncClient._extract_body_bytes(req)
        assert result is None

    def test_content_empty_fallback_to_private(self):
        """When .content returns empty bytes, try _content."""
        req = MagicMock()
        req.content = b""  # empty/falsy
        req._content = b"private content"
        result = ClaudeCacheAsyncClient._extract_body_bytes(req)
        assert result == b"private content"

    def test_getattr_raises(self):
        """When both .content raises and getattr(_content) raises."""
        req = MagicMock()
        type(req).content = property(lambda s: (_ for _ in ()).throw(Exception("no")))
        type(req)._content = property(lambda s: (_ for _ in ()).throw(Exception("no2")))
        result = ClaudeCacheAsyncClient._extract_body_bytes(req)
        assert result is None


# --- Update auth headers ---


class TestUpdateAuthHeaders:
    def test_with_authorization(self):
        h = {"Authorization": "Bearer old"}
        ClaudeCacheAsyncClient._update_auth_headers(h, "new_tok")
        assert h["Authorization"] == "Bearer new_tok"

    def test_with_x_api_key(self):
        h = {"x-api-key": "old"}
        ClaudeCacheAsyncClient._update_auth_headers(h, "new_tok")
        assert h["x-api-key"] == "new_tok"

    def test_neither(self):
        h = {}
        ClaudeCacheAsyncClient._update_auth_headers(h, "new_tok")
        assert h["Authorization"] == "Bearer new_tok"


# --- Cloudflare detection ---


class TestCloudflareDetection:
    @pytest.mark.asyncio
    async def test_true(self):
        resp = Mock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html"}
        resp._content = b"<html>cloudflare 400 bad request</html>"
        c = ClaudeCacheAsyncClient()
        assert await c._is_cloudflare_html_error(resp) is True

    @pytest.mark.asyncio
    async def test_json_content_type(self):
        resp = Mock(spec=httpx.Response)
        resp.headers = {"content-type": "application/json"}
        c = ClaudeCacheAsyncClient()
        assert await c._is_cloudflare_html_error(resp) is False

    @pytest.mark.asyncio
    async def test_no_content_fallback_to_text(self):
        resp = Mock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html"}
        resp._content = None
        resp.text = "cloudflare 400 bad request"
        resp.aread = AsyncMock(return_value=resp.text.encode("utf-8"))
        c = ClaudeCacheAsyncClient()
        assert await c._is_cloudflare_html_error(resp) is True

    @pytest.mark.asyncio
    async def test_outer_exception_path(self):
        """Test the outer except Exception in _is_cloudflare_html_error."""
        resp = Mock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html"}
        # _content that decodes to something whose .lower() raises
        resp._content = MagicMock()
        resp._content.__bool__ = lambda s: True
        resp._content.decode = MagicMock(side_effect=Exception("decode boom"))
        c = ClaudeCacheAsyncClient()
        assert await c._is_cloudflare_html_error(resp) is False

    @pytest.mark.asyncio
    async def test_no_content_text_raises(self):
        resp = Mock(spec=httpx.Response)
        resp.headers = {"content-type": "text/html"}
        resp._content = None
        resp.aread = AsyncMock(return_value=b"")
        type(resp).text = property(
            lambda s: (_ for _ in ()).throw(Exception("consumed"))
        )
        c = ClaudeCacheAsyncClient()
        assert await c._is_cloudflare_html_error(resp) is False


# --- Refresh token ---


class TestRefreshToken:
    def test_success(self):
        c = ClaudeCacheAsyncClient(headers={"Authorization": "Bearer old"})
        mock_module = MagicMock()
        mock_module.refresh_access_token = MagicMock(return_value="new_token")
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            result = c._refresh_claude_oauth_token()
            assert result == "new_token"

    def test_returns_none(self):
        c = ClaudeCacheAsyncClient()
        mock_module = MagicMock()
        mock_module.refresh_access_token = MagicMock(return_value=None)
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            result = c._refresh_claude_oauth_token()
            assert result is None

    def test_exception(self):
        c = ClaudeCacheAsyncClient()
        mock_module = MagicMock()
        mock_module.refresh_access_token = MagicMock(side_effect=Exception("fail"))
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.plugins.claude_code_oauth": MagicMock(),
                "code_puppy.plugins.claude_code_oauth.utils": mock_module,
            },
        ):
            result = c._refresh_claude_oauth_token()
            assert result is None


# --- Send with retries ---


class TestSendWithRetries:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            req = httpx.Request("POST", "https://x.com")
            result = await c._send_with_retries(req)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        resp_429 = Mock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.1"}
        resp_429.aclose = AsyncMock()

        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[resp_429, resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_on_429_http_date(self):
        resp_429 = Mock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "Mon, 01 Jan 2024 00:00:00 GMT"}
        resp_429.aclose = AsyncMock()

        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[resp_429, resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_on_429_invalid_retry_after(self):
        resp_429 = Mock(spec=httpx.Response)
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "not-a-number-or-date!!!"}
        resp_429.aclose = AsyncMock()

        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[resp_429, resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        resp_500 = Mock(spec=httpx.Response)
        resp_500.status_code = 500
        resp_500.headers = {}
        resp_500.aclose = AsyncMock()

        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[resp_500, resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        resp_500 = Mock(spec=httpx.Response)
        resp_500.status_code = 500
        resp_500.headers = {}
        resp_500.aclose = AsyncMock()

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp_500
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 500

    @pytest.mark.asyncio
    async def test_retry_on_connect_error(self):
        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[httpx.ConnectError("fail"), resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_connect_error_max_retries(self):
        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                with pytest.raises(httpx.ConnectError):
                    await c._send_with_retries(req)

    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=ValueError("bad"),
        ):
            c = ClaudeCacheAsyncClient()
            req = httpx.Request("POST", "https://x.com")
            with pytest.raises(ValueError):
                await c._send_with_retries(req)

    @pytest.mark.asyncio
    async def test_retry_on_read_timeout(self):
        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[httpx.ReadTimeout("timeout"), resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_retry_on_pool_timeout(self):
        resp_200 = Mock(spec=httpx.Response)
        resp_200.status_code = 200

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[httpx.PoolTimeout("pool"), resp_200],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://x.com")
                result = await c._send_with_retries(req)
                assert result.status_code == 200


# --- Full send flow ---


class TestSendFlow:
    @pytest.mark.asyncio
    async def test_non_messages_endpoint(self):
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            req = httpx.Request("GET", "https://api.com/v1/models")
            result = await c.send(req)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_messages_endpoint_transforms(self):
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            body = json.dumps(
                {
                    "model": "claude-3",
                    "tools": [{"name": "fn"}],
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "hi"}],
                        }
                    ],
                }
            ).encode()
            req = httpx.Request("POST", "https://api.com/v1/messages", content=body)
            result = await c.send(req)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_error_refresh(self):
        failed = Mock(spec=httpx.Response)
        failed.status_code = 401
        failed.headers = {"content-type": "application/json"}
        failed.aclose = AsyncMock()

        success = Mock(spec=httpx.Response)
        success.status_code = 200
        success.headers = {}

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[failed, success],
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new",
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request(
                    "POST",
                    "https://api.com/v1/messages",
                    headers={"Authorization": "Bearer old"},
                    content=b'{"model": "x"}',
                )
                result = await c.send(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_error_refresh_fails(self):
        failed = Mock(spec=httpx.Response)
        failed.status_code = 403
        failed.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=failed
        ):
            with patch.object(
                ClaudeCacheAsyncClient, "_refresh_claude_oauth_token", return_value=None
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request(
                    "POST", "https://api.com/v1/messages", content=b"{}"
                )
                result = await c.send(req)
                assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_already_attempted_refresh(self):
        """When refresh was already attempted, don't refresh again on auth error."""
        failed = Mock(spec=httpx.Response)
        failed.status_code = 401
        failed.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=failed
        ):
            with patch.object(ClaudeCacheAsyncClient, "_refresh_claude_oauth_token"):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://api.com/v1/messages")
                req.extensions["claude_oauth_refresh_attempted"] = True
                result = await c.send(req)
                # Proactive refresh is skipped because extension flag is set
                # Auth error refresh is also skipped because flag is set
                assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_proactive_refresh_exception_handled(self):
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_should_refresh_token",
                side_effect=Exception("boom"),
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("GET", "https://api.com/other")
                result = await c.send(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_transformation_exception_handled(self):
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_transform_headers_for_claude_code",
                side_effect=Exception("boom"),
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request(
                    "POST", "https://api.com/v1/messages", content=b"{}"
                )
                result = await c.send(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_error_handling_exception(self):
        failed = Mock(spec=httpx.Response)
        failed.status_code = 401
        failed.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=failed
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                side_effect=Exception("boom"),
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request("POST", "https://api.com/v1/messages")
                result = await c.send(req)
                assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_cloudflare_400_triggers_refresh(self):
        failed = Mock(spec=httpx.Response)
        failed.status_code = 400
        failed.headers = {"content-type": "text/html"}
        failed._content = b"cloudflare 400 bad request"
        failed.aclose = AsyncMock()

        success = Mock(spec=httpx.Response)
        success.status_code = 200
        success.headers = {}

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[failed, success],
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new",
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request(
                    "POST",
                    "https://api.com/v1/messages",
                    headers={"Authorization": "Bearer old"},
                    content=b"{}",
                )
                result = await c.send(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_proactive_refresh_success(self):
        token = _create_jwt(iat=time.time() - 7200)  # old token
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new_tok",
            ):
                c = ClaudeCacheAsyncClient()
                req = httpx.Request(
                    "POST",
                    "https://api.com/other",
                    headers={"Authorization": f"Bearer {token}"},
                )
                result = await c.send(req)
                assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_messages_endpoint_full_transformations(self):
        """Test that all transformations are applied to /v1/messages."""
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            body = json.dumps(
                {
                    "model": "claude-3",
                    "tools": [{"name": "fn"}],
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": "hi"}],
                        }
                    ],
                }
            ).encode()
            req = httpx.Request(
                "POST",
                "https://api.com/v1/messages",
                content=body,
                headers={
                    "anthropic-beta": "interleaved-thinking-2025-05-14",
                    "x-api-key": "secret",
                },
            )
            result = await c.send(req)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_messages_no_body(self):
        """Test /v1/messages with no body."""
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            req = httpx.Request("POST", "https://api.com/v1/messages")
            result = await c.send(req)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_rebuild_request_exception(self):
        """Test that rebuild_request exceptions are handled gracefully."""
        resp = Mock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {}

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=resp
        ):
            c = ClaudeCacheAsyncClient()
            # Create a request to /v1/messages to trigger transformations
            req = httpx.Request(
                "POST", "https://api.com/v1/messages", content=b'{"model": "x"}'
            )
            with patch.object(
                c, "build_request", side_effect=Exception("rebuild fail")
            ):
                result = await c.send(req)
                # Should still succeed despite rebuild failure
                assert result.status_code == 200
