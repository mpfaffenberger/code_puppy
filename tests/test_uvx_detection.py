"""
Tests for uvx launch detection on Windows.

These tests verify that code-puppy correctly detects when it was launched
via uvx on Windows and switches to Ctrl+K for agent cancellation.
"""

import os
import platform
from unittest.mock import patch

import pytest


class TestUvxDetection:
    """Tests for the uvx_detection module."""

    def test_is_windows_on_windows(self):
        """Test is_windows() returns True on Windows."""
        with patch("platform.system", return_value="Windows"):
            from code_puppy.uvx_detection import is_windows

            assert is_windows() is True

    def test_is_windows_on_linux(self):
        """Test is_windows() returns False on Linux."""
        with patch("platform.system", return_value="Linux"):
            from code_puppy.uvx_detection import is_windows

            assert is_windows() is False

    def test_is_windows_on_darwin(self):
        """Test is_windows() returns False on macOS."""
        with patch("platform.system", return_value="Darwin"):
            from code_puppy.uvx_detection import is_windows

            assert is_windows() is False

    def test_is_uvx_in_chain_with_uvx_exe(self):
        """Test _is_uvx_in_chain detects uvx.exe."""
        from code_puppy.uvx_detection import _is_uvx_in_chain

        chain = ["python.exe", "uvx.exe", "cmd.exe"]
        assert _is_uvx_in_chain(chain) is True

    def test_is_uvx_in_chain_with_uv_exe_only(self):
        """Test _is_uvx_in_chain does NOT detect uv.exe alone (only uvx.exe)."""
        from code_puppy.uvx_detection import _is_uvx_in_chain
        
        # uv.exe alone should NOT trigger detection - only uvx.exe has SIGINT issues
        chain = ["python.exe", "uv.exe", "powershell.exe"]
        assert _is_uvx_in_chain(chain) is False

    def test_is_uvx_in_chain_without_uvx(self):
        """Test _is_uvx_in_chain returns False when uvx is not present."""
        from code_puppy.uvx_detection import _is_uvx_in_chain

        chain = ["python.exe", "cmd.exe", "explorer.exe"]
        assert _is_uvx_in_chain(chain) is False

    def test_is_uvx_in_chain_empty(self):
        """Test _is_uvx_in_chain handles empty chain."""
        from code_puppy.uvx_detection import _is_uvx_in_chain

        assert _is_uvx_in_chain([]) is False

    def test_is_uvx_in_chain_with_uvx_no_extension(self):
        """Test _is_uvx_in_chain detects uvx without .exe extension."""
        from code_puppy.uvx_detection import _is_uvx_in_chain

        chain = ["python", "uvx", "bash"]
        assert _is_uvx_in_chain(chain) is True

    def test_should_use_alternate_cancel_key_windows_uvx(self):
        """Test should_use_alternate_cancel_key returns True on Windows + uvx."""
        with (
            patch("code_puppy.uvx_detection.is_windows", return_value=True),
            patch("code_puppy.uvx_detection.is_launched_via_uvx", return_value=True),
        ):
            # Clear the lru_cache to ensure fresh evaluation
            from code_puppy.uvx_detection import is_launched_via_uvx

            is_launched_via_uvx.cache_clear()

            # Re-import with mocks active
            import importlib
            import code_puppy.uvx_detection

            importlib.reload(code_puppy.uvx_detection)

            with (
                patch.object(code_puppy.uvx_detection, "is_windows", return_value=True),
                patch.object(
                    code_puppy.uvx_detection, "is_launched_via_uvx", return_value=True
                ),
            ):
                assert (
                    code_puppy.uvx_detection.should_use_alternate_cancel_key() is True
                )

    def test_should_use_alternate_cancel_key_windows_no_uvx(self):
        """Test should_use_alternate_cancel_key returns False on Windows without uvx."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        with (
            patch.object(code_puppy.uvx_detection, "is_windows", return_value=True),
            patch.object(
                code_puppy.uvx_detection, "is_launched_via_uvx", return_value=False
            ),
        ):
            assert code_puppy.uvx_detection.should_use_alternate_cancel_key() is False

    def test_should_use_alternate_cancel_key_linux_uvx(self):
        """Test should_use_alternate_cancel_key returns False on Linux even with uvx."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        with (
            patch.object(code_puppy.uvx_detection, "is_windows", return_value=False),
            patch.object(
                code_puppy.uvx_detection, "is_launched_via_uvx", return_value=True
            ),
        ):
            assert code_puppy.uvx_detection.should_use_alternate_cancel_key() is False

    def test_should_use_alternate_cancel_key_macos_uvx(self):
        """Test should_use_alternate_cancel_key returns False on macOS even with uvx."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        with (
            patch.object(code_puppy.uvx_detection, "is_windows", return_value=False),
            patch.object(
                code_puppy.uvx_detection, "is_launched_via_uvx", return_value=True
            ),
        ):
            assert code_puppy.uvx_detection.should_use_alternate_cancel_key() is False

    def test_get_uvx_detection_info_returns_dict(self):
        """Test get_uvx_detection_info returns proper structure."""
        from code_puppy.uvx_detection import get_uvx_detection_info

        info = get_uvx_detection_info()

        assert isinstance(info, dict)
        assert "is_windows" in info
        assert "is_launched_via_uvx" in info
        assert "should_use_alternate_cancel_key" in info
        assert "parent_process_chain" in info
        assert "current_pid" in info
        assert "python_executable" in info

        assert isinstance(info["is_windows"], bool)
        assert isinstance(info["is_launched_via_uvx"], bool)
        assert isinstance(info["should_use_alternate_cancel_key"], bool)
        assert isinstance(info["parent_process_chain"], list)
        assert isinstance(info["current_pid"], int)
        assert isinstance(info["python_executable"], str)

    def test_get_uvx_detection_info_current_pid_matches(self):
        """Test that current_pid in detection info matches os.getpid()."""
        from code_puppy.uvx_detection import get_uvx_detection_info

        info = get_uvx_detection_info()
        assert info["current_pid"] == os.getpid()


class TestParentProcessChainPsutil:
    """Tests for parent process chain detection using psutil."""

    def test_get_parent_process_chain_psutil_available(self):
        """Test parent chain detection when psutil is available."""
        # This test runs with actual psutil if installed
        try:
            import psutil  # noqa: F401
            from code_puppy.uvx_detection import _get_parent_process_chain_psutil

            chain = _get_parent_process_chain_psutil()

            # Should return a non-empty list including at least current process
            assert isinstance(chain, list)
            # The chain should contain python somewhere
            assert any("python" in name for name in chain)
        except ImportError:
            pytest.skip("psutil not installed")

    def test_get_parent_process_chain_psutil_error_handling(self):
        """Test that psutil chain detection handles errors gracefully."""
        with patch.dict("sys.modules", {"psutil": None}):
            from code_puppy.uvx_detection import _get_parent_process_chain_psutil

            # Should return empty list on error, not raise
            # (The mock will cause an AttributeError when accessing psutil.Process)
            result = _get_parent_process_chain_psutil()
            assert isinstance(result, list)


class TestParentProcessChainWindows:
    """Tests for Windows-specific parent process chain detection."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_get_parent_process_chain_windows_ctypes(self):
        """Test Windows ctypes-based parent chain detection."""
        from code_puppy.uvx_detection import _get_parent_process_chain_windows_ctypes

        chain = _get_parent_process_chain_windows_ctypes()

        # Should return a list
        assert isinstance(chain, list)
        # Chain should contain at least current process (python.exe)
        if chain:
            assert any("python" in name for name in chain)

    @pytest.mark.skipif(platform.system() == "Windows", reason="Non-Windows test")
    def test_get_parent_process_chain_windows_ctypes_on_non_windows(self):
        """Test that Windows ctypes chain returns empty on non-Windows."""
        from code_puppy.uvx_detection import _get_parent_process_chain_windows_ctypes

        chain = _get_parent_process_chain_windows_ctypes()
        assert chain == []


