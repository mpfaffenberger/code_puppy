"""Tests for silencing Windows ProactorEventLoop WinError 10054 teardown noise."""

from __future__ import annotations

import sys
import types
from asyncio import proactor_events
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pytest

from code_puppy import main as main_module
from code_puppy.main import main_entry, quiet_windows_proactor_reset


class _DummySock:
    def __init__(
        self,
        *,
        shutdown_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.shutdown_error = shutdown_error
        self.close_error = close_error
        self.closed = False

    def fileno(self) -> int:
        return 123

    def shutdown(self, _how: int) -> None:
        if self.shutdown_error is not None:
            raise self.shutdown_error

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class _DummyProtocol:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error
        self.calls: list[BaseException | None] = []

    def connection_lost(self, exc: BaseException | None) -> None:
        self.calls.append(exc)
        if self.error is not None:
            raise self.error


class _DummyServer:
    def __init__(self) -> None:
        self.detached: list[object] = []

    def _detach(self, transport: object) -> None:
        self.detached.append(transport)


class _DummyTransport:
    def __init__(
        self,
        *,
        sock: _DummySock | None,
        protocol: _DummyProtocol,
        server: _DummyServer | None = None,
        called_connection_lost: bool = False,
    ) -> None:
        self._called_connection_lost = called_connection_lost
        self._sock = sock
        self._protocol = protocol
        self._server = server


def _win_reset_error(winerror: int = 10054) -> ConnectionResetError:
    err = ConnectionResetError(winerror, f"simulated winerror {winerror}")
    err.winerror = winerror
    return err


def _fake_call_connection_lost(
    transport: _DummyTransport, exc: BaseException | None
) -> None:
    if transport._called_connection_lost:
        return
    try:
        transport._protocol.connection_lost(exc)
    finally:
        if transport._sock is not None and transport._sock.fileno() != -1:
            transport._sock.shutdown(2)
        if transport._sock is not None:
            transport._sock.close()
        transport._sock = None
        if transport._server is not None:
            transport._server._detach(transport)
            transport._server = None
        transport._called_connection_lost = True


class _FakeTransportClass:
    _call_connection_lost = staticmethod(_fake_call_connection_lost)


def _patch_proactor(
    monkeypatch: pytest.MonkeyPatch,
    platform: str = "win32",
    transport_cls: type[object] = _FakeTransportClass,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(
        proactor_events,
        "_ProactorBasePipeTransport",
        transport_cls,
        raising=False,
    )


def test_suppresses_winerror_10054_on_shutdown_and_finishes_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch)
    sentinel = RuntimeError("peer closed")
    sock = _DummySock(shutdown_error=_win_reset_error())
    protocol = _DummyProtocol()
    server = _DummyServer()
    transport = _DummyTransport(sock=sock, protocol=protocol, server=server)

    with quiet_windows_proactor_reset():
        _FakeTransportClass._call_connection_lost(transport, sentinel)
        _FakeTransportClass._call_connection_lost(transport, sentinel)

    assert protocol.calls == [sentinel]
    assert sock.closed is True
    assert transport._sock is None
    assert server.detached == [transport]
    assert transport._server is None
    assert transport._called_connection_lost is True


def test_preserves_protocol_error_when_shutdown_also_resets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch)
    callback_error = RuntimeError("callback failed")
    sock = _DummySock(shutdown_error=_win_reset_error())
    protocol = _DummyProtocol(error=callback_error)
    server = _DummyServer()
    transport = _DummyTransport(sock=sock, protocol=protocol, server=server)

    with (
        quiet_windows_proactor_reset(),
        pytest.raises(RuntimeError, match="callback failed") as exc_info,
    ):
        _FakeTransportClass._call_connection_lost(transport, None)

    assert exc_info.value is callback_error
    assert sock.closed is True
    assert transport._sock is None
    assert server.detached == [transport]
    assert transport._server is None
    assert transport._called_connection_lost is True


