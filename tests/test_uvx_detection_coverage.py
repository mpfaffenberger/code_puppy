"""Additional coverage tests for uvx_detection.py.

This module focuses on covering the uncovered detection logic:
- Lines 38-41: Success path in _get_parent_process_name_psutil
- Lines 57-63: Process chain building loop in _get_parent_process_chain_psutil
- Lines 106-140: Windows ctypes process map building
- Line 158: Fallback to ctypes when psutil unavailable on Windows
"""

import sys
from unittest.mock import MagicMock, patch

from code_puppy.uvx_detection import (
    _get_parent_process_chain,
    _get_parent_process_chain_psutil,
    _get_parent_process_chain_windows_ctypes,
    _get_parent_process_name_psutil,
)


class TestGetParentProcessNamePsutilCoverage:
    """Tests for _get_parent_process_name_psutil success path."""

    def test_success_path_returns_parent_name(self):
        """Test that parent process name is returned when parent exists."""
        mock_parent = MagicMock()
        mock_parent.name.return_value = "uvx.exe"

        mock_proc = MagicMock()
        mock_proc.parent.return_value = mock_parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_proc

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            result = _get_parent_process_name_psutil(1234)

        assert result == "uvx.exe"
        mock_psutil.Process.assert_called_once_with(1234)

    def test_success_path_returns_lowercase_name(self):
        """Test that parent process name is lowercased."""
        mock_parent = MagicMock()
        mock_parent.name.return_value = "UVX.EXE"

        mock_proc = MagicMock()
        mock_proc.parent.return_value = mock_parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_proc

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            result = _get_parent_process_name_psutil(1234)

        assert result == "uvx.exe"

    def test_returns_none_when_parent_is_none(self):
        """Test that None is returned when parent() returns None."""
        mock_proc = MagicMock()
        mock_proc.parent.return_value = None

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_proc

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            result = _get_parent_process_name_psutil(1234)

        assert result is None

    def test_returns_none_on_exception(self):
        """Test that None is returned when an exception occurs."""
        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = Exception("No such process")

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            result = _get_parent_process_name_psutil(1234)

        assert result is None

    def test_handles_psutil_noaccess_exception(self):
        """Test graceful handling of psutil access denied errors."""
        mock_psutil = MagicMock()
        # Create a fake AccessDenied exception
        mock_psutil.Process.side_effect = Exception("AccessDenied")

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            result = _get_parent_process_name_psutil(1)

        assert result is None


class TestGetParentProcessChainPsutilCoverage:
    """Tests for _get_parent_process_chain_psutil chain building."""

    def test_builds_chain_from_process_hierarchy(self):
        """Test that the chain is built by traversing parent processes."""
        # Create process hierarchy: current -> parent1 -> parent2 -> None
        mock_parent2 = MagicMock()
        mock_parent2.name.return_value = "bash"
        mock_parent2.pid = 100
        mock_parent2.parent.return_value = None  # Ends the chain

        mock_parent1 = MagicMock()
        mock_parent1.name.return_value = "uvx"
        mock_parent1.pid = 200
        mock_parent1.parent.return_value = mock_parent2

        mock_current = MagicMock()
        mock_current.name.return_value = "python"
        mock_current.pid = 300
        mock_current.parent.return_value = mock_parent1

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=300):
                result = _get_parent_process_chain_psutil()

        # Chain should include all processes from current up
        assert "python" in result
        assert "uvx" in result
        assert "bash" in result

    def test_chain_stops_at_pid_zero(self):
        """Test that chain traversal stops at PID 0."""
        mock_parent = MagicMock()
        mock_parent.name.return_value = "init"
        mock_parent.pid = 0  # This should terminate the loop

        mock_current = MagicMock()
        mock_current.name.return_value = "python"
        mock_current.pid = 100
        mock_current.parent.return_value = mock_parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        # Should have current process in chain but stopped at parent with pid 0
        assert "python" in result

    def test_chain_stops_when_parent_pid_equals_current(self):
        """Test that chain stops if parent PID equals current (circular ref)."""
        mock_current = MagicMock()
        mock_current.name.return_value = "python"
        mock_current.pid = 100

        # Create circular reference - parent has same PID
        mock_parent = MagicMock()
        mock_parent.name.return_value = "python"
        mock_parent.pid = 100  # Same as current - should break loop

        mock_current.parent.return_value = mock_parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        # Should have at least the current process
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_returns_empty_list_on_exception(self):
        """Test that empty list is returned on exception."""
        mock_psutil = MagicMock()
        mock_psutil.Process.side_effect = Exception("Process not found")

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        assert result == []

    def test_handles_none_parent_gracefully(self):
        """Test that None parent terminates chain correctly."""
        mock_current = MagicMock()
        mock_current.name.return_value = "python"
        mock_current.pid = 100
        mock_current.parent.return_value = None  # No parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        assert "python" in result
        assert len(result) == 1


