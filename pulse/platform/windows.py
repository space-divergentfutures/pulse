"""Windows platform adapter (spec §3, §4). ctypes + winreg only; no content ever read.

Implements the five OS-specific capabilities. Idle math is wrap-safe per §4: the tick
counter behind GetLastInputInfo is 32-bit and wraps at ~49.7 days, so the elapsed
computation is done in modular 32-bit arithmetic; all *interval* arithmetic elsewhere
uses the 64-bit GetTickCount64 exposed as get_monotonic_ms().
"""

from __future__ import annotations

import ctypes
import os
import winreg
from collections.abc import Iterable
from ctypes import wintypes

from .base import PlatformInterface

# --- Win32 plumbing ------------------------------------------------------------

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

_kernel32.GetTickCount64.restype = ctypes.c_ulonglong
_kernel32.GetTickCount.restype = wintypes.DWORD

_STARTUP_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_VALUE_NAME = "PULSE"

_TICK32_MODULUS = 1 << 32  # GetTickCount / LASTINPUTINFO.dwTime are 32-bit


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def compute_idle_ms(now_tick32: int, last_input_tick32: int) -> int:
    """Wrap-safe idle milliseconds from two 32-bit tick values.

    Pure function so the ~49.7-day wrap can be unit-tested without a real machine.
    Modular subtraction gives the correct positive elapsed value even when the
    counter has wrapped once between the last input and now (spec §4).
    """
    return (now_tick32 - last_input_tick32) % _TICK32_MODULUS


class WindowsPlatform(PlatformInterface):
    # --- (1) idle / presence ---------------------------------------------------

    def get_idle_seconds(self) -> float:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not _user32.GetLastInputInfo(ctypes.byref(lii)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Compare against the low 32 bits of the 64-bit counter so the subtraction
        # is done in the same 32-bit space as dwTime, then wrap-correct it.
        now_tick32 = _kernel32.GetTickCount64() & 0xFFFFFFFF
        return compute_idle_ms(now_tick32, lii.dwTime) / 1000.0

    def get_monotonic_ms(self) -> int:
        return int(_kernel32.GetTickCount64())

    # --- (2) session lock ------------------------------------------------------

    def is_session_locked(self) -> bool:
        """Polling fallback: when the session is locked the input desktop switches to
        the secure "Winlogon" desktop, which a normal-integrity process cannot open,
        so OpenInputDesktop fails. Fail-safe: on any error report *not* locked — the
        idle/suspend-gap path still catches a real lock as AWAY, so a false 'locked'
        (which would reset the short-break accumulator) is the worse error to make.
        Event-based WTSRegisterSessionNotification is wired via start_lock_listener
        once a window exists (later build step).
        """
        DESKTOP_SWITCHDESKTOP = 0x0100
        h_desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not h_desktop:
            return True  # cannot open the input desktop => locked / secure desktop
        try:
            return False
        finally:
            _user32.CloseDesktop(h_desktop)

    # --- (3) startup registration (HKCU Run key, no elevation) -----------------

    def is_startup_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_RUN_KEY) as key:
                winreg.QueryValueEx(key, _STARTUP_VALUE_NAME)
                return True
        except FileNotFoundError:
            return False

    def set_startup_enabled(
        self, enabled: bool, launch_command: str | None = None
    ) -> None:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _STARTUP_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                if not launch_command:
                    raise ValueError("launch_command is required to enable startup")
                winreg.SetValueEx(
                    key, _STARTUP_VALUE_NAME, 0, winreg.REG_SZ, launch_command
                )
            else:
                try:
                    winreg.DeleteValue(key, _STARTUP_VALUE_NAME)
                except FileNotFoundError:
                    pass

    # --- (4) foreground-process check (name never leaves this layer) -----------

    def is_foreground_process_in(self, names: Iterable[str]) -> bool:
        wanted = {n.lower() for n in names}
        if not wanted:
            return False
        exe = self._foreground_exe_basename()
        return exe is not None and exe in wanted

    def _foreground_exe_basename(self) -> str | None:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = _kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not h_proc:
            return None
        try:
            buf_len = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(buf_len.value)
            if _kernel32.QueryFullProcessImageNameW(
                h_proc, 0, buf, ctypes.byref(buf_len)
            ):
                return os.path.basename(buf.value).lower()
            return None
        finally:
            _kernel32.CloseHandle(h_proc)

    # --- (5) exclusive-fullscreen detection ------------------------------------

    def is_foreground_fullscreen(self) -> bool:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        # The desktop/shell owning the whole screen is not "an app in fullscreen".
        if hwnd in (_user32.GetShellWindow(), _user32.GetDesktopWindow()):
            return False
        rect = wintypes.RECT()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        MONITOR_DEFAULTTONEAREST = 0x00000002
        h_mon = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not _user32.GetMonitorInfoW(h_mon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor
        return (
            rect.left <= m.left
            and rect.top <= m.top
            and rect.right >= m.right
            and rect.bottom >= m.bottom
        )
