"""Windows platform support for scheduler daemon."""

import ctypes


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            0x1000, False, pid
        )  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def terminate_process(pid: int) -> bool:
    """Terminate a process by PID."""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False
