"""The platform interface — the five OS-specific capabilities (spec §3).

Design rule (spec §4): **detect, don't record.** The interface exposes exactly the
facts the app needs to time breaks — never window titles, app names, typed content,
or keystroke streams. Note that (4) is deliberately shaped as
``is_foreground_process_in(names)`` returning a bool, not "give me the foreground
process name": no process name ever leaves the platform layer, so there is no
surveillance surface to leak. Only *the fact that a break was deferred* is ever used.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable


class PlatformInterface(ABC):
    """Abstract base every OS adapter implements. Windows first; macOS/Linux later."""

    # --- (1) idle / presence detection -----------------------------------------

    @abstractmethod
    def get_idle_seconds(self) -> float:
        """Seconds since the last keyboard/mouse input. A single integer of idle
        time — no content, ever (spec §4). Wrap-safe (see §4 on GetTickCount)."""

    @abstractmethod
    def get_monotonic_ms(self) -> int:
        """A monotonic millisecond counter that never goes backwards and does not
        wrap for the life of a session (Windows: GetTickCount64). Used for all
        interval/gap arithmetic so a wall-clock change can't corrupt timing."""

    # --- (2) screen lock + lock-state detection --------------------------------

    @abstractmethod
    def is_session_locked(self) -> bool:
        """True if the desktop session is locked. Treated as AWAY (spec §4)."""

    def start_lock_listener(self, on_change) -> None:
        """Optionally begin event-based lock notifications (Windows:
        WTSRegisterSessionNotification). Default no-op; ``is_session_locked`` polling
        is the always-available fallback. ``on_change(locked: bool)`` is called on
        transitions. Wired to a real window in a later build step."""
        return None

    # --- (3) startup registration ----------------------------------------------

    @abstractmethod
    def is_startup_enabled(self) -> bool:
        """True if PULSE is registered to launch at login."""

    @abstractmethod
    def set_startup_enabled(self, enabled: bool, launch_command: str | None = None) -> None:
        """Enable/disable launch-at-login. Windows uses the per-user HKCU Run key
        (no elevation). ``launch_command`` is required when enabling."""

    # --- (4) foreground-process check (defer conditions, privacy-preserving) ----

    @abstractmethod
    def is_foreground_process_in(self, names: Iterable[str]) -> bool:
        """True if the foreground window belongs to one of ``names`` (case-insensitive
        executable basenames, e.g. ``{"zoom.exe", "teams.exe"}``). The name never
        leaves this layer — callers learn only yes/no, so a break can be deferred
        mid-meeting without ever storing what app is focused (spec §4)."""

    # --- (5) exclusive-fullscreen detection ------------------------------------

    @abstractmethod
    def is_foreground_fullscreen(self) -> bool:
        """True if the foreground window covers its whole monitor (exclusive or
        borderless fullscreen) — another defer condition so a break never lands
        mid-recording or mid-presentation (spec §4)."""

    # --- UI support (not one of the five detection capabilities) ---------------
    # Placing the corner widget "where the clock already lives" (§5a) is inherently
    # OS-specific, so these live behind the same interface for the same porting reason.

    @abstractmethod
    def get_work_area(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) of the primary monitor's work area, with the
        taskbar excluded — so the corner widget can hug the bottom-right corner next
        to the system clock."""

    def prepare_high_dpi(self) -> None:
        """Make the process DPI-aware before any window is created, so work-area
        pixels and window placement agree on high-DPI displays. Default no-op."""
        return None
