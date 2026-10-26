"""Bulk Windows VT input without the CRT's per-character queue scans."""

from __future__ import annotations

import ctypes
from ctypes import wintypes


class _KeyEvent(ctypes.Structure):
    _fields_ = [
        ("down", wintypes.BOOL),
        ("repeat", wintypes.WORD),
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("char", ctypes.c_wchar),
        ("control_state", wintypes.DWORD),
    ]


class _EventData(ctypes.Union):
    _fields_ = [("key", _KeyEvent), ("padding", ctypes.c_byte * 16)]


class _InputRecord(ctypes.Structure):
    _fields_ = [("kind", wintypes.WORD), ("event", _EventData)]


def read_vt_burst(cap: int) -> list | None:
    """Read queued VT key events in one call, or None for CRT fallback.

    Only used while the listener owns stdin. VT mode translates special
    keys into escape sequences, so non-character records can be ignored.
    Classic consoles must retain the CRT extended-key translation path.
    Unlike kbhit/getwch per character, this does not repeatedly scan the
    remaining input queue (quadratic work for large Windows pastes).
    """
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_handle = kernel.GetStdHandle
        get_handle.argtypes = [wintypes.DWORD]
        get_handle.restype = wintypes.HANDLE
        handle = get_handle(-10)
        get_mode = kernel.GetConsoleMode
        get_mode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_mode.restype = wintypes.BOOL
        mode = wintypes.DWORD()
        if not get_mode(handle, ctypes.byref(mode)) or not mode.value & 0x0200:
            return None
        get_count = kernel.GetNumberOfConsoleInputEvents
        get_count.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_count.restype = wintypes.BOOL
        count = wintypes.DWORD()
        if not get_count(handle, ctypes.byref(count)):
            return None
        if not count.value:
            return []
        records = (_InputRecord * min(count.value, cap))()
        read = kernel.ReadConsoleInputW
        read.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_InputRecord),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        read.restype = wintypes.BOOL
        received = wintypes.DWORD()
        if not read(handle, records, len(records), ctypes.byref(received)):
            return None
    except (AttributeError, OSError):
        return None

    items = []
    for record in records[: received.value]:
        key = record.event.key
        if record.kind == 1 and key.down and key.char != "\x00":
            items.extend([("char", key.char)] * max(1, key.repeat))
    return items
