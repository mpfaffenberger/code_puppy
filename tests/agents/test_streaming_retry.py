"""Tests for transient streaming retry behavior.

These stay intentionally focused on the retry classifier and retry loop so
we don't need to spin up the entire BaseAgent circus just to verify whether
network gremlins get another chance.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpcore
import httpx
import pytest
from pydantic_ai import UnexpectedModelBehavior

from code_puppy.agents.base_agent import should_retry_streaming_exception

try:
    from openai import APIError
except ImportError:  # pragma: no cover - optional dependency in some test envs
    APIError = None

MAX_STREAMING_RETRIES = 3
STREAMING_RETRY_DELAYS = [1, 2, 4]


async def _run_with_streaming_retry(run_coro_factory):
    last_error = None
    for attempt in range(MAX_STREAMING_RETRIES):
        try:
            return await run_coro_factory()
        except Exception as e:
            if not should_retry_streaming_exception(e):
                raise
            last_error = e
            if attempt < MAX_STREAMING_RETRIES - 1:
                delay = STREAMING_RETRY_DELAYS[attempt]
                await asyncio.sleep(delay)
    raise last_error


def _make_openai_api_error(message: str, *, body=None):
    if APIError is None:
        pytest.skip("openai is not installed in this test environment")
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return APIError(message, request=request, body=body)


class TestStreamingRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        factory = AsyncMock(return_value="ok")

        result = await _run_with_streaming_retry(factory)

        assert result == "ok"
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_httpx_remote_protocol_error(self):
        factory = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError("peer closed connection"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpx_read_timeout(self):
        factory = AsyncMock(
            side_effect=[
                httpx.ReadTimeout("read timed out"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpx_read_error(self):
        # Regression: a dropped socket mid-stream (e.g. VPN/WiFi blip) raises
        # httpx.ReadError. It used to escape the retry classifier and crash
        # the whole REPL. A connection-management hiccup must never be fatal.
        factory = AsyncMock(
            side_effect=[
                httpx.ReadError("connection dropped mid-stream"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpx_connect_error(self):
        factory = AsyncMock(
            side_effect=[
                httpx.ConnectError("failed to establish connection"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpcore_read_error(self):
        factory = AsyncMock(
            side_effect=[
                httpcore.ReadError("connection dropped mid-stream"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpcore_remote_protocol_error(self):
        factory = AsyncMock(
            side_effect=[
                httpcore.RemoteProtocolError("peer closed connection"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_transient_openai_api_error(self):
        factory = AsyncMock(
            side_effect=[
                _make_openai_api_error(
                    "Service unavailable, please retry.",
                    body={
                        "message": "Service unavailable, please retry.",
                        "type": "server_error",
                    },
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_unexpected_model_behavior_with_streaming_message(self):
        factory = AsyncMock(
            side_effect=[
                UnexpectedModelBehavior("streamed response ended without content"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self):
        factory = AsyncMock(side_effect=ValueError("not a network error"))

        with pytest.raises(ValueError, match="not a network error"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_non_transient_openai_api_error_does_not_retry(self):
        error = _make_openai_api_error(
            "Nope.",
            body={"message": "Nope.", "type": "invalid_request_error"},
        )
        factory = AsyncMock(side_effect=error)

        with pytest.raises(type(error), match="Nope"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        error = httpx.RemoteProtocolError("keep failing")
        factory = AsyncMock(side_effect=error)
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(httpx.RemoteProtocolError):
                await _run_with_streaming_retry(factory)

        assert sleep_calls == [1, 2]

    @pytest.mark.asyncio
    async def test_raises_last_retryable_exception_after_exhaustion(self):
        error = httpx.RemoteProtocolError("persistent failure")
        factory = AsyncMock(side_effect=error)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.RemoteProtocolError, match="persistent failure"):
                await _run_with_streaming_retry(factory)

        assert factory.await_count == MAX_STREAMING_RETRIES

    def test_classifier_accepts_retryable_streaming_errors(self):
        assert should_retry_streaming_exception(
            httpx.RemoteProtocolError("peer closed connection")
        )
        assert should_retry_streaming_exception(httpx.ReadTimeout("timed out"))
        assert should_retry_streaming_exception(
            httpx.ReadError("connection dropped mid-stream")
        )
        assert should_retry_streaming_exception(
            httpx.ConnectError("failed to establish connection")
        )
        assert should_retry_streaming_exception(
            httpx.ConnectTimeout("connect timed out")
        )
        assert should_retry_streaming_exception(
            httpcore.RemoteProtocolError("peer closed connection")
        )
        assert should_retry_streaming_exception(
            httpcore.ReadError("connection dropped mid-stream")
        )
        assert should_retry_streaming_exception(
            UnexpectedModelBehavior("streamed response ended without content")
        )

    def test_classifier_rejects_non_retryable_errors(self):
        assert not should_retry_streaming_exception(ValueError("nope"))
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("tool schema validation exploded")
        )


# Each of these snippets is either an explicit provider "please retry" hint or
# an SSE framing artifact that reliably succeeds on retry. They were added as
# part of issue #294. Keep this list aligned with ``_RETRYABLE_SNIPPETS``.
_NEW_RETRYABLE_SNIPPETS = [
    "malformed streamed SSE event",
    "extra JSON data in SSE payload",
    "Too Many Requests",
    "rate limited",
    "server had an error processing your request",
    "please retry your request",
    "internal server error",
    # Generic "stream ... ended" fallback — covers wording we don't yet know.
    "stream connection ended unexpectedly",
    "stream ended early",
]


class TestExpandedRetryClassifier:
    """Coverage for the expanded retry snippet list (issue #294)."""

    @pytest.mark.parametrize("snippet", _NEW_RETRYABLE_SNIPPETS)
    def test_unexpected_model_behavior_snippet_is_retryable(self, snippet):
        assert should_retry_streaming_exception(UnexpectedModelBehavior(snippet))

    @pytest.mark.parametrize("snippet", _NEW_RETRYABLE_SNIPPETS)
    def test_openai_api_error_body_snippet_is_retryable(self, snippet):
        err = _make_openai_api_error(
            snippet,
            body={"message": snippet, "type": "server_error"},
        )
        assert should_retry_streaming_exception(err)

    def test_classifier_still_rejects_unrelated_errors(self):
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("your prompt is malformed")
        )
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("stream opened but no body")
        )  # matches 'stream' but not 'ended'

    def test_generic_stream_ended_fallback(self):
        # Different phrasings, all transient.
        for phrasing in (
            "the stream ended prematurely",
            "stream connection ended mid-chunk",
            "upstream stream ended unexpectedly",
        ):
            assert should_retry_streaming_exception(UnexpectedModelBehavior(phrasing))


