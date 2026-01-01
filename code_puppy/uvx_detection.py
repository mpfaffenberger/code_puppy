"""Detect if code-puppy was launched via uvx on Windows.

This module provides utilities to detect the launch method of code-puppy,
specifically to handle signal differences when running via uvx on Windows.

On Windows, when launched via `uvx code-puppy`, Ctrl+C (SIGINT) gets captured
by uvx's process handling before reaching our Python process. To work around
this, we detect the uvx launch scenario and switch to Ctrl+K for cancellation.

Note: This issue is specific to uvx.exe, NOT uv.exe. Running via `uv run`
handles SIGINT correctly on Windows.

On non-Windows platforms, this is not an issue - Ctrl+C works fine with uvx.
"""

import os
import platform
import sys
from functools import lru_cache
from typing import Optional

# Cache the detection result - it won't change during runtime
_uvx_detection_cache: Optional[bool] = None


def _get_parent_process_name_psutil(pid: int) -> Optional[str]:
    """Get parent process name using psutil (if available).

    Args:
        pid: Process ID to get parent name for

    Returns:
        Parent process name (lowercase) or None if not found
    """
    try:
        import psutil

        proc = psutil.Process(pid)
        parent = proc.parent()
        if parent:
            return parent.name().lower()
    except Exception:
        pass
    return None


def _get_parent_process_chain_psutil() -> list[str]:
    """Get the entire parent process chain using psutil.

    Returns:
        List of process names from current process up to init/System
    """
    chain = []
    try:
        import psutil

        proc = psutil.Process(os.getpid())
        while proc:
            chain.append(proc.name().lower())
            parent = proc.parent()
            if parent is None or parent.pid in (0, proc.pid):
                break
            proc = parent
    except Exception:
        pass
    return chain


def _get_parent_process_chain_windows_ctypes() -> list[str]:
    """Get parent process chain on Windows using ctypes (no external deps).

    This is a fallback when psutil is not available.

    Returns:
        List of process names from current process up to System
    """
    if platform.system() != "Windows":
        return []

    chain = []
    try:
        import ctypes
        from ctypes import wintypes

        # Windows API constants
        TH32CS_SNAPPROCESS = 0x00000002
        INVALID_HANDLE_VALUE = -1

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260),
            ]

        kernel32 = ctypes.windll.kernel32

        # Take a snapshot of all processes
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            return chain

        try:
            # Build a map of PID -> (parent_pid, exe_name)
            process_map: dict[int, tuple[int, str]] = {}
            pe = PROCESSENTRY32()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32)

            if kernel32.Process32First(snapshot, ctypes.byref(pe)):
                while True:
                    pid = pe.th32ProcessID
                    parent_pid = pe.th32ParentProcessID
                    exe_name = pe.szExeFile.decode("utf-8", errors="ignore").lower()
                    process_map[pid] = (parent_pid, exe_name)

                    if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
                        break

            # Traverse from current PID up the parent chain
            current_pid = os.getpid()
            visited = set()  # Prevent infinite loops

            while current_pid in process_map and current_pid not in visited:
                visited.add(current_pid)
                parent_pid, exe_name = process_map[current_pid]
                chain.append(exe_name)

                if parent_pid == 0 or parent_pid == current_pid:
                    break
                current_pid = parent_pid

        finally:
            kernel32.CloseHandle(snapshot)

    except Exception:
        pass

    return chain


def _get_parent_process_chain() -> list[str]:
    """Get the parent process chain using best available method.

    Returns:
        List of process names from current process up to init/System
    """
    # Try psutil first (more reliable, cross-platform)
    try:
        import psutil  # noqa: F401

        return _get_parent_process_chain_psutil()
    except ImportError:
        pass

    # Fall back to ctypes on Windows
    if platform.system() == "Windows":
        return _get_parent_process_chain_windows_ctypes()

    return []


def _is_uvx_in_chain(chain: list[str]) -> bool:
    """Check if uvx is in the process chain.

    Note: We only check for uvx.exe, NOT uv.exe. The uv.exe binary
    (used by `uv run`) handles SIGINT correctly on Windows, but
    uvx.exe captures it before it reaches Python.

    Args:
        chain: List of process names (lowercase)

    Returns:
        True if uvx.exe is found in the chain
    """
    # Only uvx.exe has the SIGINT issue, not uv.exe
    uvx_names = {"uvx.exe", "uvx"}
    return any(name in uvx_names for name in chain)


@lru_cache(maxsize=1)
def is_launched_via_uvx() -> bool:
    """Detect if code-puppy was launched via uvx.

    Traverses the parent process chain to find uvx.exe or uv.exe.
    Result is cached for the lifetime of the process.

    Returns:
        True if launched via uvx, False otherwise
    """
    chain = _get_parent_process_chain()
    return _is_uvx_in_chain(chain)


def is_windows() -> bool:
    """Check if we're running on Windows.

    Returns:
        True if running on Windows, False otherwise
    """
    return platform.system() == "Windows"


def should_use_alternate_cancel_key() -> bool:
    """Determine if we should use an alternate cancel key (Ctrl+K) instead of Ctrl+C.

    This returns True when:
    - Running on Windows AND
    - Launched via uvx

    In this scenario, Ctrl+C is captured by uvx before reaching Python,
    so we need to use a different key (Ctrl+K) for agent cancellation.

    Returns:
        True if alternate cancel key should be used, False otherwise
    """
    return is_windows() and is_launched_via_uvx()


def get_uvx_detection_info() -> dict:
    """Get diagnostic information about uvx detection.

    Useful for debugging and testing.

    Returns:
        Dictionary with detection details
    """
    chain = _get_parent_process_chain()
    return {
        "is_windows": is_windows(),
        "is_launched_via_uvx": is_launched_via_uvx(),
        "should_use_alternate_cancel_key": should_use_alternate_cancel_key(),
        "parent_process_chain": chain,
        "current_pid": os.getpid(),
        "python_executable": sys.executable,
    }
