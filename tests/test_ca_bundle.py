"""Tests for code_puppy.ca_bundle: one builder for public + corporate trust."""

from __future__ import annotations

import os
import shutil
import socket
import ssl
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlparse

import certifi
import pytest

from code_puppy import ca_bundle
from tests.tls_test_ca import (
    https_server,
    make_test_ca,
    minimal_child_env,
    verify_in_child,
)


@pytest.fixture
def cas(tmp_path, monkeypatch):
    public = make_test_ca(tmp_path, "Public")
    corporate = make_test_ca(tmp_path, "Corporate")
    monkeypatch.setattr(certifi, "where", lambda: str(public.ca_pem))
    return public, corporate


def _ders(cafile) -> set[bytes]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(cafile))
    return set(context.get_ca_certs(binary_form=True))


def _assert_default_client_policy(
    context: ssl.SSLContext, defaults: ssl.SSLContext
) -> None:
    assert context.protocol == ssl.PROTOCOL_TLS_CLIENT
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.minimum_version == defaults.minimum_version
    assert context.options == defaults.options
    assert context.verify_flags == defaults.verify_flags


def test_system_context_matches_runtime_secure_client_policy():
    _assert_default_client_policy(
        ca_bundle.system_trust_context(), ssl.create_default_context()
    )


def test_explicit_ca_context_matches_runtime_secure_client_policy(cas):
    public, _ = cas
    _assert_default_client_policy(
        ca_bundle.explicit_ca_context(str(public.ca_pem)),
        ssl.create_default_context(cafile=str(public.ca_pem)),
    )


def test_windows_roots_are_filtered_for_server_auth(monkeypatch):
    server_auth = ssl.Purpose.SERVER_AUTH.oid
    unrelated = {ssl.Purpose.CLIENT_AUTH.oid}

    def enum_certificates(store_name):
        if store_name == "CA":
            raise PermissionError("store denied")
        return [
            (b"unrestricted", "x509_asn", True),
            (b"server", "x509_asn", {server_auth}),
            (b"unrelated", "x509_asn", unrelated),
            (b"container", "pkcs_7_asn", True),
        ]

    monkeypatch.setattr(
        ca_bundle.ssl, "enum_certificates", enum_certificates, raising=False
    )
    context = mock.Mock()
    context.load_verify_locations.side_effect = [None, ssl.SSLError("malformed")]

    ca_bundle._load_windows_server_auth_roots(context)

    assert context.load_verify_locations.call_count == 2


def test_written_bundle_holds_public_and_corporate_roots(cas, tmp_path):
    public, corporate = cas
    destination = tmp_path / "nested" / "combined.pem"

    written = ca_bundle.write_public_and_corporate_bundle(
        str(corporate.ca_pem), str(destination)
    )

    written_path = Path(written)
    assert written_path.parent == destination.parent
    assert written_path.name.startswith("combined-")
    assert written_path.suffix == ".pem"
    assert len(written_path.stem.removeprefix("combined-")) == 64
    assert _ders(public.ca_pem) | _ders(corporate.ca_pem) <= _ders(written_path)
    assert ca_bundle.trusts_public_roots(written)


def test_exported_bundle_does_not_claim_lazy_system_capath_roots(cas, tmp_path):
    _, corporate = cas
    with mock.patch.object(
        ca_bundle,
        "system_trust_context",
        side_effect=AssertionError("export must use explicit roots only"),
    ):
        written = ca_bundle.write_public_and_corporate_bundle(
            str(corporate.ca_pem), str(tmp_path / "combined.pem")
        )

    assert Path(written).is_file()


def test_unchanged_bundle_is_not_rewritten(cas, tmp_path):
    _, corporate = cas
    destination = str(tmp_path / "combined.pem")
    ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), destination)

    with mock.patch.object(ca_bundle, "_atomic_write") as write:
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), destination)

    write.assert_not_called()


def test_invalid_corporate_bundle_raises(cas, tmp_path):
    garbage = tmp_path / "garbage.pem"
    garbage.write_text("not a certificate")
    with pytest.raises(ssl.SSLError):
        ca_bundle.write_public_and_corporate_bundle(
            str(garbage), str(tmp_path / "out.pem")
        )
    assert not (tmp_path / "out.pem").exists()


def test_active_ssl_cert_file_cannot_inject_roots(cas, tmp_path, monkeypatch):
    _, corporate = cas
    injected = make_test_ca(tmp_path, "Injected")
    monkeypatch.setenv("SSL_CERT_FILE", str(injected.ca_pem))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path))

    written = ca_bundle.write_public_and_corporate_bundle(
        str(corporate.ca_pem), str(tmp_path / "combined.pem")
    )

    assert _ders(injected.ca_pem).isdisjoint(_ders(written))


def _openssl_capath(cafile: Path, directory: Path) -> Path:
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl CLI is required to construct a hashed capath")
    result = subprocess.run(
        [openssl, "x509", "-in", str(cafile), "-noout", "-subject_hash"],
        check=True,
        capture_output=True,
        text=True,
    )
    directory.mkdir()
    shutil.copyfile(cafile, directory / f"{result.stdout.strip()}.0")
    return directory


