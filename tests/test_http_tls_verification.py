"""Regression tests: TLS verification is never disabled implicitly.

Background: ``CODE_PUPPY_DISABLE_RETRY_TRANSPORT`` (a debugging switch for
the retry transport) also set ``verify = False``, silently turning off
certificate checking for *every* request -- API keys included. The variable
name says nothing about TLS, so a user enabling it to work around a retry
problem unknowingly downgraded transport security.
"""

import pytest

from code_puppy import http_utils


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """No proxy, no CA bundle, no leftover flags from the environment."""
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "CODE_PUPPY_DISABLE_RETRY_TRANSPORT",
        "CODE_PUPPY_INSECURE_SKIP_VERIFY",
    ):
        monkeypatch.delenv(name, raising=False)


class TestRetryTransportDoesNotDisableTls:
    def test_retry_switch_keeps_certificate_verification(self, monkeypatch):
        """The retry switch must not touch TLS verification."""
        monkeypatch.setenv("CODE_PUPPY_DISABLE_RETRY_TRANSPORT", "1")

        config = http_utils.resolve_proxy_config()

        assert config.disable_retry is True
        # verify must NOT be False -- that is what the bug was.
        assert config.verify is not False

    def test_retry_switch_keeps_an_explicit_verify_argument(self, monkeypatch):
        monkeypatch.setenv("CODE_PUPPY_DISABLE_RETRY_TRANSPORT", "1")

        config = http_utils.resolve_proxy_config(verify="/tmp/some-ca.pem")

        assert config.verify == "/tmp/some-ca.pem"

    def test_no_flags_keeps_verification_on(self):
        config = http_utils.resolve_proxy_config()

        assert config.disable_retry is False
        assert config.verify is not False


class TestInsecureOptIn:
    def test_explicit_opt_in_disables_verification(self, monkeypatch):
        monkeypatch.setenv("CODE_PUPPY_INSECURE_SKIP_VERIFY", "1")

        config = http_utils.resolve_proxy_config()

        assert config.verify is False

    def test_explicit_opt_in_warns_the_user(self, monkeypatch):
        """Silently downgrading TLS is the thing we are fixing."""
        monkeypatch.setenv("CODE_PUPPY_INSECURE_SKIP_VERIFY", "1")
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )
        monkeypatch.setattr(http_utils, "_INSECURE_SKIP_VERIFY_WARNED", False)

        http_utils.resolve_proxy_config()

        assert warnings, "the insecure opt-in must warn"
        assert "CODE_PUPPY_INSECURE_SKIP_VERIFY" in warnings[0]

    def test_the_warning_fires_only_once_per_process(self, monkeypatch):
        """The client factory runs per model -- one warning, not one per call."""
        monkeypatch.setenv("CODE_PUPPY_INSECURE_SKIP_VERIFY", "1")
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )
        monkeypatch.setattr(http_utils, "_INSECURE_SKIP_VERIFY_WARNED", False)

        http_utils.resolve_proxy_config()
        http_utils.resolve_proxy_config()
        http_utils.resolve_proxy_config()

        assert len(warnings) == 1

    def test_normal_configuration_does_not_warn(self, monkeypatch):
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )

        http_utils.resolve_proxy_config()

        assert not warnings


class TestMissingCertBundle:
    def test_missing_cert_file_warns(self, monkeypatch, tmp_path):
        """A configured-but-missing bundle is a misconfiguration, not a no-op."""
        missing = tmp_path / "nope.pem"
        monkeypatch.setenv("SSL_CERT_FILE", str(missing))
        monkeypatch.setattr(http_utils, "_MISSING_CERT_BUNDLE_WARNED", set())
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )

        http_utils.get_cert_bundle_path()

        assert warnings, "a missing CA bundle must be reported"
        assert "SSL_CERT_FILE" in warnings[0]

    def test_the_missing_bundle_warning_fires_once(self, monkeypatch, tmp_path):
        """The bundle is read per client build -- one warning, not one per build."""
        missing = tmp_path / "nope.pem"
        monkeypatch.setenv("SSL_CERT_FILE", str(missing))
        monkeypatch.setattr(http_utils, "_MISSING_CERT_BUNDLE_WARNED", set())
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )

        http_utils.get_cert_bundle_path()
        http_utils.get_cert_bundle_path()
        http_utils.get_cert_bundle_path()

        assert len(warnings) == 1

    def test_present_cert_file_does_not_warn(self, monkeypatch, tmp_path):
        bundle = tmp_path / "ca.pem"
        bundle.write_text("-----BEGIN CERTIFICATE-----\n")
        monkeypatch.setenv("SSL_CERT_FILE", str(bundle))
        monkeypatch.setenv("CODE_PUPPY_COMBINE_CA_BUNDLE", "false")
        warnings = []
        monkeypatch.setattr(
            http_utils,
            "emit_warning",
            lambda content, **kwargs: warnings.append(content),
        )

        http_utils.get_cert_bundle_path()

        assert not warnings
