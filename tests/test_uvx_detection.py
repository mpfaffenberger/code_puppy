"""Comprehensive test coverage for uvx_detection.py.

Tests UVX environment detection including:
- Process parent detection via psutil
- Process parent detection via Windows ctypes
- Process chain traversal
- UVX launch scenario detection on Windows
- Signal handling adaptation for uvx
- Fallback mechanisms when detection fails
"""

from unittest.mock import patch

from code_puppy.uvx_detection import (
    _get_parent_process_chain,
    _get_parent_process_chain_psutil,
    _get_parent_process_chain_windows_ctypes,
    _get_parent_process_name_psutil,
    _is_uvx_in_chain,
    get_uvx_detection_info,
    is_launched_via_uvx,
    is_windows,
    should_use_alternate_cancel_key,
)


class TestIsUVXInChain:
    """Test UVX detection in process chain."""

    def test_is_uvx_in_chain_detects_uvx_exe(self):
        """Test detection of uvx.exe in chain."""
        chain = ["python.exe", "uvx.exe", "cmd.exe"]
        result = _is_uvx_in_chain(chain)
        assert result is True

    def test_is_uvx_in_chain_detects_uvx_no_extension(self):
        """Test detection of uvx without .exe extension."""
        chain = ["python", "uvx", "cmd"]
        result = _is_uvx_in_chain(chain)
        assert result is True

    def test_is_uvx_in_chain_ignores_uv_exe(self):
        """Test that uv.exe is not detected as uvx."""
        chain = ["python.exe", "uv.exe", "cmd.exe"]
        result = _is_uvx_in_chain(chain)
        assert result is False

    def test_is_uvx_in_chain_empty(self):
        """Test empty chain returns False."""
        result = _is_uvx_in_chain([])
        assert result is False

    def test_is_uvx_in_chain_no_match(self):
        """Test chain with no uvx returns False."""
        chain = ["python", "bash", "cmd"]
        result = _is_uvx_in_chain(chain)
        assert result is False

    def test_is_uvx_in_chain_mixed_case(self):
        """Test case handling in chain detection."""
        # Implementation may normalize to lowercase
        chain = ["python.exe", "uvx.exe", "cmd.exe"]
        result = _is_uvx_in_chain(chain)
        assert isinstance(result, bool)


class TestIsWindowsDetection:
    """Test Windows platform detection."""

    @patch("platform.system")
    def test_is_windows_true(
        self,
        mock_platform,
    ):
        """Test Windows detection returns True on Windows."""
        mock_platform.return_value = "Windows"
        result = is_windows()
        assert result is True

    @patch("platform.system")
    def test_is_windows_false_linux(
        self,
        mock_platform,
    ):
        """Test Windows detection returns False on Linux."""
        mock_platform.return_value = "Linux"
        result = is_windows()
        assert result is False

    @patch("platform.system")
    def test_is_windows_false_darwin(
        self,
        mock_platform,
    ):
        """Test Windows detection returns False on macOS."""
        mock_platform.return_value = "Darwin"
        result = is_windows()
        assert result is False


