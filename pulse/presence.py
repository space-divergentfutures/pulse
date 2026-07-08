"""Presence derivation (spec §4) — 'detect, don't record'.

Pure logic: given the single fact "seconds since last input" (plus whether the session
is locked), classify the person's presence. No content, no storage here — this only
turns an idle number into one of four states so the engine can decide whether to
accumulate active time.
"""

from __future__ import annotations

import enum

from .config import TimingConfig


class PresenceState(enum.Enum):
    ACTIVE = "active"  # last input < threshold: accumulate active time
    IDLE = "idle"      # >= threshold: pause accumulation, don't reset
    AWAY = "away"      # >= away_reset: a real break; reset the short accumulator
    LOCKED = "locked"  # session locked: treated as AWAY

    @property
    def counts_as_active(self) -> bool:
        return self is PresenceState.ACTIVE

    @property
    def resets_short_break(self) -> bool:
        """AWAY and LOCKED both mean the person genuinely stepped away."""
        return self in (PresenceState.AWAY, PresenceState.LOCKED)


def derive_presence(
    idle_seconds: float, locked: bool, config: TimingConfig
) -> PresenceState:
    """Classify presence from idle seconds and lock state (spec §4)."""
    if locked:
        return PresenceState.LOCKED
    if idle_seconds < config.active_idle_threshold_seconds:
        return PresenceState.ACTIVE
    if idle_seconds < config.away_reset_minutes * 60.0:
        return PresenceState.IDLE
    return PresenceState.AWAY