class TestWrappedTransientErrors:
    """Regression coverage for PR #482's blind spot.

    Real-world transient failures don't show up as bare httpx exceptions --
    they arrive wrapped in :class:`pydantic_ai.exceptions.ModelAPIError` or
    :class:`anthropic.APIStatusError`. The classifier must walk the cause
    chain *and* recognise these wrappers directly, otherwise a VPN/gateway
    blip surfaces as a 60-line REPL traceback instead of a silent retry.
    """

    def test_pydantic_ai_model_api_error_via_cause_chain(self):
        # Shape: pydantic-ai's anthropic adapter raises
        # ``ModelAPIError("Connection error.") from anthropic.APIConnectionError(...)``
        # whose own ``__cause__`` is the underlying httpx error.
        from pydantic_ai.exceptions import ModelAPIError

        underlying = httpx.ConnectError("failed to establish connection")
        wrapper = ModelAPIError(model_name="claude-x", message="Connection error.")
        wrapper.__cause__ = underlying
        assert should_retry_streaming_exception(wrapper)

    def test_pydantic_ai_model_api_error_via_snippet(self):
        # Same wrapper, but the cause chain has been severed by some upstream
        # layer. Snippet match on the message must still catch it.
        from pydantic_ai.exceptions import ModelAPIError

        wrapper = ModelAPIError(model_name="claude-x", message="Connection error.")
        assert should_retry_streaming_exception(wrapper)

    def test_anthropic_api_status_error_upstream_idle_timeout(self):
        # Shape: gateway emits a 200/streaming response then stalls; the
        # Anthropic SDK surfaces it as APIStatusError with type=api_error
        # and the message we see in production: "upstream_idle_timeout ...".
        from anthropic import APIStatusError

        body = {
            "error": {
                "message": "upstream_idle_timeout (rid=abc): no data for 60s",
                "type": "api_error",
            }
        }
        # Construct via __new__ so we don't have to fake the SDK's full
        # Response/request plumbing -- the classifier only reads .status_code,
        # .body, and str(exc).
        err = APIStatusError.__new__(APIStatusError)
        err.status_code = 502
        err.body = body
        err.message = body["error"]["message"]
        assert should_retry_streaming_exception(err)

    def test_anthropic_api_status_error_500(self):
        from anthropic import APIStatusError

        err = APIStatusError.__new__(APIStatusError)
        err.status_code = 500
        err.body = {"error": {"message": "internal", "type": "server_error"}}
        err.message = "internal"
        assert should_retry_streaming_exception(err)

    def test_anthropic_api_status_error_400_not_retryable(self):
        # 4xx (other than 429 which the existing ModelHTTPError branch covers)
        # should NOT be retried -- those are client-side mistakes, not blips.
        from anthropic import APIStatusError

        err = APIStatusError.__new__(APIStatusError)
        err.status_code = 400
        err.body = {
            "error": {"message": "bad request", "type": "invalid_request_error"}
        }
        err.message = "bad request"
        assert not should_retry_streaming_exception(err)

    def test_anthropic_api_connection_error_bare(self):
        from anthropic import APIConnectionError

        # APIConnectionError's __init__ requires a request; construct via __new__
        # to keep the test independent of SDK plumbing.
        err = APIConnectionError.__new__(APIConnectionError)
        err.message = "connection error"
        assert should_retry_streaming_exception(err)

    def test_cause_chain_is_cycle_safe(self):
        # A pathological self-referencing chain must terminate and still
        # produce the right verdict for any retryable link in the chain.
        a = ValueError("opaque")
        b = httpx.ConnectError("transient")
        a.__cause__ = b
        b.__cause__ = a  # cycle
        assert should_retry_streaming_exception(a)

    def test_cause_chain_walks_context_too(self):
        # ``raise X`` inside an ``except: ...`` sets __context__, not __cause__.
        # The walker covers both so library code that uses bare ``raise`` still
        # gets its transient origin detected.
        outer = RuntimeError("opaque wrapper")
        outer.__context__ = httpx.ReadTimeout("slow upstream")
        assert should_retry_streaming_exception(outer)

    def test_genuine_non_transient_still_rejected(self):
        # Belt-and-braces: the new logic must not classify ordinary bugs as transient.
        assert not should_retry_streaming_exception(ValueError("nope"))
        assert not should_retry_streaming_exception(TypeError("bad type"))

    def test_cause_chain_depth_is_bounded(self):
        # If someone tightens the depth cap below the real-world chain length
        # (pydantic-ai → anthropic-sdk → httpx → socket = ~4 layers), we should
        # notice in CI rather than in production. Hide the transient at link 8
        # of a 10-link chain; current cap of 5 means it should NOT be detected.
        # If anyone bumps the cap into double-digits, this assertion flips and
        # they have to update it -- which is the conversation we want to force.
        chain: list[BaseException] = [ValueError(f"opaque {i}") for i in range(8)]
        chain.append(httpx.ConnectError("transient"))
        chain.append(ValueError("tail"))
        for upper, lower in zip(chain, chain[1:]):
            upper.__cause__ = lower
        # Verdict is False because the transient lives outside the depth cap.
        # If this assertion ever flips, the cap moved -- intentional or not,
        # the change deserves to be looked at deliberately.
        assert not should_retry_streaming_exception(chain[0])


