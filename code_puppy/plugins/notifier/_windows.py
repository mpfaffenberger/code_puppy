"""Windows notification backend for the notifier plugin.

Priority order when sending a notification:
1. WinRT ``Windows.UI.Notifications.ToastNotificationManager``
   — proper Windows 10/11 toast that lands in Action Center.
   Requires PowerShell and the Windows Runtime (standard on Win 10+).
2. ``System.Windows.Forms.NotifyIcon`` balloon tip
   — legacy Win32 tray balloon.  Works on Windows 7+.  Falls back
   to this automatically when WinRT fails.

Notification content and display options are always passed through
environment variables so quotes, backticks, ``$()`` and other
shell-metacharacters in the title or message can never escape into
the PowerShell script.

Timeout / persistent behaviour
-------------------------------
WinRT toasts only support two duration presets, not arbitrary seconds:
  duration="short"   → ~5 s  (default)
  duration="long"    → ~25 s

  persistent / scenario="reminder" → stays until the user dismisses it.

Python-side mapping (passed as ``CODE_PUPPY_NOTIFY_DURATION`` env var):
  persistent=True          →  "reminder"
  timeout=0                →  "reminder"
  0 < timeout <= 7         →  "short"
  timeout > 7              →  "long"
  timeout=None (default)   →  "short"

Balloon-tip fallback uses ShowBalloonTip(ms) directly; persistent maps
to the Windows maximum of 30 s.
"""

from __future__ import annotations

import logging
import ctypes
import os
import shutil
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PowerShell scripts (static — data arrives via env vars, never inline)
# ---------------------------------------------------------------------------

_POWERSHELL_AUMID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
    r"\WindowsPowerShell\v1.0\powershell.exe"
)

