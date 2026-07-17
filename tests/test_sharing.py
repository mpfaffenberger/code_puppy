import os
from unittest.mock import Mock, patch

import pytest

from code_puppy.sharing import export_session_html, redact_text, upload_session_html


def test_redacts_bearers_assignments_and_known_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MIST_TEST_API_KEY", "super-secret-value")
    text = "Authorization: Bearer abcdefghijkl api_key=plain-secret super-secret-value"

    redacted = redact_text(text)

    assert "abcdefghijkl" not in redacted
    assert "plain-secret" not in redacted
    assert os.environ["MIST_TEST_API_KEY"] not in redacted

    destination = export_session_html([{"content": text}], tmp_path / "share.html")
    assert "super-secret-value" not in destination.read_text(encoding="utf-8")


def test_hosted_share_requires_explicit_safe_endpoint():
    with pytest.raises(ValueError, match="HTTPS"):
        upload_session_html([], "http://example.com")

    response = Mock()
    response.json.return_value = {"url": "https://shares.example/session/1"}
    with patch("code_puppy.sharing.httpx.post", return_value=response) as post:
        url = upload_session_html([{"token": "abc"}], "https://shares.example/api")

    assert url == "https://shares.example/session/1"
    post.assert_called_once()
