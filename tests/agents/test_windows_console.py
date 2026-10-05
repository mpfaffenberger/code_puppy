"""Bulk VT console input: bounded native reads, no per-character polling."""

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from code_puppy.agents import _windows_console as console


@pytest.fixture
def kernel(monkeypatch):
    def mode(handle, result):
        result._obj.value = 0x0200
        return True

    def count(handle, result):
        result._obj.value = 100_000
        return True

    api = SimpleNamespace(
        GetStdHandle=Mock(return_value=123),
        GetConsoleMode=Mock(side_effect=mode),
        GetNumberOfConsoleInputEvents=Mock(side_effect=count),
        ReadConsoleInputW=Mock(),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: api, raising=False)
    return api


def test_bulk_read_preserves_vt_text_and_repeats(kernel):
    def read(handle, records, size, received):
        assert size == 4096
        for index, char in enumerate("\x1b[200~à\r\n"):
            records[index].kind = 1
            records[index].event.key.down = True
            records[index].event.key.repeat = 1
            records[index].event.key.char = char
        records[6].event.key.repeat = 2
        # Key-up and non-key records must not become typed input.
        records[9].kind = 1
        records[9].event.key.char = "x"
        records[10].kind = 2
        received._obj.value = 11
        return True

    kernel.ReadConsoleInputW.side_effect = read
    assert console.read_vt_burst(4096) == [("char", char) for char in "\x1b[200~àà\r\n"]
    kernel.ReadConsoleInputW.assert_called_once()
    kernel.GetNumberOfConsoleInputEvents.assert_called_once()


def test_idle_does_not_block_in_native_read(kernel):
    def count(handle, result):
        result._obj.value = 0
        return True

    kernel.GetNumberOfConsoleInputEvents.side_effect = count
    assert console.read_vt_burst(4096) == []
    kernel.ReadConsoleInputW.assert_not_called()


def test_classic_console_uses_crt_fallback(kernel):
    def mode(handle, result):
        result._obj.value = 0
        return True

    kernel.GetConsoleMode.side_effect = mode
    assert console.read_vt_burst(4096) is None
    kernel.ReadConsoleInputW.assert_not_called()


@pytest.mark.parametrize(
    "operation",
    ["GetConsoleMode", "GetNumberOfConsoleInputEvents", "ReadConsoleInputW"],
)
def test_native_failure_uses_crt_fallback(kernel, operation):
    function = getattr(kernel, operation)
    function.side_effect = None
    function.return_value = False
    assert console.read_vt_burst(4096) is None


def test_unavailable_api_uses_crt_fallback(monkeypatch):
    monkeypatch.setattr(ctypes, "WinDLL", Mock(side_effect=OSError), raising=False)
    assert console.read_vt_burst(4096) is None
