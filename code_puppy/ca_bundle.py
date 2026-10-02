"""Build public + corporate CA trust without disabling verification.

In-memory contexts combine environment-independent system trust, certifi, and
an optional corporate bundle. Exported PEM files contain only the enumerable
certifi and corporate roots. System ``capath`` entries are intentionally not
promised in exported files because OpenSSL loads them lazily and cannot
reliably enumerate them before a handshake. On macOS, OpenSSL contexts also do
not automatically inherit roots installed only in the system Keychain; callers
must supply those roots explicitly as ``corporate_bundle``.

The module deliberately depends only on the standard library and certifi so it
is safe to import in early-startup and lightweight client code. The public
context builders and root-subset check are shared APIs for setup/diagnostic
plugins: they inspect effective trust without mutating process environment.
The exporter is the file-based counterpart used by HTTP/MCP runtime clients.
"""

from __future__ import annotations

import hashlib
import os
import re
import ssl
import stat
import sys
import tempfile
from pathlib import Path

import certifi

from code_puppy.atomic_io import ContentTooLarge, read_bounded_bytes


def _load_windows_server_auth_roots(context: ssl.SSLContext) -> None:
    """Load Windows roots with the same server-auth filtering as stdlib SSL."""
    enum_certificates = getattr(ssl, "enum_certificates", None)
    if enum_certificates is None:
        return

    server_auth_oid = ssl.Purpose.SERVER_AUTH.oid
    for store_name in ("CA", "ROOT"):
        try:
            certificates = enum_certificates(store_name)
        except PermissionError:
            continue
        for certificate, encoding, trust in certificates:
            if encoding != "x509_asn":
                continue
            if trust is not True and server_auth_oid not in trust:
                continue
            try:
                context.load_verify_locations(
                    cadata=ssl.DER_cert_to_PEM_cert(certificate)
                )
            except (ssl.SSLError, ValueError):
                continue