def _make_anthropic_502() -> "BaseException":
    """Reproduce the production 502: a Google-gateway HTML error page bubbled
    up by the Anthropic SDK as APIStatusError(status_code=502).

    The message is a giant HTML blob (``[HTTP 502] <!DOCTYPE html>...``) that
    matches NO retry snippet -- the only reliable signal is ``status_code``.
    """
    from anthropic import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 502
    err.body = {"message": "[HTTP 502] <!DOCTYPE html> ... 502. That's an error."}
    err.message = "[HTTP 502] <!DOCTYPE html> ... 502. That's an error."
    return err


class TestExceptionGroupUnwrapping:
    """Regression coverage for the real-world 502 crash.

    pydantic-ai streams the model response inside an anyio task group, so a
    transient provider error (e.g. anthropic.APIStatusError HTTP 502 from a
    gateway) reaches ``run_agent_task`` wrapped in an ExceptionGroup -- which
    is why that code path uses ``except*``. The classifier used to only walk
    ``__cause__``/``__context__`` and never descended into ``.exceptions``, so
    a perfectly retryable 5xx looked opaque and crashed the REPL with a
    60-line traceback instead of getting the slow 1-2-3 retry.
    """

    def test_bare_anthropic_502_is_retryable(self):
        # Sanity: even outside a group, an HTML-body 502 must retry purely on
        # status_code (its message matches no snippet).
        assert should_retry_streaming_exception(_make_anthropic_502())

    def test_exception_group_wrapping_502_is_retryable(self):
        # The exact production shape: ExceptionGroup([APIStatusError(502)]).
        group = ExceptionGroup(
            "unhandled errors in a TaskGroup", [_make_anthropic_502()]
        )
        assert should_retry_streaming_exception(group)

    def test_nested_exception_groups_are_retryable(self):
        # anyio can nest groups when tasks spawn sub-tasks. Descend all the way.
        inner = ExceptionGroup("inner", [_make_anthropic_502()])
        outer = ExceptionGroup("outer", [ValueError("noise"), inner])
        assert should_retry_streaming_exception(outer)

    def test_exception_group_member_via_cause_chain(self):
        # A group member that hides its transient origin in __cause__ must still
        # be caught -- we walk each member's cause chain, not just the member.
        wrapper = RuntimeError("opaque wrapper")
        wrapper.__cause__ = httpx.ConnectError("dropped socket")
        group = ExceptionGroup("grp", [ValueError("noise"), wrapper])
        assert should_retry_streaming_exception(group)

    def test_exception_group_of_only_non_transient_is_not_retryable(self):
        # Belt-and-braces: a group of genuine bugs must NOT be retried.
        group = ExceptionGroup("grp", [ValueError("bug"), TypeError("also bug")])
        assert not should_retry_streaming_exception(group)

    def test_exception_group_is_cycle_safe(self):
        # A member whose cause points back at a sibling must still terminate.
        a = ValueError("a")
        b = httpx.ConnectError("transient")
        a.__cause__ = b
        b.__cause__ = a
        group = ExceptionGroup("grp", [a])
        assert should_retry_streaming_exception(group)