class TestKeymapIntegration:
    """Tests for keymap.py integration with uvx detection."""

    def test_keymap_returns_ctrl_k_on_windows_uvx(self):
        """Test that get_cancel_agent_key returns ctrl+k on Windows + uvx."""
        # Patch at the uvx_detection module level before keymap imports it
        with (
            patch(
                "code_puppy.uvx_detection.should_use_alternate_cancel_key",
                return_value=True,
            ),
        ):
            # Import fresh to pick up the mock
            import importlib
            import code_puppy.keymap

            importlib.reload(code_puppy.keymap)

            result = code_puppy.keymap.get_cancel_agent_key()
            assert result == "ctrl+k"

    def test_keymap_respects_config_when_not_uvx(self):
        """Test that get_cancel_agent_key respects config when not on Windows+uvx."""
        with (
            patch(
                "code_puppy.uvx_detection.should_use_alternate_cancel_key",
                return_value=False,
            ),
            patch("code_puppy.config.get_value", return_value="ctrl+q"),
        ):
            import importlib
            import code_puppy.keymap

            importlib.reload(code_puppy.keymap)

            result = code_puppy.keymap.get_cancel_agent_key()
            assert result == "ctrl+q"

    def test_keymap_returns_default_when_not_uvx_and_no_config(self):
        """Test that get_cancel_agent_key returns default when not uvx and no config."""
        with (
            patch(
                "code_puppy.uvx_detection.should_use_alternate_cancel_key",
                return_value=False,
            ),
            patch("code_puppy.config.get_value", return_value=None),
        ):
            import importlib
            import code_puppy.keymap

            importlib.reload(code_puppy.keymap)

            result = code_puppy.keymap.get_cancel_agent_key()
            assert result == "ctrl+c"  # DEFAULT_CANCEL_AGENT_KEY