# CODE_PUPPY_NOTIFY_DURATION: "short" | "long" | "reminder"
_PS_SCRIPT = r"""
$title    = [Environment]::GetEnvironmentVariable('CODE_PUPPY_NOTIFY_TITLE',    'Process')
$message  = [Environment]::GetEnvironmentVariable('CODE_PUPPY_NOTIFY_MESSAGE',  'Process')
$appId    = [Environment]::GetEnvironmentVariable('CODE_PUPPY_NOTIFY_APPID',    'Process')
$duration = [Environment]::GetEnvironmentVariable('CODE_PUPPY_NOTIFY_DURATION', 'Process')

# ── WinRT Toast (Windows 10/11) ─────────────────────────────────────────────
try {
    [Windows.UI.Notifications.ToastNotificationManager,
     Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument,
     Windows.Data.Xml.Dom.XmlDocument,  ContentType = WindowsRuntime] | Out-Null

    # Build toast attributes from duration hint
    $toastAttr = ''
    $durationAttr = ''
    if ($duration -eq 'reminder') {
        $toastAttr = ' scenario="reminder"'
    } elseif ($duration -eq 'long') {
        $durationAttr = ' duration="long"'
    }

    $xmlStr = @"
<toast$toastAttr$durationAttr>
  <visual>
    <binding template="ToastGeneric">
      <text id="1"></text>
      <text id="2"></text>
    </binding>
  </visual>
  <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($xmlStr)

    # Inject content through the DOM — never via string interpolation.
    $xml.SelectSingleNode('//text[@id="1"]').InnerText = $title
    $xml.SelectSingleNode('//text[@id="2"]').InnerText = $message

    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    exit 0
} catch {
    # Fall through to legacy balloon tip
}

# ── Balloon tip fallback (Windows 7+) ───────────────────────────────────────
try {
    Add-Type -AssemblyName System.Windows.Forms
    $ms = switch ($duration) {
        'reminder' { 30000 }   # Windows caps balloon at 30 s
        'long'     { 25000 }
        default    { 5000  }
    }
    $n = New-Object System.Windows.Forms.NotifyIcon
    $n.Icon    = [System.Drawing.SystemIcons]::Information
    $n.BalloonTipTitle = $title
    $n.BalloonTipText  = $message
    $n.Visible = $true
    $n.ShowBalloonTip($ms)
    Start-Sleep -Milliseconds ($ms + 1000)
    $n.Dispose()
} catch { }
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_powershell() -> Optional[str]:
    """Return an absolute path to PowerShell — never a bare name on PATH."""
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    candidates: list[str] = []
    if system_root:
        candidates.append(
            os.path.join(
                system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
            )
        )

    for exe in ("pwsh.exe", "powershell.exe"):
        found = shutil.which(exe)
        if found and os.path.isabs(found):
            candidates.append(found)

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_duration(timeout: Optional[int], persistent: bool) -> str:
    """Map timeout/persistent to the WinRT duration string.

    Returns one of: "short" | "long" | "reminder"
    """
    if persistent or timeout == 0:
        return "reminder"
    if timeout is not None and timeout > 7:
        return "long"
    return "short"


# ---------------------------------------------------------------------------
# Focus detection
# ---------------------------------------------------------------------------


# PROCESSENTRY32 layout (winbase.h).
# th32DefaultHeapID is ULONG_PTR — pointer-sized on both x86 and x64.
class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32),
        ("cntUsage", ctypes.c_uint32),
        ("th32ProcessID", ctypes.c_uint32),
        ("th32DefaultHeapID", ctypes.c_size_t),  # ULONG_PTR
        ("th32ModuleID", ctypes.c_uint32),
        ("cntThreads", ctypes.c_uint32),
        ("th32ParentProcessID", ctypes.c_uint32),
        ("pcPriClassBase", ctypes.c_int32),
        ("dwFlags", ctypes.c_uint32),
        ("szExeFile", ctypes.c_char * 260),
    ]


_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def _get_foreground_hwnd() -> int:
    """Return the HWND of the current foreground window, or 0."""
    try:
        return ctypes.windll.user32.GetForegroundWindow()  # type: ignore[attr-defined]
    except Exception:
        return 0


def _get_console_hwnd() -> int:
    """Return the HWND of the console window attached to this process, or 0.

    Works for classic console hosts (conhost.exe backing PowerShell, cmd.exe,
    pwsh.exe).  Returns 0 or a hidden pseudo-window when running inside
    Windows Terminal (ConPTY), which is the expected fallback signal.
    """
    try:
        return ctypes.windll.kernel32.GetConsoleWindow()  # type: ignore[attr-defined]
    except Exception:
        return 0


def _hwnd_to_pid(hwnd: int) -> Optional[int]:
    """Return the PID of the process that owns *hwnd*, or None."""
    try:
        pid = ctypes.c_uint32(0)
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))  # type: ignore[attr-defined]
        return pid.value or None
    except Exception:
        return None


def _build_parent_map() -> dict[int, int]:
    """Return ``{pid: parent_pid}`` for every process visible right now.

    Uses ``CreateToolhelp32Snapshot`` — available on all NT versions.
    Returns an empty dict on any error.
    """
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        snap = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if snap == _INVALID_HANDLE_VALUE:
            return {}

        pe = _PROCESSENTRY32()
        pe.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        parent_map: dict[int, int] = {}
        try:
            if kernel32.Process32First(snap, ctypes.byref(pe)):
                while True:
                    parent_map[pe.th32ProcessID] = pe.th32ParentProcessID
                    if not kernel32.Process32Next(snap, ctypes.byref(pe)):
                        break
        finally:
            kernel32.CloseHandle(snap)
        return parent_map
    except Exception:
        return {}


def _pid_is_ancestor_of(
    target_pid: int,
    start_pid: int,
    parent_map: dict[int, int],
) -> bool:
    """Pure function: return True if *target_pid* is *start_pid* or any ancestor.

    Walks the parent-chain upward from *start_pid* using *parent_map*.
    Stops when it reaches PID 0 (System Idle) or detects a cycle.
    Extracted as a standalone function so it can be unit-tested without
    Windows system calls.
    """
    current = start_pid
    seen: set[int] = set()
    while current and current not in seen:
        if current == target_pid:
            return True
        seen.add(current)
        current = parent_map.get(current, 0)
    return False


def is_terminal_focused() -> bool:
    """Return True if the terminal running Code Puppy is the foreground window.

    Two-path strategy to handle both classic consoles and Windows Terminal:

    Path 1 — Classic console host (PowerShell, cmd.exe, pwsh.exe standalone):
        ``GetConsoleWindow()`` returns the HWND of the conhost.exe window that
        is backing our process.  If that HWND matches the foreground window we
        are focused — no process-tree walk needed.

        Why not just walk PIDs here?  conhost.exe is a *child* of the shell
        (powershell.exe spawns it), so it does NOT appear in our ancestor chain.
        A direct HWND comparison is the only reliable approach.

    Path 2 — Windows Terminal (ConPTY):
        WT replaces conhost.exe with a pseudo-console; ``GetConsoleWindow()``
        returns 0 or a hidden stub.  The visible window is owned by
        ``WindowsTerminal.exe``, which IS a process ancestor
        (WT → pwsh → python).  A ``CreateToolhelp32Snapshot`` ancestor walk
        finds it correctly.

    Returns False on any error (fail open → notification is sent).
    """
    try:
        fg_hwnd = _get_foreground_hwnd()
        if not fg_hwnd:
            return False

        # Path 1: classic console — compare HWNDs directly.
        our_console_hwnd = _get_console_hwnd()
        if our_console_hwnd and our_console_hwnd == fg_hwnd:
            return True

        # Path 2: Windows Terminal / ConPTY — walk the process ancestor chain.
        fg_pid = _hwnd_to_pid(fg_hwnd)
        if not fg_pid:
            return False
        if fg_pid == os.getpid():
            return True  # fast path: foreground window is owned by us directly
        parent_map = _build_parent_map()
        return _pid_is_ancestor_of(fg_pid, os.getpid(), parent_map)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def send(
    title: str,
    message: str,
    timeout: Optional[int] = None,
    persistent: bool = False,
) -> bool:
    """Send a Windows desktop notification. Returns True on success.

    Args:
        title:      Notification title.
        message:    Notification body.
        timeout:    Seconds until auto-dismiss.
                    None / 1-7  → "short" (~5 s).
                    8+          → "long"  (~25 s).
                    0           → persistent (same as persistent=True).
        persistent: If True the notification stays until dismissed.
    """
    powershell = _resolve_powershell()
    if not powershell:
        logger.debug("notifier: no PowerShell found on Windows")
        return False

    duration = _resolve_duration(timeout, persistent)

    env = os.environ.copy()
    env["CODE_PUPPY_NOTIFY_TITLE"] = title
    env["CODE_PUPPY_NOTIFY_MESSAGE"] = message
    env["CODE_PUPPY_NOTIFY_APPID"] = _POWERSHELL_AUMID
    env["CODE_PUPPY_NOTIFY_DURATION"] = duration

    try:
        subprocess.Popen(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _PS_SCRIPT,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        return True
    except Exception as exc:
        logger.debug("Windows notification failed: %s", exc)
        return False
