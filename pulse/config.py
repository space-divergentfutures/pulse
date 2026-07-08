"""Timing/behaviour defaults (spec §5, §6, §7).

These are the *user-facing* settings. In Step 4/5 they move into SQLite (every
user-facing setting lives in the database, §8); for now a frozen dataclass with the
spec's documented defaults is their home, and the engine takes one so tests can pin
exact values. config.yaml holds machine plumbing ONLY and never any of these.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimingConfig:
    # --- Light Movement Layer (§5a) ---
    light_interval_minutes: float = 30.0
    warning_lead_minutes: float = 5.0
    light_break_seconds: float = 90.0  # default self-started movement timer (60–120s)

    # --- Presence (§4) ---
    active_idle_threshold_seconds: float = 60.0  # <60s active; >=60s idle
    away_reset_minutes: float = 10.0  # a real break: reset the short accumulator
    suspend_gap_seconds: float = 60.0  # poll gap beyond this => machine slept => AWAY

    # --- Boundary Training Layer (§5b) ---
    boundary_interval_minutes: float = 90.0
    max_training_sessions_per_day: int = 2

    # --- "Was this useful?" cadence (§7) ---
    useful_check_hours: float = 5.5  # per accumulated ACTIVE hours, persists across days

    # --- Insight evidence floor (§7) ---
    insight_min_observations: int = 15

    def __post_init__(self) -> None:
        # Advance warning cannot exceed the interval it warns about, or the widget
        # would need to appear before the previous break ended.
        if self.warning_lead_minutes >= self.light_interval_minutes:
            raise ValueError(
                "warning_lead_minutes must be less than light_interval_minutes"
            )
        for name in (
            "light_interval_minutes",
            "warning_lead_minutes",
            "away_reset_minutes",
            "boundary_interval_minutes",
            "useful_check_hours",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
