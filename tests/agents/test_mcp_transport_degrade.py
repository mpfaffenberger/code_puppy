"""An unreachable HTTP/SSE MCP connector degrades the turn, never ends it.

HTTP/SSE connectors are dialed lazily, when the run task enters the combined
toolset. A 401 or a refused connection therefore surfaces mid-run as a raw
``httpx`` error rather than an ``McpError``, so it used to reach the generic
handler and abort the whole run over one dead connector.
"""

from __future__ import annotations

import httpcore
import httpx
import pytest
from pydantic_ai.exceptions import ModelHTTPError

from code_puppy.agents._runtime import (
    _collect_exceptions,
    _is_mcp_transport_failure,
)


def _status_error(code: int) -> httpx.HTTPStatusError:
    """The shape raised when a connector answers 401/5xx during connect."""
    request = httpx.Request("POST", "https://mcp.example/sse")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"{code}", request=request, response=response)


@pytest.mark.parametrize(
    "exc",
    [
        _status_error(401),
        _status_error(503),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
        httpx.PoolTimeout("pool timeout"),
        httpcore.ConnectError("refused"),
        httpcore.ConnectTimeout("timed out"),
    ],
    ids=["401", "503", "refused", "read-timeout", "pool-timeout", "core", "core-to"],
)
def test_transport_failures_are_degradable(exc: BaseException) -> None:
    assert _is_mcp_transport_failure(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("a real bug"),
        RuntimeError("a real bug"),
        ModelHTTPError(status_code=500, model_name="m", body=None),
    ],
    ids=["value-error", "runtime-error", "model-http-error"],
)
def test_genuine_failures_still_propagate(exc: BaseException) -> None:
    """A real bug, and a model-side failure, must stay fatal.

    ``ModelHTTPError`` is the important one: the model itself failing is not
    a degraded connector, and it is not an ``httpx`` error either.
    """
    assert _is_mcp_transport_failure(exc) is False


def test_mixed_group_degrades_only_the_connector() -> None:
    """A dead connector alongside a real bug must not hide the real bug."""
    connector = _status_error(401)
    real_bug = ValueError("a real bug")
    group = BaseExceptionGroup("run failed", [connector, real_bug])

    leaves = _collect_exceptions(group, lambda e: True)
    degraded = [e for e in leaves if _is_mcp_transport_failure(e)]
    fatal = [e for e in leaves if not _is_mcp_transport_failure(e)]

    assert degraded == [connector]
    assert fatal == [real_bug]
