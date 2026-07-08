"""WebView2 Runtime availability check (spec §11).

Called once at startup — before pywebview.start() — so the user gets a clear
message instead of a crash if the runtime is missing. Returns True (safe to
proceed) or False (WebView2 absent; user has been informed).

Non-Windows platforms always return True: idle/lock detection is the concern
there, not WebView2.
"""

from __future__ import annotations

import sys

# WebView2 Evergreen Runtime GUID — same on all Windows machines.
_WV2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

_REGISTRY_PATHS = [
    # Per-machine installs (most common — ships with Windows 11 and Edge).
    ("HKLM", rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{_WV2_GUID}"),
    ("HKLM", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WV2_GUID}"),
    # Per-user installs (user installed Edge/WebView2 without admin rights).
    ("HKCU", rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{_WV2_GUID}"),
]


def is_webview2_available() -> bool:
    """Return True if the WebView2 Runtime registry key exists on this machine."""
    if sys.platform != "win32":
        return True
    import winreg
    hives = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}
    for hive_name, path in _REGISTRY_PATHS:
        try:
            winreg.OpenKey(hives[hive_name], path)
            return True
        except OSError:
            pass
    return False


def check_webview2_or_warn() -> bool:
    """Check for WebView2. If missing, show a native MessageBox and return False.

    The caller should exit immediately on False — PULSE cannot start without
    WebView2 (the entire UI layer depends on it).
    """
    if is_webview2_available():
        return True

    # Only reached on Windows when WebView2 is genuinely absent.
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None,
        "PULSE needs the Microsoft WebView2 Runtime to display its interface.\n\n"
        "It is free, ships with Windows 11 and recent Edge updates, and takes "
        "under a minute to install:\n\n"
        "    https://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
        "Install the WebView2 Runtime, then launch PULSE again.",
        "PULSE — WebView2 Runtime Required",
        0x10,  # MB_ICONERROR | MB_OK
    )
    return False
