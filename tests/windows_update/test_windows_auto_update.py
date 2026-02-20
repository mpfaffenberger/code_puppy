"""
Tests for the Windows auto-update path in auto_update.py.

Focused on the three confirmed strict-win fixes:
  1. sys.exit(0) fires after subprocess — old process dies cleanly.
  2. Bat content uses get_setup_windows_url(), not a hardcoded string.
  3. Bat content uses proxy-aware curl flags (curl.exe -Lk --proxy-insecure).

Plus full coverage of fetch_latest_version() error paths (the Walmart-specific
one — distinct from version_checker.py's PyPI fetch which already has tests).

Strategy:
  - We are running ON Windows, so sys.platform == "win32" is naturally True;
    no platform-mocking needed for the Windows branch.
  - sys.exit is mocked to prevent the test process from actually exiting.
  - input() is mocked to simulate user responses without blocking.
  - subprocess.run is mocked — we verify call args, never spawn real processes.
  - The bat file IS written to a real temp path so we can inspect its contents.
  - emit_system_message is mocked to keep test output clean.
"""

from unittest.mock import MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "code_puppy.plugins.walmart_specific.auto_update"


def _mock_http_response(json_data, status_code=200):
    """Build a minimal httpx.Response-like mock."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# fetch_latest_version — the Walmart-specific one in auto_update.py
# ---------------------------------------------------------------------------


class TestFetchLatestVersion:
    """Tests for auto_update.fetch_latest_version (Walmart API, not PyPI)."""

    def _run(self, mock_response=None, side_effect=None):
        """Helper: patch create_client and call fetch_latest_version."""
        from code_puppy.plugins.walmart_specific.auto_update import fetch_latest_version

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        if side_effect:
            mock_client.get.side_effect = side_effect
        else:
            mock_client.get.return_value = mock_response

        with patch(f"{MODULE}.create_client", return_value=mock_client):
            return fetch_latest_version()

    def test_success_returns_normalised_version(self):
        """Happy path: API returns {success: true, data: {version: 'v1.2.3'}}."""
        resp = _mock_http_response({"success": True, "data": {"version": "v1.2.3"}})
        assert self._run(mock_response=resp) == "1.2.3"

    def test_success_strips_leading_v(self):
        """Version string normalisation strips the leading 'v'."""
        resp = _mock_http_response({"success": True, "data": {"version": "v0.0.99"}})
        assert self._run(mock_response=resp) == "0.0.99"

    def test_already_normalised_version_unchanged(self):
        """Version string without 'v' prefix is returned as-is."""
        resp = _mock_http_response({"success": True, "data": {"version": "1.2.3"}})
        assert self._run(mock_response=resp) == "1.2.3"

    def test_api_success_false_returns_none(self):
        """If success == False the function returns None, never raises."""
        resp = _mock_http_response({"success": False, "message": "not found"})
        assert self._run(mock_response=resp) is None

    def test_missing_version_key_returns_none(self):
        """Missing 'version' inside 'data' → None."""
        resp = _mock_http_response({"success": True, "data": {}})
        assert self._run(mock_response=resp) is None

    def test_missing_data_key_returns_none(self):
        """Missing 'data' entirely → None."""
        resp = _mock_http_response({"success": True})
        assert self._run(mock_response=resp) is None

    def test_timeout_returns_none(self):
        """Network timeout → None, never raises."""
        assert self._run(side_effect=httpx.TimeoutException("timed out")) is None

    def test_http_status_error_returns_none(self):
        """HTTP 5xx → None, never raises."""
        err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
        assert self._run(side_effect=err) is None

    def test_request_error_returns_none(self):
        """Connection error → None, never raises."""
        assert self._run(side_effect=httpx.RequestError("connection refused")) is None

    def test_invalid_json_returns_none(self):
        """Malformed JSON → None, never raises."""
        resp = _mock_http_response({})
        resp.json.side_effect = ValueError("bad json")
        assert self._run(mock_response=resp) is None

    def test_raise_for_status_raises_returns_none(self):
        """raise_for_status() throwing → None, never raises."""
        resp = _mock_http_response({})
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        assert self._run(mock_response=resp) is None


# ---------------------------------------------------------------------------
# urls.py — get_setup_windows_url
# ---------------------------------------------------------------------------


class TestGetSetupWindowsUrl:
    """The new helper we add to urls.py."""

    def test_function_exists_and_is_importable(self):
        """get_setup_windows_url must be importable from urls module."""
        from code_puppy.plugins.walmart_specific.urls import get_setup_windows_url  # noqa: F401

    def test_returns_string(self):
        from code_puppy.plugins.walmart_specific.urls import get_setup_windows_url

        assert isinstance(get_setup_windows_url(), str)

    def test_contains_correct_path(self):
        """URL must point to the setup_windows.bat endpoint."""
        from code_puppy.plugins.walmart_specific.urls import get_setup_windows_url

        url = get_setup_windows_url()
        assert "/api/releases/setup_windows.bat" in url

    def test_default_is_not_empty(self):
        from code_puppy.plugins.walmart_specific.urls import get_setup_windows_url

        assert get_setup_windows_url().startswith("https://")

    def test_stage_environment_contains_stg(self):
        """Stage environment URL contains 'stg'."""
        from code_puppy.plugins.walmart_specific.urls import (
            Environment,
            get_setup_windows_url,
        )

        assert "stg" in get_setup_windows_url(Environment.STAGE)

    def test_prod_environment_does_not_contain_stg(self):
        """Prod environment URL does NOT contain 'stg'."""
        from code_puppy.plugins.walmart_specific.urls import (
            Environment,
            get_setup_windows_url,
        )

        assert "stg" not in get_setup_windows_url(Environment.PROD)


# ---------------------------------------------------------------------------
# _handle_update — Windows path, strict-win fixes
# ---------------------------------------------------------------------------


class TestHandleUpdateWindowsPath:
    """
    Tests for the Windows branch of _handle_update.

    All tests run on the live sys.platform (win32) without mocking it.
    """

    def _run_handle_update(
        self,
        current_version="1.0.0",
        latest_version="2.0.0",
        user_input="y",
    ):
        """
        Run _handle_update with full mocking of I/O side effects.

        Returns a dict of the relevant mocks so tests can assert on them.
        """
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        mock_subprocess = MagicMock()
        mock_subprocess.return_value.returncode = 0

        with (
            patch(f"{MODULE}.fetch_latest_version", return_value=latest_version),
            patch(f"{MODULE}.emit_system_message"),
            patch("builtins.input", return_value=user_input),
            patch("sys.exit") as mock_exit,
            patch(f"{MODULE}.subprocess.run", mock_subprocess),
        ):
            _handle_update(current_version)

        return {
            "exit": mock_exit,
            "subprocess": mock_subprocess,
        }

    # --- Guard: no update needed ---

    def test_versions_equal_no_subprocess_no_exit(self):
        """When already up-to-date, nothing is launched and process lives on."""
        mocks = self._run_handle_update(
            current_version="2.0.0",
            latest_version="2.0.0",
        )
        mocks["subprocess"].assert_not_called()
        mocks["exit"].assert_not_called()

    def test_fetch_returns_none_no_subprocess_no_exit(self):
        """
        If the version API is unreachable, we must NOT attempt an update.
        The old code would fall-through and show 'update available: None'.
        """
        mocks = self._run_handle_update(
            current_version="1.0.0",
            latest_version=None,
        )
        mocks["subprocess"].assert_not_called()
        mocks["exit"].assert_not_called()

    # --- User declines ---

    def test_user_declines_no_subprocess_no_exit(self):
        """User types 'n' → no update launched, process keeps running."""
        mocks = self._run_handle_update(user_input="n")
        mocks["subprocess"].assert_not_called()
        mocks["exit"].assert_not_called()

    def test_user_declines_capital_N_no_subprocess(self):
        """User types 'N' (capital) → same as 'n'."""
        mocks = self._run_handle_update(user_input="N")
        mocks["subprocess"].assert_not_called()

    # --- FIX 1: sys.exit(0) fires on success ---

    def test_user_confirms_sys_exit_called(self):
        """
        STRICT WIN: After launching the update, sys.exit(0) must be called.
        The old process should die — not sleep 20 seconds and report failure.
        """
        mocks = self._run_handle_update(user_input="y")
        mocks["exit"].assert_called_once_with(0)

    def test_sys_exit_called_before_any_error_message(self):
        """
        STRICT WIN: The error-reporting block must never be reached on the
        happy path. We verify this by ensuring emit_system_message is NOT
        called with an error-flavoured argument after sys.exit fires.
        """
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        error_calls = []

        def capture_emit(msg, **kw):
            msg_str = str(msg)
            if "❌" in msg_str or "Update failed" in msg_str:
                error_calls.append(msg_str)

        with (
            patch(f"{MODULE}.fetch_latest_version", return_value="2.0.0"),
            patch(f"{MODULE}.emit_system_message", side_effect=capture_emit),
            patch("builtins.input", return_value="y"),
            patch("sys.exit"),
            patch(f"{MODULE}.subprocess.run"),
        ):
            _handle_update("1.0.0")

        assert error_calls == [], (
            f"Error message(s) emitted on the happy path: {error_calls}"
        )

    # --- FIX 2: bat content uses get_setup_windows_url(), not hardcoded string ---

    def test_bat_url_comes_from_get_setup_windows_url_not_hardcoded(self):
        """
        STRICT WIN: The bat URL must be dynamically sourced from
        get_setup_windows_url() — not a hardcoded string literal.

        We verify this by patching get_setup_windows_url to return a sentinel
        URL and asserting the sentinel appears in the bat content.  If the code
        used a hardcoded string, the sentinel would NOT appear.
        """
        SENTINEL_URL = (
            "https://puppy.sentinel-test.walmart.com/api/releases/setup_windows.bat"
        )

        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        written_content = []
        real_open = open

        def capturing_open(path, mode="r", **kwargs):
            fh = real_open(path, mode, **kwargs)
            if "update.bat" in str(path) and "w" in mode:
                original_write = fh.write

                def capturing_write(data):
                    written_content.append(data)
                    return original_write(data)

                fh.write = capturing_write
            return fh

        with (
            patch(f"{MODULE}.fetch_latest_version", return_value="2.0.0"),
            patch(f"{MODULE}.emit_system_message"),
            patch("builtins.input", return_value="y"),
            patch("sys.exit"),
            patch(f"{MODULE}.subprocess.run"),
            patch("builtins.open", side_effect=capturing_open),
            patch(f"{MODULE}.get_setup_windows_url", return_value=SENTINEL_URL),
        ):
            _handle_update("1.0.0")

        full_content = " ".join(written_content)
        assert SENTINEL_URL in full_content, (
            f"Sentinel URL not found — bat content is NOT using get_setup_windows_url(). "
            f"Content: {full_content!r}"
        )

    def test_bat_uses_setup_windows_url_from_urls_module(self):
        """
        STRICT WIN: The URL in the bat content must come from
        get_setup_windows_url(), making it architecturally correct.
        """
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update
        from code_puppy.plugins.walmart_specific.urls import get_setup_windows_url

        expected_url = get_setup_windows_url()
        written_content = []

        real_open = open

        def capturing_open(path, mode="r", **kwargs):
            fh = real_open(path, mode, **kwargs)
            if "update.bat" in str(path) and "w" in mode:
                original_write = fh.write

                def capturing_write(data):
                    written_content.append(data)
                    return original_write(data)

                fh.write = capturing_write
            return fh

        with (
            patch(f"{MODULE}.fetch_latest_version", return_value="2.0.0"),
            patch(f"{MODULE}.emit_system_message"),
            patch("builtins.input", return_value="y"),
            patch("sys.exit"),
            patch(f"{MODULE}.subprocess.run"),
            patch("builtins.open", side_effect=capturing_open),
        ):
            _handle_update("1.0.0")

        full_content = " ".join(written_content)
        assert expected_url in full_content, (
            f"Expected URL {expected_url!r} not found in bat. Content: {full_content!r}"
        )

    # --- FIX 3: bat content has proxy-aware curl flags ---

    def test_bat_contains_proxy_aware_curl_flags(self):
        """
        STRICT WIN: The bootstrap bat must use curl.exe -Lk --proxy-insecure
        so it works on Walmart networks without explicit proxy config.
        """
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        written_content = []

        real_open = open

        def capturing_open(path, mode="r", **kwargs):
            fh = real_open(path, mode, **kwargs)
            if "update.bat" in str(path) and "w" in mode:
                original_write = fh.write

                def capturing_write(data):
                    written_content.append(data)
                    return original_write(data)

                fh.write = capturing_write
            return fh

        with (
            patch(f"{MODULE}.fetch_latest_version", return_value="2.0.0"),
            patch(f"{MODULE}.emit_system_message"),
            patch("builtins.input", return_value="y"),
            patch("sys.exit"),
            patch(f"{MODULE}.subprocess.run"),
            patch("builtins.open", side_effect=capturing_open),
        ):
            _handle_update("1.0.0")

        full_content = " ".join(written_content)
        assert "--proxy-insecure" in full_content, (
            f"Proxy-insecure flag missing from bat. Content: {full_content!r}"
        )
        assert "curl.exe" in full_content or "curl" in full_content, (
            f"curl missing from bat. Content: {full_content!r}"
        )


# ---------------------------------------------------------------------------
# macOS / Linux update path
# ---------------------------------------------------------------------------


class TestHandleUpdateMacLinux:
    """Cover the non-Windows branch of _handle_update."""

    def _run_macos(
        self,
        curl_returncode: int = 0,
        bash_returncode: int = 0,
        latest_version: str = "2.0.0",
    ):
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        curl_result = MagicMock(
            returncode=curl_returncode, stdout="#!/bin/bash\necho ok", stderr=""
        )
        bash_result = MagicMock(returncode=bash_returncode)

        def fake_subprocess_run(cmd, **kwargs):
            if isinstance(cmd, list) and "curl" in cmd[0]:
                return curl_result
            return bash_result

        emitted = []
        with (
            patch(f"{MODULE}.fetch_latest_version", return_value=latest_version),
            patch(
                f"{MODULE}.emit_system_message",
                side_effect=lambda m, **k: emitted.append(str(m)),
            ),
            patch(f"{MODULE}.subprocess.run", side_effect=fake_subprocess_run),
            patch("sys.platform", "darwin"),
            patch("sys.exit") as mock_exit,
        ):
            _handle_update("1.0.0")

        return {"emitted": emitted, "exit": mock_exit}

    def test_successful_mac_update_calls_sys_exit(self):
        """Happy path on macOS: curl + bash succeed -> sys.exit(0)."""
        result = self._run_macos()
        result["exit"].assert_called_once_with(0)

    def test_successful_mac_update_emits_success_message(self):
        result = self._run_macos()
        combined = " ".join(result["emitted"])
        assert "successfully" in combined.lower() or "completed" in combined.lower()

    def test_curl_failure_no_sys_exit(self):
        """If curl fails, we bail without calling sys.exit."""
        result = self._run_macos(curl_returncode=1)
        result["exit"].assert_not_called()

    def test_curl_failure_emits_error(self):
        result = self._run_macos(curl_returncode=1)
        combined = " ".join(result["emitted"])
        assert (
            "failed" in combined.lower()
            or "error" in combined.lower()
            or "download" in combined.lower()
        )

    def test_bash_failure_no_sys_exit(self):
        """Curl works but bash script returns non-zero -> no sys.exit."""
        result = self._run_macos(bash_returncode=1)
        result["exit"].assert_not_called()

    def test_bash_failure_emits_error(self):
        result = self._run_macos(bash_returncode=1)
        combined = " ".join(result["emitted"])
        assert "failed" in combined.lower() or "error" in combined.lower()


# ---------------------------------------------------------------------------
# Exception handlers in _handle_update
# ---------------------------------------------------------------------------


class TestHandleUpdateExceptions:
    """Ensure TimeoutExpired and bare Exception are swallowed gracefully."""

    def _run_with_exception(self, exc, platform: str = "win32"):
        from code_puppy.plugins.walmart_specific.auto_update import _handle_update

        emitted = []
        with (
            patch(f"{MODULE}.fetch_latest_version", return_value="2.0.0"),
            patch(
                f"{MODULE}.emit_system_message",
                side_effect=lambda m, **k: emitted.append(str(m)),
            ),
            patch("builtins.input", return_value="y"),
            patch(f"{MODULE}.subprocess.run", side_effect=exc),
            patch("sys.platform", platform),
            patch("sys.exit"),
        ):
            _handle_update("1.0.0")

        return emitted

    def test_timeout_win32_emits_message(self):
        import subprocess as _sp

        emitted = self._run_with_exception(
            _sp.TimeoutExpired(cmd="update", timeout=30), "win32"
        )
        combined = " ".join(emitted)
        assert "timed out" in combined.lower() or "timeout" in combined.lower()

    def test_timeout_linux_emits_message(self):
        import subprocess as _sp

        emitted = self._run_with_exception(
            _sp.TimeoutExpired(cmd="update", timeout=30), "linux"
        )
        combined = " ".join(emitted)
        assert "timed out" in combined.lower() or "timeout" in combined.lower()

    def test_generic_exception_win32_emits_message(self):
        emitted = self._run_with_exception(RuntimeError("something broke"), "win32")
        combined = " ".join(emitted)
        assert "error" in combined.lower() or "unexpected" in combined.lower()

    def test_generic_exception_linux_emits_message(self):
        emitted = self._run_with_exception(RuntimeError("something broke"), "linux")
        combined = " ".join(emitted)
        assert "error" in combined.lower() or "unexpected" in combined.lower()