def _secure_client_context() -> ssl.SSLContext:
    """Create a client context matching supported Python runtime policy."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # CPython 3.13 added these to create_default_context(). Mirror them here
    # because calling it without a cafile would read SSL_CERT_* overrides.
    if sys.version_info >= (3, 13):
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        context.verify_flags |= ssl.VERIFY_X509_STRICT
    return context


def explicit_ca_context(cafile: str) -> ssl.SSLContext:
    """Build default-policy client trust from exactly one explicit CA file."""
    # Passing an explicit cafile prevents create_default_context() from loading
    # environment-selected defaults while preserving the runtime's TLS policy.
    return ssl.create_default_context(cafile=cafile)


def system_trust_context() -> ssl.SSLContext:
    """Build system trust without consulting CA environment overrides."""
    context = _secure_client_context()

    # OpenSSL exposes its compiled-in file/directory separately from the env
    # override names. Load only those explicit defaults.
    defaults = ssl.get_default_verify_paths()
    if defaults.openssl_cafile and Path(defaults.openssl_cafile).is_file():
        context.load_verify_locations(cafile=defaults.openssl_cafile)
    if defaults.openssl_capath and Path(defaults.openssl_capath).is_dir():
        context.load_verify_locations(capath=defaults.openssl_capath)

    # Windows' native roots are not represented by OpenSSL's paths.
    _load_windows_server_auth_roots(context)
    return context


def public_and_corporate_context(
    corporate_bundle: str | None = None,
) -> ssl.SSLContext:
    """Return system + certifi trust, plus ``corporate_bundle``.

    Trust sources are loaded explicitly so active CA environment overrides do
    not inject arbitrary roots.
    """
    context = system_trust_context()
    context.load_verify_locations(cafile=certifi.where())
    if corporate_bundle:
        context.load_verify_locations(cafile=corporate_bundle)
    return context


def _content_addressed_path(destination: str, content: bytes) -> Path:
    """Return an immutable sibling path derived from ``content``."""
    requested = Path(destination)
    digest = hashlib.sha256(content).hexdigest()
    return requested.with_name(f"{requested.stem}-{digest}{requested.suffix}")


def _read_regular_file(path: Path, expected_size: int) -> bytes | None:
    """Read an existing regular file without following symlinks or blocking."""
    try:
        file_info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(file_info.st_mode):
        raise OSError(f"CA bundle destination is not a regular file: {path}")
    if file_info.st_size != expected_size:
        raise OSError(f"Content-addressed CA bundle has unexpected size: {path}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as existing:
        opened_info = os.fstat(existing.fileno())
        if not stat.S_ISREG(opened_info.st_mode):
            raise OSError(f"CA bundle destination changed file type: {path}")
        return existing.read(expected_size + 1)


def _atomic_write(path: Path, content: bytes) -> None:
    """Atomically install ``content`` without resolving a destination symlink."""
    # atomic_io resolves realpath(), which would follow destination symlinks.
    # Keep this path-preserving writer and private directory creation here.
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def write_public_and_corporate_bundle(corporate_bundle: str, destination: str) -> str:
    """Write trusted roots to an immutable, content-addressed PEM file.

    ``destination`` supplies the parent, stem, and suffix. Its directory must
    be application-private and protected from modification by other principals;
    portable path APIs cannot guarantee immutability inside a hostile directory.
    The returned path includes a SHA-256 digest, so cooperative concurrent
    application versions cannot replace a bundle already exported by another
    running process. Existing final-component special files and unexpected
    content fail closed.
    """
    # Export only enumerable, explicit sources. OpenSSL capath roots are loaded
    # lazily, so claiming they are faithfully serializable would be fiction.
    # Preserve certificate PEMs rather than enumerating get_ca_certs(), which
    # silently filters pinned CA:FALSE leaves. Export certificates only: a
    # configured file may also contain private keys that must not be copied.
    certificate_blocks = []
    seen_certificates: set[bytes] = set()
    for source in (certifi.where(), corporate_bundle):
        # Validate the original file, not just extracted blocks: malformed PEM
        # trailers must fail rather than being silently sanitized.
        try:
            content = read_bounded_bytes(source)
        except ContentTooLarge as exc:
            raise OSError("CA source exceeds the bounded-read limit") from exc
        explicit_ca_context(source)
        if b"-----BEGIN TRUSTED CERTIFICATE-----" in content:
            # X509_AUX trust/reject metadata must not be lost in a PEM rewrite.
            # Let the resolver fall back to this original OpenSSL trust file.
            raise ssl.SSLError(
                "OpenSSL trusted-certificate metadata requires the original CA file"
            )
        blocks = re.findall(
            rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            content,
            flags=re.DOTALL,
        )
        source_pem = b"\n".join(blocks) + b"\n"
        context = _secure_client_context()
        try:
            context.load_verify_locations(cadata=source_pem.decode("ascii"))
        except (ValueError, UnicodeError) as exc:
            raise ssl.SSLError("CA source contains no valid certificate PEMs") from exc
        for block in blocks:
            # Deduplicate DER payloads despite PEM wrapping differences, while
            # retaining the first block verbatim (including CA:FALSE anchors).
            payload = ssl.PEM_cert_to_DER_cert(block.decode("ascii"))
            if payload not in seen_certificates:
                seen_certificates.add(payload)
                certificate_blocks.append(block + b"\n")
    pem = b"\n".join(certificate_blocks)
    output_path = _content_addressed_path(destination, pem)
    # Do not reap older digests here: callers may have persisted one of those
    # immutable paths in their environment. The files are intentionally small.
    existing = _read_regular_file(output_path, len(pem))
    if existing is None:
        _atomic_write(output_path, pem)
    elif existing != pem:
        raise OSError(
            f"Content-addressed CA bundle has unexpected content: {output_path}"
        )
    return str(output_path)


def trusts_public_roots(cafile: str) -> bool:
    """True if roots loaded from ``cafile`` include every certifi root.

    This checks the file's contents, not a process's complete effective trust;
    OpenSSL capath entries or platform-native stores may add other roots. An
    internal-only file still fails this required public-root subset check.
    """
    try:
        candidate = explicit_ca_context(cafile)
    except (OSError, ssl.SSLError):
        return False
    public = explicit_ca_context(certifi.where())
    return set(public.get_ca_certs(binary_form=True)) <= set(
        candidate.get_ca_certs(binary_form=True)
    )
