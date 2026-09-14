"""Credential lifecycle for explicitly opted-in Claude OAuth transports."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import time
from typing import Any, Callable, MutableMapping

import httpx2

logger = logging.getLogger(__name__)
TOKEN_MAX_AGE_SECONDS = 3600


class ClaudeOAuthTransport:
    """OAuth helpers shared by the Claude HTTP transport, never API-key clients."""

    def _is_oauth_request(self, request: httpx2.Request) -> bool:
        origin = self._oauth_origin
        return (
            self._oauth_enabled
            and request.url.scheme == "https"
            and (request.url.host, request.url.port) == (origin.host, origin.port)
        )

    @staticmethod
    async def _call_provider(callback, *args, **kwargs):
        if inspect.iscoroutinefunction(callback):
            return await callback(*args, **kwargs)
        result = await asyncio.to_thread(callback, *args, **kwargs)
        return await result if inspect.isawaitable(result) else result

    async def _prepare_oauth_request(self, request: httpx2.Request) -> None:
        if self._oauth_token_provider is not None:
            # A missing token (logout, expired credentials, failed refresh) must
            # never silently fall back to credentials retained by the SDK.
            token = await self._call_provider(self._oauth_token_provider)
            if not isinstance(token, str) or not token:
                raise ValueError(
                    "No valid Claude OAuth credentials available; reauthenticate"
                )
            self._apply_token_refresh_results([token])
            self._update_auth_headers(request.headers, token)
        elif await self._should_refresh_token_async(request):
            token = await self._refresh_claude_oauth_token_async()
            if token:
                self._update_auth_headers(request.headers, token)

    async def _recover_claude_oauth_token_after_auth_error_async(
        self, rejected_token: str | None
    ) -> str | None:
        if self._oauth_refresh_callback is not None:
            token = await self._call_provider(
                self._oauth_refresh_callback, rejected_token=rejected_token
            )
            token = self._apply_token_refresh_results([token])
        else:
            token = await self._refresh_claude_oauth_token_async()
        if token or not self._oauth_reauthentication_callback:
            return token
        token = await self._call_provider(self._oauth_reauthentication_callback)
        return self._apply_token_refresh_results([token])

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

    def _extract_bearer_token(self, request: httpx2.Request) -> str | None:
        """Extract the bearer token from request headers."""
        auth_header = request.headers.get("Authorization") or request.headers.get(
            "authorization"
        )
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:]  # Strip "Bearer " prefix
        return None

    def _jwt_refresh_decision(self, request: httpx2.Request) -> bool | None:
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

    def _should_refresh_token(self, request: httpx2.Request) -> bool:
        """Synchronously check JWT age, then the stored-token callback."""
        decision = self._jwt_refresh_decision(request)
        if decision is not None:
            return decision
        return self._log_stored_token_refresh(self._check_stored_token_expiry())

    async def _should_refresh_token_async(self, request: httpx2.Request) -> bool:
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
    async def _is_cloudflare_html_error(response: httpx2.Response) -> bool:
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
