"""Tests for HMAC-based session file integrity protection."""

from __future__ import annotations

import pickle
import stat
from typing import Callable, List
from unittest.mock import patch

import pytest

from code_puppy.session_storage import (
    _HEADER_MAGIC,
    _HMAC_SIZE,
    _get_signing_key,
    load_session,
    save_session,
)


@pytest.fixture()
def history() -> List[str]:
    return ["hello", "world", "test"]


@pytest.fixture()
def token_estimator() -> Callable[[object], int]:
    return lambda msg: len(str(msg))


def _save(tmp_path, history, token_estimator, name="sess"):
    return save_session(
        history=history,
        session_name=name,
        base_dir=tmp_path,
        timestamp="2024-01-01T00:00:00",
        token_estimator=token_estimator,
    )


def test_save_load_roundtrip_with_hmac(tmp_path, history, token_estimator):
    """Save then load works and data round-trips correctly."""
    _save(tmp_path, history, token_estimator)
    loaded = load_session("sess", tmp_path)
    assert loaded == history

    # Verify file has the magic header
    raw = (tmp_path / "sess.pkl").read_bytes()
    assert raw.startswith(_HEADER_MAGIC)


def test_tampered_pickle_data_raises(tmp_path, history, token_estimator):
    """Modifying pickle bytes after signing raises ValueError."""
    meta = _save(tmp_path, history, token_estimator)
    raw = meta.pickle_path.read_bytes()

    # Flip a byte in the pickle data (after header + signature)
    offset = len(_HEADER_MAGIC) + _HMAC_SIZE
    tampered = raw[:offset] + bytes([raw[offset] ^ 0xFF]) + raw[offset + 1 :]
    meta.pickle_path.write_bytes(tampered)

    with pytest.raises(ValueError, match="HMAC verification failed"):
        load_session("sess", tmp_path)


def test_tampered_signature_raises(tmp_path, history, token_estimator):
    """Modifying HMAC bytes raises ValueError."""
    meta = _save(tmp_path, history, token_estimator)
    raw = meta.pickle_path.read_bytes()

    # Flip a byte in the signature
    sig_start = len(_HEADER_MAGIC)
    tampered = raw[:sig_start] + bytes([raw[sig_start] ^ 0xFF]) + raw[sig_start + 1 :]
    meta.pickle_path.write_bytes(tampered)

    with pytest.raises(ValueError, match="HMAC verification failed"):
        load_session("sess", tmp_path)


def test_legacy_unsigned_file_raises(tmp_path, history):
    """Raw pickle without HMAC header raises ValueError by default."""
    pkl_path = tmp_path / "legacy.pkl"
    pkl_path.write_bytes(pickle.dumps(history))

    with pytest.raises(ValueError, match="Unsigned session file"):
        load_session("legacy", tmp_path)


def test_legacy_unsigned_file_allow_legacy(tmp_path, history):
    """Legacy files load when allow_legacy=True."""
    pkl_path = tmp_path / "legacy.pkl"
    pkl_path.write_bytes(pickle.dumps(history))

    loaded = load_session("legacy", tmp_path, allow_legacy=True)
    assert loaded == history


def test_key_file_permissions(tmp_path):
    """Verify key file is created with 0o600 permissions."""
    with patch("code_puppy.session_storage.Path.home", return_value=tmp_path):
        # Directly test key creation logic
        kp = tmp_path / ".config" / "code_puppy" / ".session_key"
        # Remove if exists to force creation
        if kp.exists():
            kp.unlink()

        _get_signing_key()

        assert kp.exists()
        mode = kp.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600
