"""Tests for puppy_share_tools module."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.walmart_specific.puppy_share_tools import (
    PuppyShareDeleteOutput,
    PuppyShareListOutput,
    PuppyShareUploadOutput,
    _get_puppy_token,
    _make_request,
    _open_url_in_browser,
    puppy_share_delete,
    puppy_share_list_my_pages,
    puppy_share_upload,
    puppy_share_upload_file,
    register_puppy_share_delete,
    register_puppy_share_list_my_pages,
    register_puppy_share_upload,
    register_puppy_share_upload_file,
)


# =============================================================================
# Token helpers
# =============================================================================


class TestGetPuppyToken:
    def test_reads_from_config_file(self, tmp_path):
        cfg_dir = tmp_path / ".code_puppy"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "puppy.cfg"
        cfg_file.write_text(
            "[puppy]\npuppy_token = tok-from-cfg\n"
        )
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.Path.home", return_value=tmp_path):
            assert _get_puppy_token() == "tok-from-cfg"

    def test_returns_none_when_config_missing(self, tmp_path):
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.Path.home", return_value=tmp_path):
            assert _get_puppy_token() is None


# =============================================================================
# _make_request
# =============================================================================


class TestMakeRequest:
    def test_successful_get(self):
        body = json.dumps({"ok": True}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _make_request("http://example.com/api")
        assert result == {"ok": True}

    def test_http_error_returns_error_dict(self):
        import urllib.error

        err_body = json.dumps({"detail": "Unauthorized"}).encode()
        exc = urllib.error.HTTPError(
            "http://x", 401, "Unauthorized", {}, None
        )
        exc.read = MagicMock(return_value=err_body)

        with patch("urllib.request.urlopen", side_effect=exc):
            result = _make_request("http://example.com/api")
        assert result["success"] is False
        assert "401" in result["error"]

    def test_generic_error_returns_error_dict(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=ConnectionError("refused"),
        ):
            result = _make_request("http://example.com/api")
        assert result["success"] is False
        assert "refused" in result["error"]


# =============================================================================
# _open_url_in_browser
# =============================================================================


class TestOpenUrlInBrowser:
    def test_opens_url_on_macos(self):
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.platform.system", return_value="Darwin"):
            with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.subprocess.Popen") as mock_popen:
                result = _open_url_in_browser("https://example.com")
                assert result is True
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                assert args[0] == "open"
                assert "https://example.com" in args

    def test_opens_url_on_windows(self):
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.platform.system", return_value="Windows"):
            with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.subprocess.Popen") as mock_popen:
                result = _open_url_in_browser("https://example.com")
                assert result is True
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                assert args[0] == "cmd"
                assert "/c" in args
                assert "start" in args

    def test_opens_url_on_linux(self):
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.platform.system", return_value="Linux"):
            with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.subprocess.Popen") as mock_popen:
                result = _open_url_in_browser("https://example.com")
                assert result is True
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                assert args[0] == "xdg-open"

    def test_returns_false_on_error(self):
        with patch("code_puppy.plugins.walmart_specific.puppy_share_tools.platform.system", side_effect=Exception("boom")):
            result = _open_url_in_browser("https://example.com")
            assert result is False


# =============================================================================
# Upload
# =============================================================================


class TestPuppyShareUpload:
    def test_no_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("puppy_token", raising=False)
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
            return_value=None,
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "test-page", open_in_browser=False)
        assert out.success is False
        assert "token" in out.error.lower()

    def test_successful_upload_uses_backend_url(self):
        """Test that we use the URL from the backend response, not construct our own."""
        api_response = {
            "success": True,
            "message": "Page created!",
            "url": "https://puppy.walmart.com/sharing/jsmith/my-dash",  # Backend URL with username
            "data": {
                "name": "my-dash",
                "business": "general",
                "version": 1,
                "action": "created",
                "url": "/sharing/jsmith/my-dash",
            },
        }
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="fake-token",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value=api_response,
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._open_url_in_browser",
                return_value=True,
            ) as mock_open,
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "my-dash")
        assert out.success is True
        assert out.version == 1
        # Should use the URL from backend response, which has the username
        assert out.url == "https://puppy.walmart.com/sharing/jsmith/my-dash"
        assert "jsmith" in out.url  # The username should be in the URL
        assert out.action == "created"
        # Browser should have been opened with the correct URL
        mock_open.assert_called_once_with("https://puppy.walmart.com/sharing/jsmith/my-dash")

    def test_upload_local_mode_uses_backend_url(self):
        """Test local mode also uses backend URL, not constructed URL."""
        api_response = {
            "success": True,
            "url": "http://localhost:8080/sharing/testuser/x",
            "data": {"name": "x", "business": "general", "version": 1, "url": "/sharing/testuser/x"},
        }
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value=api_response,
            ) as mock_req,
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._open_url_in_browser",
                return_value=True,
            ),
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "x", local=True, open_in_browser=False)
        assert out.success is True
        assert out.url == "http://localhost:8080/sharing/testuser/x"
        call_url = mock_req.call_args[0][0]
        assert "localhost:8080" in call_url

    def test_upload_failure(self):
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value={"success": False, "error": "boom"},
            ),
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "x", open_in_browser=False)
        assert out.success is False
        assert out.error == "boom"

    def test_open_in_browser_can_be_disabled(self):
        """Test that open_in_browser=False prevents browser from opening."""
        api_response = {
            "success": True,
            "url": "https://puppy.walmart.com/sharing/user/test",
            "data": {"name": "test", "business": "general", "version": 1},
        }
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value=api_response,
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._open_url_in_browser",
                return_value=True,
            ) as mock_open,
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "test", open_in_browser=False)
        assert out.success is True
        mock_open.assert_not_called()

    def test_fallback_url_when_backend_returns_none(self):
        """Test fallback URL construction when backend doesn't return url field."""
        api_response = {
            "success": True,
            "data": {
                "name": "test",
                "business": "general",
                "version": 1,
                "url": "/sharing/testuser/test",  # URL in data, not top-level
            },
        }
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value=api_response,
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._open_url_in_browser",
                return_value=True,
            ),
        ):
            out = puppy_share_upload("<h1>Hi</h1>", "test", open_in_browser=False)
        assert out.success is True
        # Should fall back to constructing URL from data.url
        assert "testuser" in out.url or "test" in out.url


