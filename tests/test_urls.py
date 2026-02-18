"""
Tests for code_puppy.plugins.walmart_specific.urls

Covers every public function and every Environment branch so that the
module hits 95%+ coverage.
"""

import pytest

from code_puppy.plugins.walmart_specific.urls import (
    BaseURLs,
    Environment,
    get_authentication_url,
    get_base_url,
    get_latest_version_url,
    get_models_url,
    get_safety_validation_url,
    get_setup_url,
    get_setup_windows_url,
    get_telemetry_url,
)


# ---------------------------------------------------------------------------
# get_base_url
# ---------------------------------------------------------------------------


class TestGetBaseUrl:
    def test_prod_is_default(self):
        assert get_base_url() == BaseURLs.PROD

    def test_prod_explicit(self):
        assert get_base_url(Environment.PROD) == BaseURLs.PROD

    def test_stage(self):
        assert get_base_url(Environment.STAGE) == BaseURLs.STAGE

    def test_dev(self):
        assert get_base_url(Environment.DEV) == BaseURLs.DEV

    def test_invalid_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            get_base_url("invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_models_url
# ---------------------------------------------------------------------------


class TestGetModelsUrl:
    def test_prod(self):
        url = get_models_url(Environment.PROD)
        assert url.startswith(BaseURLs.PROD)
        assert "/api/puppy-models/latest" in url

    def test_stage(self):
        url = get_models_url(Environment.STAGE)
        assert url.startswith(BaseURLs.STAGE)

    def test_dev(self):
        url = get_models_url(Environment.DEV)
        assert url.startswith(BaseURLs.DEV)


# ---------------------------------------------------------------------------
# get_authentication_url
# ---------------------------------------------------------------------------


class TestGetAuthenticationUrl:
    def test_no_port(self):
        url = get_authentication_url(environment=Environment.PROD)
        assert url.startswith(BaseURLs.PROD)
        assert "authenticate_puppy" in url
        assert "port" not in url

    def test_with_port(self):
        url = get_authentication_url(port=9000, environment=Environment.PROD)
        assert "port=9000" in url

    def test_stage(self):
        url = get_authentication_url(environment=Environment.STAGE)
        assert url.startswith(BaseURLs.STAGE)

    def test_dev(self):
        url = get_authentication_url(environment=Environment.DEV)
        assert url.startswith(BaseURLs.DEV)


# ---------------------------------------------------------------------------
# get_latest_version_url
# ---------------------------------------------------------------------------


class TestGetLatestVersionUrl:
    def test_defaults_to_stage(self):
        url = get_latest_version_url()
        assert url.startswith(BaseURLs.STAGE)
        assert "/api/releases/latest" in url

    def test_prod(self):
        url = get_latest_version_url(Environment.PROD)
        assert url.startswith(BaseURLs.PROD)

    def test_dev(self):
        url = get_latest_version_url(Environment.DEV)
        assert url.startswith(BaseURLs.DEV)


# ---------------------------------------------------------------------------
# get_setup_url  (Linux/macOS installer)
# ---------------------------------------------------------------------------


class TestGetSetupUrl:
    def test_defaults_to_stage(self):
        url = get_setup_url()
        assert url.startswith(BaseURLs.STAGE)
        assert "/api/releases/setup" in url

    def test_prod(self):
        url = get_setup_url(Environment.PROD)
        assert url.startswith(BaseURLs.PROD)

    def test_dev(self):
        url = get_setup_url(Environment.DEV)
        assert url.startswith(BaseURLs.DEV)


# ---------------------------------------------------------------------------
# get_setup_windows_url  (our new function)
# ---------------------------------------------------------------------------


class TestGetSetupWindowsUrl:
    """Tests for get_setup_windows_url — the function introduced in this PR."""

    def test_defaults_to_stage(self):
        url = get_setup_windows_url()
        assert url.startswith(BaseURLs.STAGE)
        assert "setup_windows.bat" in url

    def test_prod(self):
        url = get_setup_windows_url(Environment.PROD)
        assert url.startswith(BaseURLs.PROD)
        assert "setup_windows.bat" in url

    def test_dev(self):
        url = get_setup_windows_url(Environment.DEV)
        assert url.startswith(BaseURLs.DEV)

    def test_returns_string(self):
        assert isinstance(get_setup_windows_url(), str)

    def test_starts_with_https(self):
        assert get_setup_windows_url().startswith("https://")


# ---------------------------------------------------------------------------
# get_telemetry_url
# ---------------------------------------------------------------------------


class TestGetTelemetryUrl:
    def test_stage_default(self):
        url = get_telemetry_url()
        assert "stg" in url
        assert "telemetry" in url

    def test_prod(self):
        url = get_telemetry_url(Environment.PROD)
        assert "stg" not in url
        assert "dev" not in url
        assert "telemetry" in url

    def test_dev(self):
        url = get_telemetry_url(Environment.DEV)
        assert "dev" in url

    def test_invalid_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            get_telemetry_url("nope")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# get_safety_validation_url
# ---------------------------------------------------------------------------


class TestGetSafetyValidationUrl:
    def test_stage_default(self):
        url = get_safety_validation_url()
        assert "stg" in url
        assert "safety" in url

    def test_prod(self):
        url = get_safety_validation_url(Environment.PROD)
        assert "stg" not in url
        assert "dev" not in url
        assert "safety" in url

    def test_dev(self):
        url = get_safety_validation_url(Environment.DEV)
        assert "dev" in url

    def test_invalid_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            get_safety_validation_url("nope")  # type: ignore[arg-type]
