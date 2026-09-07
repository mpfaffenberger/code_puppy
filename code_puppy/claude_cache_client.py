"""OAuth-aware HTTP transport for Claude Code and Anthropic models.

Prompt caching is configured through pydantic-ai's native
``AnthropicModelSettings``. This client deliberately does not rewrite cache
markers; it only owns transport concerns that cannot be expressed there:
OAuth refresh/retry, Claude Code tool-name prefixing, request headers, URL
parameters, and the Opus summarized-thinking compatibility transform.

Built on ``httpx2`` (not ``httpx``): every consumer of this client hands it
to ``anthropic.AsyncAnthropic``, and the Anthropic SDK moved to httpx2 in
its 1.0 release (pydantic-ai >= 2.35 followed). The rest of Code Puppy
(OpenAI providers, http_utils) still rides classic httpx.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, MutableMapping
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx2

from .claude_oauth_transport import ClaudeOAuthTransport

logger = logging.getLogger(__name__)

# Refresh tokens before the OAuth subscription's one-hour age limit.
TOKEN_MAX_AGE_SECONDS = 3600

# Retry transient provider failures without duplicating SDK behavior.
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
MAX_RETRIES = 5

# Claude Code requires this namespace for outgoing tool names.
TOOL_PREFIX = "cp_"

CLAUDE_CLI_USER_AGENT = "claude-cli/2.1.251 (external, cli)"

# The Claude Code OAuth endpoint fingerprints this exact string as the FIRST
# system block; requests that lead with anything else get rejected. Mirrors
# CLAUDE_CODE_INSTRUCTIONS in the claude_code_oauth plugin's prompt_handler.
CLAUDE_CODE_SYSTEM_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."

# Beta flag required for ``thinking.display: "updates"`` (Fable 5.1 progress
# updates surfaced as text while reasoning stays hidden).
THINKING_DISPLAY_UPDATES_BETA = "thinking-display-updates-2026-08-18"


def _model_requires_thinking_summary(model_name):
    if not model_name:
        return False
    from code_puppy.model_utils import should_use_anthropic_thinking_summary

    return should_use_anthropic_thinking_summary(model_name)


def _model_supports_thinking_updates(model_name):
    if not model_name:
        return False
    from code_puppy.model_utils import should_use_anthropic_thinking_updates

    return should_use_anthropic_thinking_updates(model_name)


def _enforce_thinking_display_summary(payload):
    if not isinstance(payload, dict):
        return False
    if not _model_requires_thinking_summary(payload.get("model")):
        return False
    thinking = payload.get("thinking")
    if not isinstance(thinking, dict):
        return False
    display = thinking.get("display")
    if display == "summarized":
        return False
    if display == "updates" and _model_supports_thinking_updates(payload.get("model")):
        # Fable 5.1 legitimately asked for progress updates; don't clobber
        # it back to summarized (which would drown status lines in reasoning).
        return False
    thinking["display"] = "summarized"
    return True


class ClaudeCacheAsyncClient(ClaudeOAuthTransport, httpx2.AsyncClient):
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
        oauth_token_provider: Callable | None = None,
        oauth_refresh_callback: Callable | None = None,
        oauth_origin: str = "https://api.anthropic.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._oauth_reauthentication_callback = oauth_reauthentication_callback
        self._token_update_callback = token_update_callback
        self._apply_claude_code_prefix = apply_claude_code_prefix
        self._oauth_token_provider = oauth_token_provider
        self._oauth_refresh_callback = oauth_refresh_callback
        self._oauth_origin = httpx2.URL(oauth_origin)
        self._oauth_enabled = apply_claude_code_prefix

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
    def _ensure_claude_code_system_prompt(body: bytes) -> bytes | None:
        """Guarantee the first system block is the Claude Code instruction.

        The main agent path already leads with it (the claude_code_oauth
        plugin's ``prepare_model_prompt`` hook), but internally-built agents
        — e.g. pydantic-ai-harness's ``SummarizingCompaction`` summarizer —
        ship their own instructions and never pass through that hook. The
        OAuth endpoint fingerprints the first system block, so enforce the
        invariant here, the one choke point every claude-code request
        crosses. A pre-existing system prompt is demoted to the second
        block, never dropped. Returns None when the body is already fine.
        """
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        system = data.get("system")
        if isinstance(system, str):
            if system.startswith(CLAUDE_CODE_SYSTEM_PROMPT):
                return None
            blocks: list[Any] = [{"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT}]
            if system:
                blocks.append({"type": "text", "text": system})
            data["system"] = blocks
        elif isinstance(system, list):
            first = system[0] if system else None
            text = first.get("text") if isinstance(first, dict) else None
            if isinstance(text, str) and text.startswith(CLAUDE_CODE_SYSTEM_PROMPT):
                return None
            data["system"] = [
                {"type": "text", "text": CLAUDE_CODE_SYSTEM_PROMPT},
                *system,
            ]
        elif system is None:
            data["system"] = CLAUDE_CODE_SYSTEM_PROMPT
        else:
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
    def _ensure_thinking_updates_beta(
        headers: MutableMapping[str, str], body_bytes: bytes | None
    ) -> bool:
        """Add the updates-display beta flag when the body requests it.

        ``thinking.display: "updates"`` (Fable 5.1 progress updates) is
        rejected without the ``thinking-display-updates-2026-08-18`` beta
        header. Deciding here — off the final request body — keeps header and
        body consistent across every transport that rides this client
        (anthropic, custom_anthropic, claude_code OAuth).

        Returns True when the header was modified.
        """
        if not body_bytes:
            return False
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return False
        thinking = payload.get("thinking") if isinstance(payload, dict) else None
        if not (isinstance(thinking, dict) and thinking.get("display") == "updates"):
            return False
        existing = [
            b.strip() for b in headers.get("anthropic-beta", "").split(",") if b.strip()
        ]
        if THINKING_DISPLAY_UPDATES_BETA in existing:
            return False
        existing.append(THINKING_DISPLAY_UPDATES_BETA)
        headers["anthropic-beta"] = ",".join(existing)
        return True

    @staticmethod
    def _add_beta_query_param(url: httpx2.URL) -> httpx2.URL:
        """Add ?beta=true query parameter to the URL if not already present."""
        parsed = urlparse(str(url))
        query_params = parse_qs(parsed.query)
        if "beta" not in query_params:
            query_params["beta"] = ["true"]
            new_query = urlencode(query_params, doseq=True)
            new_parsed = parsed._replace(query=new_query)
            return httpx2.URL(urlunparse(new_parsed))
        return url

    async def send(
        self, request: httpx2.Request, *args: Any, **kwargs: Any
    ) -> httpx2.Response:  # type: ignore[override]
        is_messages_endpoint = request.url.path.endswith("/v1/messages")
        oauth_request = self._is_oauth_request(request)
        if self._oauth_enabled and not oauth_request:
            raise ValueError(
                "Claude OAuth credentials may only be sent to their configured HTTPS origin"
            )
        if oauth_request:
            # httpx follows redirects internally, bypassing our origin guard.
            # OAuth API requests must not delegate credential routing to it.
            kwargs["follow_redirects"] = False
            await self._prepare_oauth_request(request)
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
                    system_body = self._ensure_claude_code_system_prompt(body_bytes)
                    if system_body is not None:
                        body_bytes = system_body
                        body_modified = True
                if body_bytes:
                    summarized_body = self._enforce_thinking_display_summary_body(
                        body_bytes
                    )
                    if summarized_body is not None:
                        body_bytes = summarized_body
                        body_modified = True
                # After body transforms settle: updates-display requests
                # (Fable 5.1) must carry the matching beta header.
                if self._ensure_thinking_updates_beta(headers, body_bytes):
                    headers_modified = True
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
            if (
                oauth_request
                and response.status_code in (400, 401, 403)
                and not request.extensions.get("claude_oauth_refresh_attempted")
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
                        await self._recover_claude_oauth_token_after_auth_error_async(
                            self._extract_bearer_token(request)
                        )
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
                            extensions=dict(request.extensions),
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
        self, request: httpx2.Request, *args: Any, **kwargs: Any
    ) -> httpx2.Response:
        """Retry rate limits, server failures, and transient connections."""
        last_response: httpx2.Response | None = None
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
            except (httpx2.ConnectError, httpx2.ReadTimeout, httpx2.PoolTimeout) as exc:
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
    def _extract_body_bytes(request: httpx2.Request) -> bytes | None:
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