class TestOpenAIStatusCodeRetry:
    """The OpenAI branch must retry 5xx/429 on status_code alone.

    Mirrors the Anthropic and ModelHTTPError branches. An OpenAI-compatible
    gateway 502 whose body is an HTML error page matches no snippet -- the only
    reliable signal is the HTTP status the SDK exposes on APIStatusError.
    """

    def _make_openai_status_error(self, status_code: int, message: str | None = None):
        try:
            from openai import APIStatusError
        except ImportError:  # pragma: no cover
            pytest.skip("openai is not installed in this test environment")
        if message is None:
            message = "<!DOCTYPE html> 502 Bad Gateway"
        err = APIStatusError.__new__(APIStatusError)
        err.status_code = status_code
        err.body = {"message": message}
        err.message = message
        return err

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504, 429])
    def test_transient_status_codes_retry(self, status_code):
        assert should_retry_streaming_exception(
            self._make_openai_status_error(status_code)
        )

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_client_errors_do_not_retry(self, status_code):
        # A snippet-free client-error body -- status_code is the only signal,
        # and 4xx (other than 429) must NOT retry.
        assert not should_retry_streaming_exception(
            self._make_openai_status_error(
                status_code, message="invalid request payload"
            )
        )


class TestInBandSSE5xx:
    """Regression for the *real* production 502 that defeated every prior fix.

    A gateway (puppy-backend ``custom_anthropic`` proxy) delivers an upstream
    5xx as an **in-band SSE ``error`` event over a connection that was itself
    HTTP 200**. The Anthropic SDK builds an ``APIStatusError`` from the *stream*
    response, so:

      * ``status_code`` is **200** (not 502),
      * the exception is a plain ``APIStatusError`` (not ``InternalServerError``),
      * ``body.error.type`` is a generic ``"internal_error"``,
      * the only faithful trace of the failure is a ``[HTTP 502]`` marker baked
        into the message text.

    The classifier used to check ``status_code``, snippet matches, and a fixed
    set of error ``type`` values -- all of which miss this shape -- so a
    perfectly transient gateway 5xx crashed the REPL. This descends into the
    ``[HTTP 5xx]`` marker instead.
    """

    def _make_anthropic_inband_5xx(self, http_code: int):
        from anthropic import Anthropic

        client = Anthropic(api_key="sk-fake")
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        # The stream itself returned 200 -- the failure is in-band.
        resp = httpx.Response(200, request=req)
        body = {
            "error": {
                "message": f"[HTTP {http_code}] <!DOCTYPE html> ... {http_code}. "
                "That's an error. The server encountered a temporary error ...",
                "type": "internal_error",
            },
            "type": "error",
        }
        return client._make_status_error(f"{body}", body=body, response=resp)

    @pytest.mark.parametrize("http_code", [500, 502, 503, 504, 529])
    def test_inband_5xx_marker_retries(self, http_code):
        # status_code is 200; the real status lives only in the [HTTP NNN] marker.
        err = self._make_anthropic_inband_5xx(http_code)
        assert err.status_code == 200  # sanity: proves the trap this guards
        assert should_retry_streaming_exception(err)

    def test_inband_5xx_wrapped_in_exception_group_retries(self):
        # The exact production shape: anyio wraps it in an ExceptionGroup.
        err = self._make_anthropic_inband_5xx(502)
        group = ExceptionGroup("unhandled errors in a TaskGroup", [err])
        assert should_retry_streaming_exception(group)

    def test_inband_internal_error_type_retries(self):
        # Even without a marker match, type "internal_error" is a server-side
        # Anthropic failure and must retry (belt-and-braces).
        from anthropic import Anthropic

        client = Anthropic(api_key="sk-fake")
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = httpx.Response(200, request=req)
        body = {
            "error": {"message": "opaque", "type": "internal_error"},
            "type": "error",
        }
        err = client._make_status_error(f"{body}", body=body, response=resp)
        assert should_retry_streaming_exception(err)

    @pytest.mark.parametrize("http_code", [400, 401, 403, 404, 422])
    def test_inband_4xx_marker_does_not_retry(self, http_code):
        # A [HTTP 4xx] marker is a genuine client error -- must NOT retry.
        # Uses a clean client-error body (no server-error wording) so the
        # assertion stays robust even if the retryable-snippet list grows.
        from anthropic import Anthropic

        client = Anthropic(api_key="sk-fake")
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = httpx.Response(200, request=req)
        body = {
            "error": {
                "message": f"[HTTP {http_code}] invalid request payload",
                "type": "invalid_request_error",
            },
            "type": "error",
        }
        err = client._make_status_error(f"{body}", body=body, response=resp)
        assert err.status_code == 200  # sanity: same 200-stream trap, 4xx marker
        assert not should_retry_streaming_exception(err)