# =============================================================================
# Upload File
# =============================================================================


class TestPuppyShareUploadFile:
    def test_missing_file(self, tmp_path):
        out = puppy_share_upload_file(
            str(tmp_path / "nope.html"), "test", open_in_browser=False
        )
        assert out.success is False
        assert "not found" in out.error.lower()

    def test_reads_file_and_delegates(self, tmp_path):
        html_file = tmp_path / "report.html"
        html_file.write_text("<h1>Report</h1>")

        with patch(
            "code_puppy.plugins.walmart_specific.puppy_share_tools.puppy_share_upload",
            return_value=PuppyShareUploadOutput(success=True, url="/sharing/general/rpt"),
        ) as mock_upload:
            out = puppy_share_upload_file(
                str(html_file), "rpt", business="general", open_in_browser=False
            )
        assert out.success is True
        mock_upload.assert_called_once()
        assert mock_upload.call_args.kwargs["html_content"] == "<h1>Report</h1>"
        assert mock_upload.call_args.kwargs["open_in_browser"] is False


# =============================================================================
# Delete
# =============================================================================


class TestPuppyShareDelete:
    def test_no_token(self):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
            return_value=None,
        ):
            out = puppy_share_delete("x")
        assert out.success is False

    def test_successful_delete(self):
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value={"success": True, "message": "Deleted!"},
            ),
        ):
            out = puppy_share_delete("x", "general")
        assert out.success is True
        assert out.message == "Deleted!"


# =============================================================================
# List My Pages
# =============================================================================


class TestPuppyShareListMyPages:
    def test_no_token(self):
        with patch(
            "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
            return_value=None,
        ):
            out = puppy_share_list_my_pages()
        assert out.success is False

    def test_returns_list_directly(self):
        pages = [{"name": "a"}, {"name": "b"}]
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value=pages,
            ),
        ):
            out = puppy_share_list_my_pages()
        assert out.success is True
        assert len(out.pages) == 2

    def test_returns_wrapped_object(self):
        with (
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._get_puppy_token",
                return_value="tok",
            ),
            patch(
                "code_puppy.plugins.walmart_specific.puppy_share_tools._make_request",
                return_value={"pages": [{"name": "z"}]},
            ),
        ):
            out = puppy_share_list_my_pages()
        assert out.success is True
        assert out.pages == [{"name": "z"}]


# =============================================================================
# URL helpers (quick smoke test)
# =============================================================================


class TestSharingURLs:
    def test_prod_urls(self):
        from code_puppy.plugins.walmart_specific.urls import (
            get_sharing_upload_url,
            get_sharing_page_view_url,
            get_sharing_svps_url,
        )

        assert "puppy.walmart.com" in get_sharing_upload_url()
        assert "puppy.walmart.com" in get_sharing_page_view_url("a", "b")
        assert "puppy.walmart.com" in get_sharing_svps_url()

    def test_local_urls(self):
        from code_puppy.plugins.walmart_specific.urls import (
            get_sharing_upload_url,
            get_sharing_page_view_url,
            get_sharing_svps_url,
        )

        assert "localhost" in get_sharing_upload_url(local=True)
        assert "localhost" in get_sharing_page_view_url("a", "b", local=True)
        assert "localhost" in get_sharing_svps_url(local=True)