def test_cleanup_continues_when_socket_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch)
    sock = _DummySock(
        shutdown_error=_win_reset_error(),
        close_error=OSError("close failed"),
    )
    server = _DummyServer()
    transport = _DummyTransport(sock=sock, protocol=_DummyProtocol(), server=server)

    with quiet_windows_proactor_reset():
        _FakeTransportClass._call_connection_lost(transport, None)

    assert sock.closed is True
    assert transport._sock is None
    assert server.detached == [transport]
    assert transport._server is None
    assert transport._called_connection_lost is True


def test_reraises_non_10054_connection_reset_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch)
    sock = _DummySock(shutdown_error=_win_reset_error(10053))
    transport = _DummyTransport(sock=sock, protocol=_DummyProtocol())

    with (
        quiet_windows_proactor_reset(),
        pytest.raises(ConnectionResetError) as exc_info,
    ):
        _FakeTransportClass._call_connection_lost(transport, None)

    assert exc_info.value.winerror == 10053


def test_reraises_winerror_10054_from_protocol_connection_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch)
    sock = _DummySock()
    transport = _DummyTransport(
        sock=sock,
        protocol=_DummyProtocol(error=_win_reset_error()),
    )

    with (
        quiet_windows_proactor_reset(),
        pytest.raises(ConnectionResetError) as exc_info,
    ):
        _FakeTransportClass._call_connection_lost(transport, None)

    assert exc_info.value.winerror == 10054
    assert sock.closed is True
    assert transport._called_connection_lost is True


def _plain_os_error_10054() -> OSError:
    err = OSError("plain oserror")
    err.winerror = 10054
    return err


@pytest.mark.parametrize(
    ("called_connection_lost", "has_sock", "error_factory"),
    [
        (True, True, lambda: _win_reset_error()),
        (False, False, lambda: _win_reset_error()),
        (False, True, _plain_os_error_10054),
    ],
)
def test_disqualifying_guard_conditions_reraise_without_recovery(
    monkeypatch: pytest.MonkeyPatch,
    called_connection_lost: bool,
    has_sock: bool,
    error_factory: object,
) -> None:
    make_err = cast(object, error_factory)
    assert callable(make_err)
    raised = cast(OSError, make_err())

    class _DirectRaiseTransport:
        @staticmethod
        def _call_connection_lost(
            _transport: _DummyTransport, _exc: BaseException | None
        ) -> None:
            raise raised

    _patch_proactor(monkeypatch, transport_cls=_DirectRaiseTransport)
    sock = _DummySock() if has_sock else None
    server = _DummyServer()
    transport = _DummyTransport(
        sock=sock,
        protocol=_DummyProtocol(),
        server=server,
        called_connection_lost=called_connection_lost,
    )

    with (
        quiet_windows_proactor_reset(),
        pytest.raises(OSError) as exc_info,
    ):
        _DirectRaiseTransport._call_connection_lost(transport, None)

    assert exc_info.value is raised
    assert server.detached == []
    assert transport._called_connection_lost is called_connection_lost
    if sock is not None:
        assert sock.closed is False
        assert transport._sock is sock


def test_restores_original_method_on_normal_and_exceptional_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FreshTransport:
        _call_connection_lost = staticmethod(_fake_call_connection_lost)

    _patch_proactor(monkeypatch, transport_cls=_FreshTransport)
    original = _FreshTransport._call_connection_lost

    with quiet_windows_proactor_reset():
        assert _FreshTransport._call_connection_lost is not original
    assert _FreshTransport._call_connection_lost is original

    with (
        pytest.raises(RuntimeError, match="body boom"),
        quiet_windows_proactor_reset(),
    ):
        assert _FreshTransport._call_connection_lost is not original
        raise RuntimeError("body boom")
    assert _FreshTransport._call_connection_lost is original


def test_noop_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proactor(monkeypatch, "linux")
    original = _FakeTransportClass._call_connection_lost

    with quiet_windows_proactor_reset():
        assert _FakeTransportClass._call_connection_lost is original


