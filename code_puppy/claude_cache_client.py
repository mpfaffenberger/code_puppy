"""Cache helpers for Claude Code / Anthropic.

ClaudeCacheAsyncClient: httpx client that tries to patch /v1/messages bodies.

We now also expose `patch_anthropic_client_messages` which monkey-patches
AsyncAnthropic.messages.create() so we can inject cache_control BEFORE
serialization, avoiding httpx/Pydantic internals.

This module also handles:
- Tool name prefixing/unprefixing for Claude Code OAuth compatibility
- Header transformations (anthropic-beta, user-agent)
- URL modifications (adding ?beta=true query param)
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any, Callable, MutableMapping
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

# Refresh token if it's older than 1 hour (3600 seconds)
TOKEN_MAX_AGE_SECONDS = 3600

# Tool name prefix for Claude Code OAuth compatibility
# Tools are prefixed on outgoing requests and unprefixed on incoming responses
TOOL_PREFIX = "cp_"

# User-Agent to send with Claude Code OAuth requests
CLAUDE_CLI_USER_AGENT = "claude-cli/2.1.2 (external, cli)"

try:
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - optional dep
    AsyncAnthropic = None  # type: ignore


class ClaudeCacheAsyncClient(httpx.AsyncClient):
    """Async HTTP client with Claude Code OAuth transformations.

    Handles:
    - Cache control injection for prompt caching
    - Tool name prefixing on outgoing requests
    - Tool name unprefixing on incoming streaming responses
    - Header transformations (anthropic-beta, user-agent)
    - URL modifications (adding ?beta=true)
    - Proactive token refresh
    """

    # Regex pattern for unprefixing tool names in streaming responses
    _TOOL_UNPREFIX_PATTERN = re.compile(
        rf'"name"\s*:\s*"{re.escape(TOOL_PREFIX)}([^"]+)"'
    )

    def _get_jwt_age_seconds(self, token: str | None) -> float | None:
        """Decode a JWT and return its age in seconds.

        Returns None if the token can't be decoded or has no timestamp claims.
        Uses 'iat' (issued at) if available, otherwise calculates from 'exp'.
        """
        if not token:
            return None

        try:
            # JWT format: header.payload.signature
            # We only need the payload (second part)
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode the payload (base64url encoded)
            payload_b64 = parts[1]
            # Add padding if needed (base64url doesn't require padding)
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))

            now = time.time()

            # Prefer 'iat' (issued at) claim if available
            if "iat" in payload:
                iat = float(payload["iat"])
                age = now - iat
                return age

            # Fall back to calculating from 'exp' claim
            # Assume tokens are typically valid for 1 hour
            if "exp" in payload:
                exp = float(payload["exp"])
                # If exp is in the future, calculate how long until expiry
                # and assume the token was issued 1 hour before expiry
                time_until_exp = exp - now
                # If token has less than 1 hour left, it's "old"
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

    def _should_refresh_token(self, request: httpx.Request) -> bool:
        """Check if the token in the request is older than 1 hour."""
        token = self._extract_bearer_token(request)
        if not token:
            return False

        age = self._get_jwt_age_seconds(token)
        if age is None:
            return False

        should_refresh = age >= TOKEN_MAX_AGE_SECONDS
        if should_refresh:
            logger.info(
                "JWT token is %.1f seconds old (>= %d), will refresh proactively",
                age,
                TOKEN_MAX_AGE_SECONDS,
            )
        return should_refresh

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

    def _unprefix_tool_names_in_text(self, text: str) -> str:
        """Remove TOOL_PREFIX from tool names in streaming response text."""
        return self._TOOL_UNPREFIX_PATTERN.sub(r'"name": "\1"', text)

    @staticmethod
    def _transform_headers_for_claude_code(
        headers: MutableMapping[str, str],
    ) -> None:
        """Transform headers for Claude Code OAuth compatibility.

        - Sets user-agent to claude-cli
        - Merges anthropic-beta headers appropriately
        - Removes x-api-key (using Bearer auth instead)
        """
        # Set user-agent
        headers["user-agent"] = CLAUDE_CLI_USER_AGENT

        # Handle anthropic-beta header
        incoming_beta = headers.get("anthropic-beta", "")
        incoming_betas = [b.strip() for b in incoming_beta.split(",") if b.strip()]

        # Check if claude-code beta was explicitly requested
        include_claude_code = "claude-code-20250219" in incoming_betas

        # Build merged betas list
        merged_betas = [
            "oauth-2025-04-20",
            "interleaved-thinking-2025-05-14",
        ]
        if include_claude_code:
            merged_betas.append("claude-code-20250219")

        headers["anthropic-beta"] = ",".join(merged_betas)

        # Remove x-api-key if present (we use Bearer auth)
        for key in ["x-api-key", "X-API-Key", "X-Api-Key"]:
            if key in headers:
                del headers[key]

    @staticmethod
    def _add_beta_query_param(url: httpx.URL) -> httpx.URL:
        """Add ?beta=true query parameter to the URL if not already present."""
        # Parse the URL
        parsed = urlparse(str(url))
        query_params = parse_qs(parsed.query)

        # Only add if not already present
        if "beta" not in query_params:
            query_params["beta"] = ["true"]
            # Rebuild query string
            new_query = urlencode(query_params, doseq=True)
            # Rebuild URL
            new_parsed = parsed._replace(query=new_query)
            return httpx.URL(urlunparse(new_parsed))

        return url

    async def send(
        self, request: httpx.Request, *args: Any, **kwargs: Any
    ) -> httpx.Response:  # type: ignore[override]
        is_messages_endpoint = request.url.path.endswith("/v1/messages")

        # Proactive token refresh: check JWT age before every request
        if not request.extensions.get("claude_oauth_refresh_attempted"):
            try:
                if self._should_refresh_token(request):
                    refreshed_token = self._refresh_claude_oauth_token()
                    if refreshed_token:
                        logger.info("Proactively refreshed token before request")
                        # Rebuild request with new token
                        headers = dict(request.headers)
                        self._update_auth_headers(headers, refreshed_token)
                        body_bytes = self._extract_body_bytes(request)
                        request = self.build_request(
                            method=request.method,
                            url=request.url,
                            headers=headers,
                            content=body_bytes,
                        )
                        request.extensions["claude_oauth_refresh_attempted"] = True
            except Exception as exc:
                logger.debug("Error during proactive token refresh check: %s", exc)

        # Apply Claude Code OAuth transformations for /v1/messages
        if is_messages_endpoint:
            try:
                body_bytes = self._extract_body_bytes(request)
                headers = dict(request.headers)
                url = request.url
                body_modified = False
                headers_modified = False

                # 1. Transform headers for Claude Code OAuth
                self._transform_headers_for_claude_code(headers)
                headers_modified = True

                # 2. Add ?beta=true query param
                url = self._add_beta_query_param(url)

                # 3. Prefix tool names in request body
                if body_bytes:
                    prefixed_body = self._prefix_tool_names(body_bytes)
                    if prefixed_body is not None:
                        body_bytes = prefixed_body
                        body_modified = True

                    # 4. Inject cache_control
                    cached_body = self._inject_cache_control(body_bytes)
                    if cached_body is not None:
                        body_bytes = cached_body
                        body_modified = True

                # Rebuild request if anything changed
                if body_modified or headers_modified or url != request.url:
                    try:
                        rebuilt = self.build_request(
                            method=request.method,
                            url=url,
                            headers=headers,
                            content=body_bytes,
                        )

                        # Copy core internals so httpx uses the modified body/stream
                        if hasattr(rebuilt, "_content"):
                            setattr(request, "_content", rebuilt._content)  # type: ignore[attr-defined]
                        if hasattr(rebuilt, "stream"):
                            request.stream = rebuilt.stream
                        if hasattr(rebuilt, "extensions"):
                            request.extensions = rebuilt.extensions

                        # Update URL
                        request.url = url

                        # Update headers
                        for key, value in headers.items():
                            request.headers[key] = value

                        # Ensure Content-Length matches the new body
                        if body_bytes:
                            request.headers["Content-Length"] = str(len(body_bytes))

                    except Exception as exc:
                        logger.debug("Error rebuilding request: %s", exc)

            except Exception as exc:
                logger.debug("Error in Claude Code transformations: %s", exc)

        # Send the request
        response = await super().send(request, *args, **kwargs)

        # Transform streaming response to unprefix tool names
        if is_messages_endpoint and response.status_code == 200:
            try:
                response = self._wrap_response_with_tool_unprefixing(response, request)
            except Exception as exc:
                logger.debug("Error wrapping response for tool unprefixing: %s", exc)

        # Handle auth errors with token refresh
        try:
            if response.status_code in (400, 401) and not request.extensions.get(
                "claude_oauth_refresh_attempted"
            ):
                is_auth_error = response.status_code == 401

                if response.status_code == 400:
                    is_auth_error = self._is_cloudflare_html_error(response)
                    if is_auth_error:
                        logger.info(
                            "Detected Cloudflare 400 error (likely auth-related), attempting token refresh"
                        )

                if is_auth_error:
                    refreshed_token = self._refresh_claude_oauth_token()
                    if refreshed_token:
                        logger.info("Token refreshed successfully, retrying request")
                        await response.aclose()
                        body_bytes = self._extract_body_bytes(request)
                        headers = dict(request.headers)
                        self._update_auth_headers(headers, refreshed_token)
                        retry_request = self.build_request(
                            method=request.method,
                            url=request.url,
                            headers=headers,
                            content=body_bytes,
                        )
                        retry_request.extensions["claude_oauth_refresh_attempted"] = (
                            True
                        )
                        return await super().send(retry_request, *args, **kwargs)
                    else:
                        logger.warning("Token refresh failed, returning original error")
        except Exception as exc:
            logger.debug("Error during token refresh attempt: %s", exc)

        return response

    def _wrap_response_with_tool_unprefixing(
        self, response: httpx.Response, request: httpx.Request
    ) -> httpx.Response:
        """Wrap a streaming response to unprefix tool names.

        Creates a new response with a transformed stream that removes the
        TOOL_PREFIX from tool names in the response body.
        """
        original_stream = response.stream
        unprefix_fn = self._unprefix_tool_names_in_text

        class UnprefixingStream(httpx.AsyncByteStream):
            """Async byte stream that unprefixes tool names.

            Inherits from httpx.AsyncByteStream to ensure proper stream interface.
            """

            def __init__(self, inner_stream: Any) -> None:
                self._inner = inner_stream

            async def __aiter__(self):
                async for chunk in self._inner:
                    if isinstance(chunk, bytes):
                        text = chunk.decode("utf-8", errors="replace")
                        text = unprefix_fn(text)
                        yield text.encode("utf-8")
                    else:
                        yield chunk

            async def aclose(self) -> None:
                if hasattr(self._inner, "aclose"):
                    try:
                        result = self._inner.aclose()
                        # Handle both sync and async aclose
                        if hasattr(result, "__await__"):
                            await result
                    except Exception:
                        pass  # Ignore close errors
                elif hasattr(self._inner, "close"):
                    try:
                        self._inner.close()
                    except Exception:
                        pass

        # Create a new response with the transformed stream
        # Must include request for raise_for_status() to work
        new_response = httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=UnprefixingStream(original_stream),
            extensions=response.extensions,
            request=request,
        )
        return new_response

    @staticmethod
    def _extract_body_bytes(request: httpx.Request) -> bytes | None:
        # Try public content first
        try:
            content = request.content
            if content:
                return content
        except Exception:
            pass

        # Fallback to private attr if necessary
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
        if "Authorization" in headers or "authorization" in headers:
            headers["Authorization"] = bearer_value
        elif "x-api-key" in headers or "X-API-Key" in headers:
            headers["x-api-key"] = access_token
        else:
            headers["Authorization"] = bearer_value

    @staticmethod
    def _is_cloudflare_html_error(response: httpx.Response) -> bool:
        """Check if this is a Cloudflare HTML error response.

        Cloudflare often returns HTML error pages with status 400 when
        there are authentication issues.
        """
        # Check content type
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type.lower():
            return False

        # Check if body contains Cloudflare markers
        try:
            # Read response body if not already consumed
            if hasattr(response, "_content") and response._content:
                body = response._content.decode("utf-8", errors="ignore")
            else:
                # Try to read the text (this might be already consumed)
                try:
                    body = response.text
                except Exception:
                    return False

            # Look for Cloudflare and 400 Bad Request markers
            body_lower = body.lower()
            return "cloudflare" in body_lower and "400 bad request" in body_lower
        except Exception as exc:
            logger.debug("Error checking for Cloudflare error: %s", exc)
            return False

    def _refresh_claude_oauth_token(self) -> str | None:
        try:
            from code_puppy.plugins.claude_code_oauth.utils import refresh_access_token

            logger.info("Attempting to refresh Claude Code OAuth token...")
            refreshed_token = refresh_access_token(force=True)
            if refreshed_token:
                self._update_auth_headers(self.headers, refreshed_token)
                logger.info("Successfully refreshed Claude Code OAuth token")
            else:
                logger.warning("Token refresh returned None")
            return refreshed_token
        except Exception as exc:
            logger.error("Exception during token refresh: %s", exc)
            return None

    @staticmethod
    def _inject_cache_control(body: bytes) -> bytes | None:
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        modified = False

        # Minimal, deterministic strategy:
        # Add cache_control only on the single most recent block:
        # the last dict content block of the last message (if any).
        messages = data.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict):
                content = last.get("content")
                if isinstance(content, list) and content:
                    last_block = content[-1]
                    if (
                        isinstance(last_block, dict)
                        and "cache_control" not in last_block
                    ):
                        last_block["cache_control"] = {"type": "ephemeral"}
                        modified = True

        if not modified:
            return None

        return json.dumps(data).encode("utf-8")


def _inject_cache_control_in_payload(payload: dict[str, Any]) -> None:
    """In-place cache_control injection on Anthropic messages.create payload."""

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        if isinstance(last, dict):
            content = last.get("content")
            if isinstance(content, list) and content:
                last_block = content[-1]
                if isinstance(last_block, dict) and "cache_control" not in last_block:
                    last_block["cache_control"] = {"type": "ephemeral"}

    # No extra markers in production mode; keep payload clean.
    # (Function kept for potential future use.)
    return


def patch_anthropic_client_messages(client: Any) -> None:
    """Monkey-patch AsyncAnthropic.messages.create to inject cache_control.

    This operates at the highest level: just before Anthropic SDK serializes
    the request into HTTP. That means no httpx / Pydantic shenanigans can
    undo it.
    """

    if AsyncAnthropic is None or not isinstance(client, AsyncAnthropic):  # type: ignore[arg-type]
        return

    try:
        messages_obj = getattr(client, "messages", None)
        if messages_obj is None:
            return
        original_create: Callable[..., Any] = messages_obj.create
    except Exception:  # pragma: no cover - defensive
        return

    async def wrapped_create(*args: Any, **kwargs: Any):
        # Anthropic messages.create takes a mix of positional/kw args.
        # The payload is usually in kwargs for the Python SDK.
        if kwargs:
            _inject_cache_control_in_payload(kwargs)
        elif args:
            maybe_payload = args[-1]
            if isinstance(maybe_payload, dict):
                _inject_cache_control_in_payload(maybe_payload)

        return await original_create(*args, **kwargs)

    messages_obj.create = wrapped_create  # type: ignore[assignment]
