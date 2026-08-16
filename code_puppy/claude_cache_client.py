"""OAuth-aware HTTP transport for Claude Code and Anthropic models.

Prompt caching is configured through pydantic-ai's native
``AnthropicModelSettings``. This client deliberately does not rewrite cache
markers; it only owns transport concerns that cannot be expressed there:
OAuth refresh/retry, Claude Code tool-name prefixing, request headers, URL
parameters, and the Opus summarized-thinking compatibility transform.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Callable, MutableMapping
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

# Refresh tokens before the OAuth subscription's one-hour age limit.
TOKEN_MAX_AGE_SECONDS = 3600

# Retry transient provider failures without duplicating SDK behavior.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
MAX_RETRIES = 5

# Claude Code requires this namespace for outgoing tool names.
TOOL_PREFIX = "cp_"

CLAUDE_CLI_USER_AGENT = "claude-cli/2.1.2 (external, cli)"

# Compatibility value for older core-plugin releases; settings own the TTL.
CACHE_TTL_1H = "1h"


def _model_requires_thinking_summary(model_name):
    if not model_name:
        return False
    from code_puppy.model_utils import should_use_anthropic_thinking_summary

    return should_use_anthropic_thinking_summary(model_name)


def _enforce_thinking_display_summary(payload):
    if not isinstance(payload, dict):
        return False
    if not _model_requires_thinking_summary(payload.get("model")):
        return False
    thinking = payload.get("thinking")
    if not isinstance(thinking, dict):
        return False
    if thinking.get("display") == "summarized":
        return False
    thinking["display"] = "summarized"
    return True


def patch_anthropic_client_messages(
    _client: Any, *, cache_ttl: str | None = None
) -> None:
    """Compatibility no-op for core-plugin releases before native caching.

    Current model construction never calls this hook: pydantic-ai 2.31.0
    applies cache settings before SDK serialization. Older separately shipped
    plugins still import it, so keeping an inert boundary avoids breaking
    those handlers while they upgrade. ``cache_ttl`` is intentionally ignored.
    """
    del cache_ttl


class ClaudeCacheAsyncClient(httpx.AsyncClient):
    """Async HTTP client with Claude Code OAuth transformations.

    Handles:
    - Tool name prefixing on outgoing requests
    - Header transformations (anthropic-beta, user-agent)
    - URL modifications (adding ?beta=true)
    - Proactive token refresh and auth-error recovery
    - Retryable transport/status failures
    """

    def __init__(
        self,
        *args: Any,
        oauth_reauthentication_callback: Callable[[], str | None] | None = None,
        token_update_callback: Callable[[str], None] | None = None,
        apply_claude_code_prefix: bool = False,
        cache_ttl: str | None = None,
        **kwargs: Any,
    ) -> None:
        del cache_ttl
        super().__init__(*args, **kwargs)
        self._oauth_reauthentication_callback = oauth_reauthentication_callback
        self._token_update_callback = token_update_callback
        self._apply_claude_code_prefix = apply_claude_code_prefix

    def set_token_update_callback(self, callback: Callable[[str], None] | None) -> None:
        self._token_update_callback = callback

    def _notify_token_recovered(self, access_token: str) -> None:
        if not self._token_update_callback:
            return
        try:
            self._token_update_callback(access_token)
        except Exception as exc:
            logger.debug("Token update callback failed: %s", exc)

    def _get_jwt_age_seconds(self, token: str | None) -> float | None:
        """Decode a JWT and return its age in seconds.
        Returns None if the token can't be decoded or has no timestamp claims.
        Uses 'iat' (issued at) if available, otherwise calculates from 'exp'.
        """
        if not token:
            return None
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
            now = time.time()
            if "iat" in payload:
                iat = float(payload["iat"])
                age = now - iat
                return age
            if "exp" in payload:
                exp = float(payload["exp"])
                time_until_exp = exp - now
                age = TOKEN_MAX_AGE_SECONDS - time_until_exp
                return max(0, age)
            return None
        except Exception as exc:
            logger.debug("Failed to decode JWT age: %s", exc)
            return None

    def _extract_bearer_token(self, request: httpx.Request) -> str | None:
        """Extract the bearer token from request headers."""
        auth_header = request.headers.get("Authorization") or request.headers.get(
            "authorization"
        )
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:]  # Strip "Bearer " prefix
        return None

    def _jwt_refresh_decision(self, request: httpx.Request) -> bool | None:
        """Return a JWT-based refresh decision, or ``None`` for stored fallback."""
        token = self._extract_bearer_token(request)
        if not token:
            return False
        age = self._get_jwt_age_seconds(token)
        if age is None:
            return None
        should_refresh = age >= TOKEN_MAX_AGE_SECONDS
        if should_refresh:
            logger.info(
                "JWT token is %.1f seconds old (>= %d), will refresh proactively",
                age,
                TOKEN_MAX_AGE_SECONDS,
            )
        return should_refresh

    @staticmethod
    def _log_stored_token_refresh(should_refresh: bool) -> bool:
        if should_refresh:
            logger.info(
                "Stored token expires within %d seconds, will refresh proactively",
                TOKEN_MAX_AGE_SECONDS,
            )
        return should_refresh

    def _should_refresh_token(self, request: httpx.Request) -> bool:
        """Synchronously check JWT age, then the stored-token callback."""
        decision = self._jwt_refresh_decision(request)
        if decision is not None:
            return decision
        return self._log_stored_token_refresh(self._check_stored_token_expiry())

    async def _should_refresh_token_async(self, request: httpx.Request) -> bool:
        """Check token expiry while awaiting async providers in ``send()``."""
        decision = self._jwt_refresh_decision(request)
        if decision is not None:
            return decision
        return self._log_stored_token_refresh(
            await self._check_stored_token_expiry_async()
        )

    @staticmethod
    def _check_stored_token_expiry() -> bool:
        """Check if the stored token expires within TOKEN_MAX_AGE_SECONDS.
        This is a fallback for when JWT decoding fails or isn't available.
        Uses the expires_at timestamp from the stored token file.  The
        claude_code_oauth plugin self-registers this capability; when it
        isn't loaded (or the check fails) we conservatively report ``False``.
        """
        try:
            from code_puppy.callbacks import on_check_claude_oauth_token_expiry

            results = on_check_claude_oauth_token_expiry()
            return any(result is True for result in results)
        except Exception as exc:
            logger.debug("Error checking stored token expiry: %s", exc)
            return False

    @staticmethod
    async def _check_stored_token_expiry_async() -> bool:
        """Await stored-token expiry providers from an active event loop."""
        try:
            from code_puppy.callbacks import (
                on_check_claude_oauth_token_expiry_async,
            )

            results = await on_check_claude_oauth_token_expiry_async()
            return any(result is True for result in results)
        except Exception as exc:
            logger.debug("Error checking stored token expiry: %s", exc)
            return False

    @staticmethod
    def _prefix_tool_names(body: bytes) -> bytes | None:
        """Prefix all tool names in the request body with TOOL_PREFIX.
        This is required for Claude Code OAuth compatibility - tools must be
        prefixed on outgoing requests and unprefixed on incoming responses.
        """
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        tools = data.get("tools")
        if not isinstance(tools, list) or not tools:
            return None
        modified = False
        for tool in tools:
            if isinstance(tool, dict) and "name" in tool:
                name = tool["name"]
                if name and not name.startswith(TOOL_PREFIX):
                    tool["name"] = f"{TOOL_PREFIX}{name}"
                    modified = True
        if not modified:
            return None
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def _enforce_thinking_display_summary_body(body: bytes) -> bytes | None:
        """Return a rewritten body when summarized thinking is required."""
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict) or not _enforce_thinking_display_summary(
            payload
        ):
            return None
        return json.dumps(payload).encode("utf-8")

    @staticmethod
    def _transform_headers_for_claude_code(
        headers: MutableMapping[str, str],
    ) -> None:
        """Transform headers for Claude Code OAuth compatibility.
        - Sets user-agent to claude-cli
        - Merges anthropic-beta headers appropriately
        - Removes x-api-key (using Bearer auth instead)
        """
        headers["user-agent"] = CLAUDE_CLI_USER_AGENT
        incoming_beta = headers.get("anthropic-beta", "")
        incoming_betas = [b.strip() for b in incoming_beta.split(",") if b.strip()]
        required_betas = [
            "oauth-2025-04-20",
            "interleaved-thinking-2025-05-14",
        ]
        if "claude-code-20250219" in incoming_betas:
            required_betas.append("claude-code-20250219")
        merged = list(required_betas)
        required_set = set(required_betas)
        for beta in incoming_betas:
            if beta not in required_set:
                merged.append(beta)
        headers["anthropic-beta"] = ",".join(merged)
        for key in ["x-api-key", "X-API-Key", "X-Api-Key"]:
            if key in headers:
                del headers[key]

    @staticmethod
    def _add_beta_query_param(url: httpx.URL) -> httpx.URL:
        """Add ?beta=true query parameter to the URL if not already present."""
        parsed = urlparse(str(url))
        query_params = parse_qs(parsed.query)
        if "beta" not in query_params:
            query_params["beta"] = ["true"]
            new_query = urlencode(query_params, doseq=True)
            new_parsed = parsed._replace(query=new_query)
            return httpx.URL(urlunparse(new_parsed))
        return url

    async def send(
        self, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:  # type: ignore[override]
        is_messages_endpoint = request.url.path.endswith("/v1/messages")
        if not request.extensions.get("claude_oauth_proactive_refresh_attempted"):
            try:
                if await self._should_refresh_token_async(request):
                    refreshed_token = await self._refresh_claude_oauth_token_async()
                    if refreshed_token:
                        logger.info("Proactively refreshed token before request")
                        headers = dict(request.headers)
                        self._update_auth_headers(headers, refreshed_token)
                        body_bytes = self._extract_body_bytes(request)
                        request = self.build_request(
                            method=request.method,
                            url=request.url,
                            headers=headers,
                            content=body_bytes,
                        )
                        request.extensions[
                            "claude_oauth_proactive_refresh_attempted"
                        ] = True
            except Exception as exc:
                logger.debug("Error during proactive token refresh check: %s", exc)
        if is_messages_endpoint:
            try:
                body_bytes = self._extract_body_bytes(request)
                headers = dict(request.headers)
                url = request.url
                body_modified = False
                headers_modified = False
                self._transform_headers_for_claude_code(headers)
                headers_modified = True
                url = self._add_beta_query_param(url)
                if body_bytes and self._apply_claude_code_prefix:
                    prefixed_body = self._prefix_tool_names(body_bytes)
                    if prefixed_body is not None:
                        body_bytes = prefixed_body
                        body_modified = True
                if body_bytes:
                    summarized_body = self._enforce_thinking_display_summary_body(
                        body_bytes
                    )
                    if summarized_body is not None:
                        body_bytes = summarized_body
                        body_modified = True
                if body_modified or headers_modified or url != request.url:
                    try:
                        rebuilt = self.build_request(
                            method=request.method,
                            url=url,
                            headers=headers,
                            content=body_bytes,
                        )
                        if hasattr(rebuilt, "_content"):
                            request._content = rebuilt._content  # type: ignore[attr-defined]
                        if hasattr(rebuilt, "stream"):
                            request.stream = rebuilt.stream
                        if hasattr(rebuilt, "extensions"):
                            request.extensions = {
                                **rebuilt.extensions,
                                **request.extensions,
                            }
                        request.url = url
                        for key, value in headers.items():
                            request.headers[key] = value
                        if body_bytes:
                            request.headers["Content-Length"] = str(len(body_bytes))
                    except Exception as exc:
                        logger.debug("Error rebuilding request: %s", exc)
            except Exception as exc:
                logger.debug("Error in Claude Code transformations: %s", exc)
        response = await self._send_with_retries(request, *args, **kwargs)
        try:
            if response.status_code in (400, 401, 403) and not request.extensions.get(
                "claude_oauth_refresh_attempted"
            ):
                is_auth_error = response.status_code in (401, 403)
                if response.status_code == 400:
                    is_auth_error = await self._is_cloudflare_html_error(response)
                    if is_auth_error:
                        logger.info(
                            "Detected Cloudflare 400 error (likely auth-related), attempting token refresh"
                        )
                if is_auth_error:
                    recovered_token = (
                        self._recover_claude_oauth_token_after_auth_error()
                    )
                    if recovered_token:
                        logger.info("Token recovered successfully, retrying request")
                        await response.aclose()
                        body_bytes = self._extract_body_bytes(request)
                        headers = dict(request.headers)
                        self._update_auth_headers(headers, recovered_token)
                        retry_request = self.build_request(
                            method=request.method,
                            url=request.url,
                            headers=headers,
                            content=body_bytes,
                        )
                        retry_request.extensions["claude_oauth_refresh_attempted"] = (
                            True
                        )
                        return await self._send_with_retries(
                            retry_request, *args, **kwargs
                        )
                    else:
                        logger.warning(
                            "Token recovery failed, returning original error"
                        )
        except Exception as exc:
            logger.debug("Error during token refresh attempt: %s", exc)
        return response

    async def _send_with_retries(
        self, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        """Retry rate limits, server failures, and transient connections."""
        last_response: httpx.Response | None = None
        last_exception: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            status_code: int | None = None
            try:
                response = await super().send(request, *args, **kwargs)
                last_response = response
                if (
                    response.status_code not in RETRY_STATUS_CODES
                    or attempt >= MAX_RETRIES
                ):
                    return response
                status_code = response.status_code
                await response.aclose()
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                last_exception = exc
                if attempt >= MAX_RETRIES:
                    raise
            except Exception:
                raise
            wait_time = float(2**attempt)
            if status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_time = float(retry_after)
                    except ValueError:
                        try:
                            from email.utils import parsedate_to_datetime

                            wait_time = max(
                                0,
                                parsedate_to_datetime(retry_after).timestamp()
                                - time.time(),
                            )
                        except Exception:
                            pass
            wait_time = max(0.5, min(wait_time, 60.0))
            if status_code is None:
                logger.warning(
                    "HTTP connection error: %s. Retrying in %.1fs (attempt %d/%d)",
                    last_exception,
                    wait_time,
                    attempt + 1,
                    MAX_RETRIES,
                )
            else:
                logger.info(
                    "HTTP %d received, retrying in %.1fs (attempt %d/%d)",
                    status_code,
                    wait_time,
                    attempt + 1,
                    MAX_RETRIES,
                )
            await asyncio.sleep(wait_time)
        if last_response is not None:
            return last_response
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Retry loop completed without response or exception")

    @staticmethod
    def _extract_body_bytes(request: httpx.Request) -> bytes | None:
        try:
            content = request.content
            if content:
                return content
        except Exception:
            pass
        try:
            content = getattr(request, "_content", None)
            if content:
                return content
        except Exception:
            pass
        return None

    @staticmethod
    def _update_auth_headers(
        headers: MutableMapping[str, str], access_token: str
    ) -> None:
        bearer_value = f"Bearer {access_token}"
        if "Authorization" in headers:
            headers["Authorization"] = bearer_value
        elif "authorization" in headers:
            headers["authorization"] = bearer_value
        elif "x-api-key" in headers:
            headers["x-api-key"] = access_token
        elif "X-API-Key" in headers:
            headers["X-API-Key"] = access_token
        else:
            headers["Authorization"] = bearer_value

    @staticmethod
    async def _is_cloudflare_html_error(response: httpx.Response) -> bool:
        """Return whether a 400 HTML response is a Cloudflare auth failure."""
        if "text/html" not in response.headers.get("content-type", "").lower():
            return False
        try:
            if not getattr(response, "_content", None):
                await response.aread()
            raw_content = getattr(response, "_content", None)
            body = (
                raw_content.decode("utf-8", errors="ignore")
                if raw_content
                else response.text
            )
            body_lower = body.lower()
            return "cloudflare" in body_lower and "400 bad request" in body_lower
        except Exception as exc:
            logger.debug("Error checking for Cloudflare error: %s", exc)
            return False

    def _recover_claude_oauth_token_after_auth_error(self) -> str | None:
        """Recover an OAuth token after the API rejected the current one.
        First tries a refresh-token exchange. If that fails, an optional
        provider-specific callback may run a full interactive OAuth flow.
        """
        refreshed_token = self._refresh_claude_oauth_token()
        if refreshed_token:
            return refreshed_token
        if not self._oauth_reauthentication_callback:
            return None
        try:
            reauthenticated_token = self._oauth_reauthentication_callback()
        except Exception as exc:
            logger.error("Exception during OAuth reauthentication: %s", exc)
            return None
        if not reauthenticated_token:
            logger.warning("OAuth reauthentication returned no token")
            return None
        self._update_auth_headers(self.headers, reauthenticated_token)
        self._notify_token_recovered(reauthenticated_token)
        return reauthenticated_token

    def _apply_token_refresh_results(self, results: list[Any]) -> str | None:
        if not results:
            return None
        logger.info("Attempting to refresh Claude Code OAuth token...")
        refreshed_token = next(
            (result for result in results if isinstance(result, str) and result),
            None,
        )
        if refreshed_token:
            self._update_auth_headers(self.headers, refreshed_token)
            self._notify_token_recovered(refreshed_token)
            logger.info("Successfully refreshed Claude Code OAuth token")
        else:
            logger.warning("Token refresh returned None")
        return refreshed_token

    def _refresh_claude_oauth_token(self) -> str | None:
        try:
            from code_puppy.callbacks import on_refresh_claude_oauth_token

            return self._apply_token_refresh_results(on_refresh_claude_oauth_token())
        except Exception as exc:
            logger.error("Exception during token refresh: %s", exc)
            return None

    async def _refresh_claude_oauth_token_async(self) -> str | None:
        """Await token-refresh providers from an active event loop."""
        try:
            from code_puppy.callbacks import on_refresh_claude_oauth_token_async

            results = await on_refresh_claude_oauth_token_async()
            return self._apply_token_refresh_results(results)
        except Exception as exc:
            logger.error("Exception during token refresh: %s", exc)
            return None