class TestRetryBudgetSpacing:
    """The retry budget must outlast a gateway 5xx outage, not just a blip.

    A Google/gateway 502 ("try again in 30 seconds") outlasts a tight 1-2-4s
    window, so a fast burst of retries just exhausts the budget before the
    upstream recovers. The default is 3 attempts spaced (5, 30)s: a quick first
    retry for instantaneous SSE blips, then a long gap that rides out the
    advertised ~30s outage before giving up.
    """

    def test_default_budget_is_spaced_out(self):
        import inspect

        from code_puppy.agents._runtime import streaming_retry

        params = inspect.signature(streaming_retry).parameters
        assert params["max_attempts"].default == 3
        assert tuple(params["delays"].default) == (5, 30)

    def test_runner_sleeps_the_spaced_delays_then_gives_up(self):
        # 3 attempts against a persistent transient error -> two sleeps (5, 30)
        # then re-raise. We patch asyncio.sleep so the test stays instant while
        # asserting the *real* runner uses the spaced-out delays.
        from unittest.mock import AsyncMock, patch

        from code_puppy.agents._runtime import streaming_retry

        attempts = {"n": 0}

        @streaming_retry()
        async def _always_transient():
            attempts["n"] += 1
            raise httpx.ConnectError("dropped socket")  # always retryable

        with patch(
            "code_puppy.agents._runtime.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            with pytest.raises(httpx.ConnectError):
                asyncio.run(_always_transient())

        assert attempts["n"] == 3  # all attempts consumed
        assert [c.args[0] for c in mock_sleep.await_args_list] == [5, 30]
