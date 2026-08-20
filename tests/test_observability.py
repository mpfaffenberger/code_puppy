"""Tests for opt-in Logfire wiring (code_puppy/observability.py)."""

import sys
import types
from unittest.mock import patch

from code_puppy import observability
from code_puppy.config import get_enable_logfire


class TestGetEnableLogfire:
    def test_defaults_to_false(self):
        with patch("code_puppy.config.get_value", return_value=None):
            assert get_enable_logfire() is False

    def test_truthy_values(self):
        for val in ("1", "true", "Yes", "ON"):
            with patch("code_puppy.config.get_value", return_value=val):
                assert get_enable_logfire() is True, val

    def test_falsy_values(self):
        for val in ("0", "false", "no", "off", "banana"):
            with patch("code_puppy.config.get_value", return_value=val):
                assert get_enable_logfire() is False, val


class TestLogfireOptedIn:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("CODE_PUPPY_ENABLE_LOGFIRE", "1")
        with patch("code_puppy.observability.get_enable_logfire", return_value=False):
            assert observability.logfire_opted_in() is True

    def test_falls_back_to_config(self, monkeypatch):
        monkeypatch.delenv("CODE_PUPPY_ENABLE_LOGFIRE", raising=False)
        with patch("code_puppy.observability.get_enable_logfire", return_value=True):
            assert observability.logfire_opted_in() is True

    def test_default_is_opted_out(self, monkeypatch):
        monkeypatch.delenv("CODE_PUPPY_ENABLE_LOGFIRE", raising=False)
        with patch("code_puppy.observability.get_enable_logfire", return_value=False):
            assert observability.logfire_opted_in() is False


class TestConfigureLogfire:
    def test_noop_when_opted_out(self):
        with patch("code_puppy.observability.logfire_opted_in", return_value=False):
            assert observability.configure_logfire() is False

    def test_missing_package_warns_and_fails_soft(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "logfire", None)  # import -> ImportError
        with (
            patch("code_puppy.observability.logfire_opted_in", return_value=True),
            patch("code_puppy.messaging.emit_warning") as warn,
        ):
            assert observability.configure_logfire() is False
        warn.assert_called_once()

    def test_configures_and_instruments(self, monkeypatch):
        fake = types.SimpleNamespace(configure=None, instrument_pydantic_ai=None)
        calls = {}
        fake.configure = lambda **kw: calls.setdefault("configure", kw)
        fake.instrument_pydantic_ai = lambda: calls.setdefault("instrumented", True)
        monkeypatch.setitem(sys.modules, "logfire", fake)
        with (
            patch("code_puppy.observability.logfire_opted_in", return_value=True),
            patch("code_puppy.messaging.emit_system_message"),
        ):
            assert observability.configure_logfire() is True
        assert calls["configure"]["send_to_logfire"] == "if-token-present"
        assert calls["configure"]["service_name"] == "code-puppy"
        assert calls["instrumented"] is True

    def test_configure_error_warns_and_fails_soft(self, monkeypatch):
        def boom(**_kw):
            raise RuntimeError("bad token")

        fake = types.SimpleNamespace(
            configure=boom, instrument_pydantic_ai=lambda: None
        )
        monkeypatch.setitem(sys.modules, "logfire", fake)
        with (
            patch("code_puppy.observability.logfire_opted_in", return_value=True),
            patch("code_puppy.messaging.emit_warning") as warn,
        ):
            assert observability.configure_logfire() is False
        warn.assert_called_once()
