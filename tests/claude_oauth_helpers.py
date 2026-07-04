"""Shared test stubs for Claude Code OAuth auth-retry test modules."""

from unittest.mock import Mock

CLOUDFLARE_400_TEXT = (
    "<html><head><title>400 Bad Request</title></head>"
    "<body><center><h1>400 Bad Request</h1></center>"
    "<hr><center>cloudflare</center></body></html>"
)


class StatusError(Exception):
    """Stand-in for anthropic APIStatusError / pydantic-ai ModelHTTPError."""

    def __init__(self, message: str, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class HttpxishError(Exception):
    """Stand-in for httpx.HTTPStatusError (status lives on .response)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = Mock(status_code=status_code)
