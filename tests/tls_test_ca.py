"""Offline TLS fixtures: throwaway CAs, local HTTPS servers, child-process checks.

Lets CA-bundle tests prove real certificate verification (the same code path
``uv``/``pip``/MCP children take) without touching the network. Nothing here
ever disables verification -- the whole point is to prove it succeeds.
"""

from __future__ import annotations

import contextlib
import datetime
import http.server
import ipaddress
import os
import ssl
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@dataclass(frozen=True)
class ThrowawayCA:
    """A throwaway root CA plus one ``127.0.0.1`` server cert it signed."""

    ca_pem: Path
    server_cert_pem: Path
    server_key_pem: Path


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _write_pem(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def make_test_ca(directory: Path, label: str) -> ThrowawayCA:
    """Create a root CA named ``label`` and a server cert for 127.0.0.1."""
    now = datetime.datetime.now(datetime.UTC)
    validity = (now - datetime.timedelta(days=1), now + datetime.timedelta(days=1))

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(_name(f"{label} Root CA"))
        .issuer_name(_name(f"{label} Root CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(validity[0])
        .not_valid_after(validity[1])
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key = ec.generate_private_key(ec.SECP256R1())
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(_name(f"{label} server"))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(validity[0])
        .not_valid_after(validity[1])
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    slug = label.lower().replace(" ", "-")
    pem = serialization.Encoding.PEM
    return ThrowawayCA(
        ca_pem=_write_pem(directory / f"{slug}-ca.pem", ca_cert.public_bytes(pem)),
        server_cert_pem=_write_pem(
            directory / f"{slug}-server.pem", server_cert.public_bytes(pem)
        ),
        server_key_pem=_write_pem(
            directory / f"{slug}-server.key",
            server_key.private_bytes(
                pem,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ),
    )


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep pytest output quiet
        pass


@contextlib.contextmanager
def https_server(ca: ThrowawayCA) -> Iterator[str]:
    """Serve ``200 ok`` over TLS with ``ca``'s server cert; yield the URL."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ca.server_cert_pem, ca.server_key_pem)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _OkHandler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# Runs in a child process with urllib's default SSL context, exercising the
# same SSL_CERT_FILE path as a ``uv``/``pip``/MCP child. Platform-native stores
# and OpenSSL's default capath may contribute additional effective trust.
_CHILD_VERIFY_SCRIPT = """
import sys, urllib.request
failed = False
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for url in sys.argv[1:]:
    try:
        opener.open(url, timeout=5).read()
        print("OK", url)
    except Exception as exc:
        failed = True
        print("FAIL", url, type(exc).__name__, exc)
sys.exit(1 if failed else 0)
"""

_PROXY_VARS = (
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def verify_in_child(
    urls: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess:
    """GET every URL from a child process that uses ``env`` verbatim.

    Proxy variables are dropped so the child talks straight to 127.0.0.1.
    """
    child_env = {k: v for k, v in env.items() if k not in _PROXY_VARS}
    return subprocess.run(
        [sys.executable, "-c", _CHILD_VERIFY_SCRIPT, *urls],
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def minimal_child_env() -> dict[str, str]:
    """The bare env a stdio MCP child gets before our additions."""
    keep = ("PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP")
    return {k: os.environ[k] for k in keep if k in os.environ}