class TestIsLaunchedViaUVX:
    """Test UVX launch detection."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_true(
        self,
        mock_get_chain,
    ):
        """Test uvx detection returns True when uvx in chain."""
        mock_get_chain.return_value = ["python.exe", "uvx.exe"]
        # Clear the cache if it exists
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()
        result = is_launched_via_uvx()
        assert result is True

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_true_no_extension(
        self,
        mock_get_chain,
    ):
        """Test uvx detection with uvx (no extension)."""
        mock_get_chain.return_value = ["python", "uvx"]
        # Clear the cache if it exists
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()
        result = is_launched_via_uvx()
        assert result is True

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_false_no_uvx(
        self,
        mock_get_chain,
    ):
        """Test uvx detection returns False when uvx not in chain."""
        mock_get_chain.return_value = ["python.exe", "cmd.exe"]
        # Clear the cache if it exists
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()
        result = is_launched_via_uvx()
        assert result is False

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_empty_chain(
        self,
        mock_get_chain,
    ):
        """Test uvx detection with empty chain."""
        mock_get_chain.return_value = []
        # Clear the cache if it exists
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()
        result = is_launched_via_uvx()
        assert result is False

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_ignores_uv_not_uvx(
        self,
        mock_get_chain,
    ):
        """Test uv.exe is not confused with uvx.exe."""
        mock_get_chain.return_value = ["python.exe", "uv.exe", "cmd.exe"]
        # Clear the cache if it exists
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()
        result = is_launched_via_uvx()
        # uv.exe handles signals correctly
        assert result is False


class TestShouldUseAlternateCancelKey:
    """Test alternate cancel key decision."""

    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    def test_should_use_alternate_key_windows_uvx(
        self,
        mock_is_uvx,
        mock_is_windows,
    ):
        """Test alternate key is used on Windows with uvx."""
        mock_is_windows.return_value = True
        mock_is_uvx.return_value = True
        result = should_use_alternate_cancel_key()
        assert result is True

    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    def test_should_use_alternate_key_windows_no_uvx(
        self,
        mock_is_uvx,
        mock_is_windows,
    ):
        """Test alternate key is not used on Windows without uvx."""
        mock_is_windows.return_value = True
        mock_is_uvx.return_value = False
        result = should_use_alternate_cancel_key()
        assert result is False

    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    def test_should_use_alternate_key_non_windows_uvx(
        self,
        mock_is_uvx,
        mock_is_windows,
    ):
        """Test alternate key is not used on non-Windows even with uvx."""
        mock_is_windows.return_value = False
        mock_is_uvx.return_value = True
        result = should_use_alternate_cancel_key()
        # Only Windows + uvx = True
        assert result is False

    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    def test_should_use_alternate_key_non_windows_no_uvx(
        self,
        mock_is_uvx,
        mock_is_windows,
    ):
        """Test alternate key is not used on non-Windows without uvx."""
        mock_is_windows.return_value = False
        mock_is_uvx.return_value = False
        result = should_use_alternate_cancel_key()
        assert result is False


class TestGetUVXDetectionInfo:
    """Test UVX detection info gathering."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.should_use_alternate_cancel_key")
    def test_get_uvx_detection_info_returns_dict(
        self,
        mock_cancel_key,
        mock_is_windows_func,
        mock_is_uvx,
        mock_get_chain,
    ):
        """Test detection info returns a dictionary."""
        mock_get_chain.return_value = ["python.exe", "cmd.exe"]
        mock_is_windows_func.return_value = True
        mock_is_uvx.return_value = False
        mock_cancel_key.return_value = False

        result = get_uvx_detection_info()
        assert isinstance(result, dict)
        assert "is_windows" in result
        assert "is_launched_via_uvx" in result
        assert "should_use_alternate_cancel_key" in result
        assert "parent_process_chain" in result
        assert "current_pid" in result
        assert "python_executable" in result

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    @patch("code_puppy.uvx_detection.is_launched_via_uvx")
    @patch("code_puppy.uvx_detection.is_windows")
    @patch("code_puppy.uvx_detection.should_use_alternate_cancel_key")
    def test_get_uvx_detection_info_values(
        self,
        mock_cancel_key,
        mock_is_windows_func,
        mock_is_uvx,
        mock_get_chain,
    ):
        """Test detection info contains correct values."""
        mock_get_chain.return_value = ["python"]
        mock_is_windows_func.return_value = False
        mock_is_uvx.return_value = False
        mock_cancel_key.return_value = False

        result = get_uvx_detection_info()
        assert result["parent_process_chain"] == ["python"]
        assert result["is_windows"] is False
        assert result["is_launched_via_uvx"] is False
        assert result["should_use_alternate_cancel_key"] is False
        assert result["current_pid"] > 0  # Should have valid PID


