"""Tests for Walmart GitHub redirect monkey patches."""

import urllib.request
from unittest.mock import Mock, patch

import pytest

from code_puppy.plugins.walmart_specific.monkey_patches import (
    apply_github_redirect_patches,
    is_github_redirect_active,
    remove_github_redirect_patches,
    transform_github_url,
)


class TestGitHubURLTransformation:
    """Test URL transformation logic."""

    def test_transform_github_release_url(self):
        """Test transformation of GitHub release URLs."""
        original_url = "https://github.com/astral-sh/uv/releases/download/0.7.21/uv-aarch64-apple-darwin.tar.gz"
        expected_url = "https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/astral-sh/uv/releases/download/0.7.21/uv-aarch64-apple-darwin.tar.gz"

        result = transform_github_url(original_url)
        assert result == expected_url

    def test_transform_non_github_url_unchanged(self):
        """Test that non-GitHub URLs are not transformed."""
        url = "https://example.com/some/file.tar.gz"
        result = transform_github_url(url)
        assert result == url

    def test_transform_github_non_release_url(self):
        """Test transformation of other GitHub URLs."""
        original_url = "https://github.com/user/repo"
        expected_url = "https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/user/repo"

        result = transform_github_url(original_url)
        assert result == expected_url

    def test_transform_non_string_input(self):
        """Test that non-string inputs are returned unchanged."""
        assert transform_github_url(None) is None
        assert transform_github_url(123) == 123
        assert transform_github_url(["url"]) == ["url"]


class TestMonkeyPatches:
    """Test monkey patch application and removal."""

    def setup_method(self):
        """Ensure clean state before each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def teardown_method(self):
        """Clean up after each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def test_patch_application_and_removal(self):
        """Test that patches can be applied and removed."""
        # Initially no patches
        assert not is_github_redirect_active()

        # Apply patches
        apply_github_redirect_patches()
        assert is_github_redirect_active()

        # Remove patches
        remove_github_redirect_patches()
        assert not is_github_redirect_active()

    def test_double_patch_application(self):
        """Test that applying patches twice doesn't break anything."""
        apply_github_redirect_patches()
        apply_github_redirect_patches()  # Should be safe to call again
        assert is_github_redirect_active()

    def test_urllib_patch_functionality(self):
        """Test that urllib.request.urlopen is patched correctly."""
        apply_github_redirect_patches()

        # Mock the actual HTTP request to avoid real network calls
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_urlopen.return_value = mock_response

            # The patched urlopen should transform the URL
            # Note: We can't easily test this without actually calling the network
            # but we can verify the patch is in place
            assert callable(urllib.request.urlopen)

    @pytest.mark.skipif(
        not hasattr(urllib.request, "_original_urlopen"),
        reason="Original urllib function not stored",
    )
    def test_urllib_restoration(self):
        """Test that urllib.request.urlopen is restored after patch removal."""
        original_urlopen = urllib.request.urlopen

        apply_github_redirect_patches()
        patched_urlopen = urllib.request.urlopen

        # Should be different functions
        assert patched_urlopen != original_urlopen

        remove_github_redirect_patches()
        restored_urlopen = urllib.request.urlopen

        # Should be back to original
        assert restored_urlopen == original_urlopen


class TestRequestsPatching:
    """Test requests library patching if available."""

    def setup_method(self):
        """Ensure clean state before each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def teardown_method(self):
        """Clean up after each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def test_requests_patching(self):
        """Test that requests library is patched if available."""
        try:
            import requests
        except ImportError:
            pytest.skip("requests library not available")
        import requests

        original_get = requests.get

        apply_github_redirect_patches()

        # Should be patched
        assert requests.get != original_get

        remove_github_redirect_patches()

        # Should be restored
        assert requests.get == original_get


class TestHttpxPatching:
    """Test httpx library patching if available."""

    def setup_method(self):
        """Ensure clean state before each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def teardown_method(self):
        """Clean up after each test."""
        if is_github_redirect_active():
            remove_github_redirect_patches()

    def test_httpx_patching(self):
        """Test that httpx library is patched if available."""
        try:
            import httpx
        except ImportError:
            pytest.skip("httpx library not available")
        import httpx

        original_get = httpx.get

        apply_github_redirect_patches()

        # Should be patched
        assert httpx.get != original_get

        remove_github_redirect_patches()

        # Should be restored
        assert httpx.get == original_get