class TestMockedProcessChain:
    """Tests using mocked process chains to simulate uvx scenarios."""

    def test_uvx_detection_with_mocked_chain(self):
        """Test uvx detection with a simulated uvx process chain."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        # Clear the LRU cache
        code_puppy.uvx_detection.is_launched_via_uvx.cache_clear()

        mock_chain = ["python.exe", "uvx.exe", "cmd.exe", "explorer.exe"]

        with patch.object(
            code_puppy.uvx_detection,
            "_get_parent_process_chain",
            return_value=mock_chain,
        ):
            result = code_puppy.uvx_detection.is_launched_via_uvx()
            assert result is True

    def test_no_uvx_detection_with_mocked_chain(self):
        """Test no uvx detection with a non-uvx process chain."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        # Clear the LRU cache
        code_puppy.uvx_detection.is_launched_via_uvx.cache_clear()

        mock_chain = ["python.exe", "cmd.exe", "explorer.exe"]

        with patch.object(
            code_puppy.uvx_detection,
            "_get_parent_process_chain",
            return_value=mock_chain,
        ):
            result = code_puppy.uvx_detection.is_launched_via_uvx()
            assert result is False

    def test_uvx_detection_caching(self):
        """Test that uvx detection result is cached."""
        import importlib
        import code_puppy.uvx_detection

        importlib.reload(code_puppy.uvx_detection)

        # Clear the LRU cache
        code_puppy.uvx_detection.is_launched_via_uvx.cache_clear()

        call_count = 0

        def counting_get_chain():
            nonlocal call_count
            call_count += 1
            return ["python.exe", "uvx.exe"]

        with patch.object(
            code_puppy.uvx_detection, "_get_parent_process_chain", counting_get_chain
        ):
            # First call
            result1 = code_puppy.uvx_detection.is_launched_via_uvx()
            # Second call - should use cache
            result2 = code_puppy.uvx_detection.is_launched_via_uvx()

            assert result1 is True
            assert result2 is True
            # Should only call the chain function once due to caching
            assert call_count == 1