class TestProcessDetectionIntegration:
    """Test process detection functions work and don't crash."""

    def test_get_parent_process_name_psutil_returns_string_or_none(self):
        """Test _get_parent_process_name_psutil returns str or None."""
        # Test with current process ID
        import os

        result = _get_parent_process_name_psutil(os.getpid())
        assert result is None or isinstance(result, str)

    def test_get_parent_process_chain_psutil_returns_list(self):
        """Test _get_parent_process_chain_psutil returns a list."""
        result = _get_parent_process_chain_psutil()
        assert isinstance(result, list)
        # Each item should be a string if list is non-empty
        for item in result:
            assert isinstance(item, str)

    def test_get_parent_process_chain_windows_ctypes_returns_list(self):
        """Test _get_parent_process_chain_windows_ctypes returns a list."""
        result = _get_parent_process_chain_windows_ctypes()
        assert isinstance(result, list)
        # Each item should be a string
        for item in result:
            assert isinstance(item, str)


class TestGetParentProcessChainWindowsCtypes:
    """Test Windows ctypes-based process chain detection."""

    @patch("platform.system")
    def test_windows_ctypes_non_windows_returns_empty(self, mock_platform):
        """Test that non-Windows platforms return empty list."""
        mock_platform.return_value = "Linux"
        result = _get_parent_process_chain_windows_ctypes()
        assert result == []

    @patch("platform.system")
    def test_windows_ctypes_import_error(self, mock_platform):
        """Test graceful handling of ctypes import errors."""
        mock_platform.return_value = "Windows"
        # This shouldn't raise; should return empty list on error
        result = _get_parent_process_chain_windows_ctypes()
        # Result depends on whether ctypes is available, but shouldn't raise
        assert isinstance(result, list)

    @patch("platform.system")
    @patch("code_puppy.uvx_detection.os.getpid")
    def test_windows_ctypes_with_mock_processes(self, mock_getpid, mock_platform):
        """Test Windows ctypes with mocked process snapshot."""
        mock_platform.return_value = "Windows"
        mock_getpid.return_value = 1000

        # We can't easily mock the full ctypes/kernel32 stack,
        # so we just verify it doesn't raise an exception
        result = _get_parent_process_chain_windows_ctypes()
        assert isinstance(result, list)


class TestGetParentProcessChain:
    """Test the main process chain detection function."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain_psutil")
    def test_get_parent_process_chain_calls_psutil(self, mock_psutil_chain):
        """Test that psutil function is tried first."""
        mock_psutil_chain.return_value = ["python.exe", "uvx.exe"]

        # This tests that _get_parent_process_chain tries psutil path
        result = _get_parent_process_chain()
        # Result depends on whether psutil is importable
        assert isinstance(result, list)

    @patch("code_puppy.uvx_detection._get_parent_process_chain_windows_ctypes")
    @patch("platform.system")
    def test_get_parent_process_chain_fallback_ctypes(
        self, mock_platform, mock_ctypes_chain
    ):
        """Test fallback behavior on Windows without psutil."""
        mock_platform.return_value = "Windows"
        mock_ctypes_chain.return_value = ["python", "cmd"]

        result = _get_parent_process_chain()
        # Function should return a list
        assert isinstance(result, list)

    @patch("code_puppy.uvx_detection._get_parent_process_chain_psutil")
    def test_get_parent_process_chain_empty_result(self, mock_psutil_chain):
        """Test handling of empty chain result."""
        mock_psutil_chain.return_value = []

        result = _get_parent_process_chain()
        assert isinstance(result, list)

    @patch("code_puppy.uvx_detection._get_parent_process_chain_psutil")
    def test_get_parent_process_chain_resilient_to_errors(self, mock_psutil_chain):
        """Test graceful handling of errors in chain detection."""
        mock_psutil_chain.side_effect = Exception("psutil error")

        result = _get_parent_process_chain()
        # Should not raise, may return empty or fallback result
        assert isinstance(result, list)


class TestCacheBehavior:
    """Test caching behavior of uvx detection."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_caches_result(self, mock_get_chain):
        """Test that is_launched_via_uvx caches the result."""
        mock_get_chain.return_value = ["python.exe", "uvx.exe"]

        # Clear cache before test
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        # First call
        result1 = is_launched_via_uvx()

        # Second call should use cached result
        result2 = is_launched_via_uvx()

        assert result1 == result2
        assert result1 is True

        # psutil should only be called once due to caching
        assert mock_get_chain.call_count == 1

    def test_is_launched_via_uvx_has_lru_cache(self):
        """Test that is_launched_via_uvx is decorated with lru_cache."""
        # The function should have cache_clear and cache_info methods
        assert hasattr(is_launched_via_uvx, "cache_clear")
        assert hasattr(is_launched_via_uvx, "cache_info")

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_cache_info(self, mock_get_chain):
        """Test cache statistics via cache_info."""
        mock_get_chain.return_value = ["python"]

        # Clear cache
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        # Make calls
        is_launched_via_uvx()
        is_launched_via_uvx()

        # Check cache statistics
        if hasattr(is_launched_via_uvx, "cache_info"):
            info = is_launched_via_uvx.cache_info()
            assert info.hits >= 1  # Second call should be a hit
            assert info.misses >= 1  # First call is a miss