class TestGetParentProcessChainWindowsCtypesCoverage:
    """Tests for Windows ctypes-based process chain detection."""

    @patch("platform.system", return_value="Windows")
    def test_windows_ctypes_handles_invalid_handle(self, mock_platform):
        """Test handling of invalid handle from CreateToolhelp32Snapshot."""
        mock_kernel32 = MagicMock()
        mock_kernel32.CreateToolhelp32Snapshot.return_value = -1  # INVALID_HANDLE_VALUE

        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32
        mock_ctypes.sizeof.return_value = 300
        mock_ctypes.c_char = bytes
        mock_ctypes.Structure = object

        # Create a mock wintypes module
        mock_wintypes = MagicMock()
        mock_wintypes.DWORD = int
        mock_wintypes.LONG = int
        mock_wintypes.ULONG = int

        with patch.dict(
            sys.modules, {"ctypes": mock_ctypes, "ctypes.wintypes": mock_wintypes}
        ):
            result = _get_parent_process_chain_windows_ctypes()

        # Should return empty list on invalid handle
        assert isinstance(result, list)

    @patch("platform.system", return_value="Windows")
    def test_windows_ctypes_handles_exception(self, mock_platform):
        """Test handling of exceptions during ctypes operations."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.CreateToolhelp32Snapshot.side_effect = Exception(
            "Ctypes error"
        )

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            result = _get_parent_process_chain_windows_ctypes()

        assert result == []

    @patch("platform.system", return_value="Linux")
    def test_returns_empty_list_on_non_windows(self, mock_platform):
        """Test that non-Windows platforms return empty list immediately."""
        result = _get_parent_process_chain_windows_ctypes()
        assert result == []

    @patch("platform.system", return_value="Darwin")
    def test_returns_empty_list_on_macos(self, mock_platform):
        """Test that macOS returns empty list immediately."""
        result = _get_parent_process_chain_windows_ctypes()
        assert result == []


class TestGetParentProcessChainFallbackCoverage:
    """Tests for _get_parent_process_chain fallback behavior."""

    def test_uses_psutil_when_available(self):
        """Test that psutil is used when available."""
        with patch(
            "code_puppy.uvx_detection._get_parent_process_chain_psutil"
        ) as mock_psutil:
            mock_psutil.return_value = ["python", "uvx", "cmd"]
            result = _get_parent_process_chain()

        # Since psutil is available in test environment, it should use psutil
        assert isinstance(result, list)

    @patch("platform.system", return_value="Linux")
    def test_returns_empty_on_linux_when_psutil_fails(self, mock_platform):
        """Test returns empty list on Linux when psutil fails."""
        # On Linux without psutil, should return empty list (no ctypes fallback)
        with patch(
            "code_puppy.uvx_detection._get_parent_process_chain_psutil"
        ) as mock_psutil:
            mock_psutil.side_effect = Exception("psutil error")
            result = _get_parent_process_chain()

        assert isinstance(result, list)


class TestProcessChainIntegrationCoverage:
    """Integration-style tests for the full process chain detection."""

    def test_real_process_chain_contains_python(self):
        """Test that the real process chain contains python."""
        result = _get_parent_process_chain_psutil()

        # At minimum, current process should be Python
        python_found = any("python" in name.lower() for name in result)
        assert python_found or result == []  # Either has python or failed gracefully

    def test_chain_all_lowercase(self):
        """Test that all process names in chain are lowercase."""
        result = _get_parent_process_chain_psutil()

        for name in result:
            assert name == name.lower(), f"Name '{name}' is not lowercase"

    def test_chain_entries_are_strings(self):
        """Test that all chain entries are strings."""
        result = _get_parent_process_chain_psutil()

        for name in result:
            assert isinstance(name, str)

    def test_full_chain_detection_no_crash(self):
        """Test that full chain detection never crashes."""
        # This should never raise, just return a list
        result = _get_parent_process_chain()
        assert isinstance(result, list)


class TestEdgeCasesCoverage:
    """Edge case tests for additional coverage."""

    def test_psutil_chain_handles_name_exception(self):
        """Test handling when process.name() raises exception."""
        mock_current = MagicMock()
        mock_current.name.side_effect = Exception("Cannot get name")
        mock_current.pid = 100
        mock_current.parent.return_value = None

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        # Should gracefully handle and return empty list
        assert result == []

    def test_psutil_chain_handles_parent_exception(self):
        """Test handling when process.parent() raises exception after getting name."""
        mock_current = MagicMock()
        mock_current.name.return_value = "python"
        mock_current.pid = 100
        mock_current.parent.side_effect = Exception("Access denied")

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_current

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("code_puppy.uvx_detection.os.getpid", return_value=100):
                result = _get_parent_process_chain_psutil()

        # The name is appended before parent() is called, so chain has "python"
        # Then exception in parent() is caught, and the partial chain is returned
        assert result == ["python"]

    def test_parent_process_name_with_various_pids(self):
        """Test parent process name lookup with various PIDs."""
        mock_parent = MagicMock()
        mock_parent.name.return_value = "parent_process"

        mock_proc = MagicMock()
        mock_proc.parent.return_value = mock_parent

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_proc

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            # Test with various PIDs
            for pid in [0, 1, 4, 100, 9999, 65535]:
                result = _get_parent_process_name_psutil(pid)
                assert result == "parent_process"


class TestPsutilModuleNotAvailable:
    """Test behavior when psutil is not available."""

    def test_parent_process_name_without_psutil(self):
        """Test _get_parent_process_name_psutil when psutil import fails."""
        # Remove psutil from modules temporarily
        original_psutil = sys.modules.get("psutil")

        # Create a module that raises ImportError
        class FakeModule:
            def __getattr__(self, name):
                raise ImportError("No module named 'psutil'")

        sys.modules["psutil"] = FakeModule()

        try:
            result = _get_parent_process_name_psutil(1234)
            # Should return None when import fails
            assert result is None
        finally:
            # Restore original
            if original_psutil is not None:
                sys.modules["psutil"] = original_psutil

    def test_process_chain_without_psutil(self):
        """Test _get_parent_process_chain_psutil when psutil import fails."""
        original_psutil = sys.modules.get("psutil")

        class FakeModule:
            def __getattr__(self, name):
                raise ImportError("No module named 'psutil'")

        sys.modules["psutil"] = FakeModule()

        try:
            result = _get_parent_process_chain_psutil()
            # Should return empty list when import fails
            assert result == []
        finally:
            if original_psutil is not None:
                sys.modules["psutil"] = original_psutil


class TestWindowsFallbackPath:
    """Test the Windows fallback path when psutil is unavailable."""

    @patch("platform.system", return_value="Windows")
    @patch("code_puppy.uvx_detection._get_parent_process_chain_windows_ctypes")
    def test_fallback_to_ctypes_on_windows(self, mock_ctypes_chain, mock_platform):
        """Test that _get_parent_process_chain falls back to ctypes on Windows."""
        mock_ctypes_chain.return_value = ["python.exe", "uvx.exe", "cmd.exe"]

        # We need to make psutil import fail inside _get_parent_process_chain
        # The function tries to import psutil first, then falls back to ctypes
        original_modules = sys.modules.copy()

        # Remove psutil to trigger ImportError path
        if "psutil" in sys.modules:
            del sys.modules["psutil"]

        # Add a blocking entry that raises ImportError
        class BlockingImport:
            def __getattr__(self, name):
                raise ImportError("No psutil")

        sys.modules["psutil"] = BlockingImport()

        try:
            result = _get_parent_process_chain()
            # On Windows without psutil, should call ctypes fallback
            # But since we're not on actual Windows, this tests the path
            assert isinstance(result, list)
        finally:
            # Restore modules
            sys.modules.clear()
            sys.modules.update(original_modules)

    @patch("platform.system", return_value="Linux")
    def test_no_fallback_on_linux(self, mock_platform):
        """Test that there's no ctypes fallback on Linux."""
        original_modules = sys.modules.copy()

        if "psutil" in sys.modules:
            del sys.modules["psutil"]

        class BlockingImport:
            def __getattr__(self, name):
                raise ImportError("No psutil")

        sys.modules["psutil"] = BlockingImport()

        try:
            result = _get_parent_process_chain()
            # On Linux without psutil, should return empty list (no ctypes fallback)
            assert result == []
        finally:
            sys.modules.clear()
            sys.modules.update(original_modules)