def _tls_socket(context: ssl.SSLContext, url: str):
    parsed = urlparse(url)
    assert parsed.hostname is not None and parsed.port is not None
    raw = socket.create_connection((parsed.hostname, parsed.port), timeout=5)
    try:
        return context.wrap_socket(raw, server_hostname=parsed.hostname)
    except BaseException:
        raw.close()
        raise


def _assert_tls_rejected(context: ssl.SSLContext, url: str) -> None:
    with pytest.raises(ssl.SSLError):
        _tls_socket(context, url)


@pytest.mark.parametrize("environment_variable", ["SSL_CERT_FILE", "SSL_CERT_DIR"])
def test_ca_environment_cannot_inject_roots_into_contexts(
    cas, tmp_path, monkeypatch, environment_variable
):
    public, corporate = cas
    injected = make_test_ca(tmp_path, f"Injected {environment_variable}")
    injected_value = (
        str(injected.ca_pem)
        if environment_variable == "SSL_CERT_FILE"
        else str(_openssl_capath(injected.ca_pem, tmp_path / "injected-capath"))
    )
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setenv(environment_variable, injected_value)
    monkeypatch.setattr(
        ca_bundle.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(
            openssl_cafile=str(public.ca_pem),
            openssl_capath=None,
        ),
    )

    system = ca_bundle.system_trust_context()
    combined = ca_bundle.public_and_corporate_context(str(corporate.ca_pem))

    with https_server(injected) as injected_url:
        # Positive control: prove this Python/OpenSSL runtime recognizes the
        # environment value before proving our explicit contexts ignore it.
        with _tls_socket(ssl.create_default_context(), injected_url):
            pass
        _assert_tls_rejected(system, injected_url)
        _assert_tls_rejected(combined, injected_url)


def test_exported_bundle_verifies_public_and_corporate_in_child(cas, tmp_path):
    public, corporate = cas
    written = ca_bundle.write_public_and_corporate_bundle(
        str(corporate.ca_pem), str(tmp_path / "combined.pem")
    )
    with https_server(public) as public_url, https_server(corporate) as corporate_url:
        combined_result = verify_in_child(
            [public_url, corporate_url],
            {**minimal_child_env(), "SSL_CERT_FILE": written},
        )
        corporate_only_result = verify_in_child(
            [public_url],
            {**minimal_child_env(), "SSL_CERT_FILE": str(corporate.ca_pem)},
        )

    assert combined_result.returncode == 0, (
        combined_result.stdout + combined_result.stderr
    )
    assert corporate_only_result.returncode != 0


def test_internal_only_bundle_does_not_trust_public_roots(cas):
    _, corporate = cas
    assert ca_bundle.trusts_public_roots(str(corporate.ca_pem)) is False


def test_missing_bundle_does_not_trust_public_roots(tmp_path):
    assert ca_bundle.trusts_public_roots(str(tmp_path / "nope.pem")) is False


def test_content_address_keeps_previous_bundle_immutable(cas, tmp_path):
    _, corporate = cas
    destination = str(tmp_path / "combined.pem")
    first = ca_bundle.write_public_and_corporate_bundle(
        str(corporate.ca_pem), destination
    )
    first_content = Path(first).read_bytes()
    replacement = make_test_ca(tmp_path, "Replacement Corporate")

    second = ca_bundle.write_public_and_corporate_bundle(
        str(replacement.ca_pem), destination
    )

    assert second != first
    assert Path(first).read_bytes() == first_content
    assert Path(second).is_file()


def test_existing_symlink_is_rejected_without_clobbering_target(cas, tmp_path):
    _, corporate = cas
    requested = str(tmp_path / "combined.pem")
    written = Path(
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)
    )
    written.unlink()
    victim = tmp_path / "victim.txt"
    victim.write_text("leave me alone")
    try:
        written.symlink_to(victim)
    except OSError as exc:
        pytest.skip(f"real symlinks are unavailable in this environment: {exc}")

    with pytest.raises(OSError, match="not a regular file"):
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)

    assert victim.read_text() == "leave me alone"
    assert written.is_symlink()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are POSIX-only")
def test_existing_fifo_is_rejected_without_opening(cas, tmp_path):
    _, corporate = cas
    requested = str(tmp_path / "combined.pem")
    written = Path(
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)
    )
    written.unlink()
    os.mkfifo(written)

    with pytest.raises(OSError, match="not a regular file"):
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)


def test_existing_oversized_file_is_rejected_before_read(cas, tmp_path):
    _, corporate = cas
    requested = str(tmp_path / "combined.pem")
    written = Path(
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)
    )
    expected_size = written.stat().st_size
    written.write_bytes(b"x" * (expected_size + 1))

    with pytest.raises(OSError, match="unexpected size"):
        ca_bundle.write_public_and_corporate_bundle(str(corporate.ca_pem), requested)
