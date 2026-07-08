"""Platform abstraction (spec §3).

FIVE things are OS-specific and MUST sit behind this clean interface from day one:
  (1) idle / presence detection
  (2) screen-lock + lock-state detection
  (3) startup registration
  (4) foreground-process check (for defer conditions)
  (5) exclusive-fullscreen detection

Everything else (pywebview, pystray, SQLite) is already cross-platform. Porting to
macOS/Linux later is a "write five adapters" job, not a rewrite.
"""

from __future__ import annotations

import sys

from .base import PlatformInterface  # noqa: F401  (re-export)


def get_platform() -> PlatformInterface:
    """Return the platform adapter for the current OS.

    Windows now; macOS and Linux are later adapters against the same interface.
    """
    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    raise NotImplementedError(
        f"PULSE has no platform adapter for {sys.platform!r} yet. "
        "Windows is implemented; macOS and Linux are on the roadmap "
        "(five adapters against pulse.platform.base.PlatformInterface)."
    )