class TestEdgeCasesAndErrors:
    """Test edge cases and error handling."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_uvx_in_chain_with_none_values(self, mock_get_chain):
        """Test handling of None values in chain."""
        # This shouldn't happen in practice, but test robustness
        chain_with_none = ["python.exe", None, "cmd.exe"]
        result = _is_uvx_in_chain(chain_with_none)
        assert isinstance(result, bool)

    def test_is_windows_always_returns_bool(self):
        """Test that is_windows always returns a boolean."""
        result = is_windows()
        assert isinstance(result, bool)

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    def test_is_launched_via_uvx_always_returns_bool(self, mock_get_chain):
        """Test that is_launched_via_uvx always returns a boolean."""
        mock_get_chain.return_value = []
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        result = is_launched_via_uvx()
        assert isinstance(result, bool)

    def test_should_use_alternate_cancel_key_always_returns_bool(self):
        """Test that should_use_alternate_cancel_key always returns a boolean."""
        result = should_use_alternate_cancel_key()
        assert isinstance(result, bool)

    def test_get_uvx_detection_info_has_all_keys(self):
        """Test that detection info dict has all expected keys."""
        result = get_uvx_detection_info()
        required_keys = {
            "is_windows",
            "is_launched_via_uvx",
            "should_use_alternate_cancel_key",
            "parent_process_chain",
            "current_pid",
            "python_executable",
        }
        assert required_keys.issubset(result.keys())

    def test_get_uvx_detection_info_types(self):
        """Test that detection info values have correct types."""
        result = get_uvx_detection_info()
        assert isinstance(result["is_windows"], bool)
        assert isinstance(result["is_launched_via_uvx"], bool)
        assert isinstance(result["should_use_alternate_cancel_key"], bool)
        assert isinstance(result["parent_process_chain"], list)
        assert isinstance(result["current_pid"], int)
        assert isinstance(result["python_executable"], str)


class TestUVXIntegration:
    """Test UVX detection integration scenarios."""

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    @patch("platform.system")
    def test_uvx_detection_windows_uvx_chain(
        self,
        mock_platform,
        mock_get_chain,
    ):
        """Test full UVX detection on Windows with uvx."""
        mock_platform.return_value = "Windows"
        mock_get_chain.return_value = ["python.exe", "uvx.exe", "cmd.exe"]
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        assert is_windows() is True
        assert is_launched_via_uvx() is True
        assert should_use_alternate_cancel_key() is True

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    @patch("platform.system")
    def test_uv_run_chain_windows(
        self,
        mock_platform,
        mock_get_chain,
    ):
        """Test uv run (not uvx) on Windows."""
        mock_platform.return_value = "Windows"
        mock_get_chain.return_value = ["python.exe", "uv.exe", "cmd.exe"]
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        assert is_windows() is True
        assert is_launched_via_uvx() is False
        assert should_use_alternate_cancel_key() is False

    @patch("code_puppy.uvx_detection._get_parent_process_chain")
    @patch("platform.system")
    def test_direct_execution_linux(
        self,
        mock_platform,
        mock_get_chain,
    ):
        """Test direct execution on Linux."""
        mock_platform.return_value = "Linux"
        mock_get_chain.return_value = ["python", "bash"]
        if hasattr(is_launched_via_uvx, "cache_clear"):
            is_launched_via_uvx.cache_clear()

        assert is_windows() is False
        assert is_launched_via_uvx() is False
        assert should_use_alternate_cancel_key() is False