def test_handles_python_311_zero_arg_server_detach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ZeroArgServer:
        def __init__(self) -> None:
            self.detached_calls = 0

        def _detach(self) -> None:
            self.detached_calls += 1

    _patch_proactor(monkeypatch)
    sock = _DummySock(shutdown_error=_win_reset_error())
    server = _ZeroArgServer()
    transport = _DummyTransport(
        sock=sock,
        protocol=_DummyProtocol(),
        server=cast(_DummyServer, server),
    )

    with quiet_windows_proactor_reset():
        _FakeTransportClass._call_connection_lost(transport, None)

    assert sock.closed is True
    assert transport._sock is None
    assert server.detached_calls == 1
    assert transport._server is None
    assert transport._called_connection_lost is True


def test_main_entry_runs_with_windows_guard_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FreshTransport:
        _call_connection_lost = staticmethod(_fake_call_connection_lost)

    _patch_proactor(monkeypatch, transport_cls=_FreshTransport)
    original = _FreshTransport._call_connection_lost

    sock = _DummySock(shutdown_error=_win_reset_error())
    server = _DummyServer()
    transport = _DummyTransport(sock=sock, protocol=_DummyProtocol(), server=server)
    observed: dict[str, object] = {}

    class _FakeSplash:
        def __init__(self, *, enabled: bool) -> None:
            self.enabled = enabled
            self.started = False
            self.stopped = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    @contextmanager
    def _noop_logs() -> Iterator[None]:
        yield

    def _fake_run(*, splash: object) -> None:
        observed["splash"] = splash
        observed["patched_during_run"] = (
            _FreshTransport._call_connection_lost is not original
        )
        _FreshTransport._call_connection_lost(transport, None)

    monkeypatch.setattr(main_module, "_load_dotenv", lambda: None)
    monkeypatch.setattr(main_module, "_own_command", lambda _argv: None)
    monkeypatch.setattr(main_module, "splash_wanted", lambda _argv, _db: False)
    monkeypatch.setattr(main_module, "_migrate_legacy_setup", lambda: None)

    fake_distribution = types.ModuleType("code_puppy.distribution")
    fake_distribution.install_splash = lambda: None  # type: ignore[attr-defined]
    fake_distribution.install = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "code_puppy.distribution", fake_distribution)

    fake_pax = types.ModuleType("pydantic_ai_pax")
    fake_pax_ui = types.ModuleType("pydantic_ai_pax.ui")
    fake_pax_rendering = types.ModuleType("pydantic_ai_pax.ui.rendering")
    fake_pax_splash = types.ModuleType("pydantic_ai_pax.ui.rendering.splash")
    fake_pax_splash.Splash = _FakeSplash  # type: ignore[attr-defined]
    fake_pax_main = types.ModuleType("pydantic_ai_pax.__main__")
    fake_pax_main.quiet_telemetry_logs = _noop_logs  # type: ignore[attr-defined]
    fake_pax_cli_pkg = types.ModuleType("pydantic_ai_pax.cli")
    fake_pax_cli = types.ModuleType("pydantic_ai_pax.cli.cli")
    fake_pax_cli.run = _fake_run  # type: ignore[attr-defined]

    for mod_name, mod in (
        ("pydantic_ai_pax", fake_pax),
        ("pydantic_ai_pax.ui", fake_pax_ui),
        ("pydantic_ai_pax.ui.rendering", fake_pax_rendering),
        ("pydantic_ai_pax.ui.rendering.splash", fake_pax_splash),
        ("pydantic_ai_pax.__main__", fake_pax_main),
        ("pydantic_ai_pax.cli", fake_pax_cli_pkg),
        ("pydantic_ai_pax.cli.cli", fake_pax_cli),
    ):
        monkeypatch.setitem(sys.modules, mod_name, mod)

    main_entry()

    assert observed["patched_during_run"] is True
    assert sock.closed is True
    assert transport._sock is None
    assert server.detached == [transport]
    assert transport._called_connection_lost is True
    assert _FreshTransport._call_connection_lost is original
