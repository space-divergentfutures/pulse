"""Session state machine + time accumulators (spec §3, §4, §5).

    work → warn → break → work   (light layer, §5a)
    + short-break / boundary / lifetime / useful-check accumulators

This is deliberately a **pure engine**: every call to ``tick`` is handed the current
monotonic time, idle seconds, and lock state by the caller (the run loop supplies them
from the platform adapter). Nothing here reads a real clock, so the whole thing is
driven by a mocked clock in the unit tests — timing bugs are silent for weeks
otherwise (§12).

**Stores only aggregates** (§4, §13): counters of accumulated milliseconds and small
integers. No window titles, no app names, no keystrokes — there is nothing here to leak.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .config import TimingConfig
from .presence import PresenceState, derive_presence


class SessionState(enum.Enum):
    WORK = "work"    # accumulating active time toward the next break
    WARN = "warn"    # corner countdown is showing (advance warning, §5a)
    BREAK = "break"  # a self-started break is in progress


class EngineEvent(enum.Enum):
    WARNING_START = "warning_start"        # show the corner countdown widget
    BREAK_DUE = "break_due"                # countdown reached 0 (still user's move to start)
    BREAK_STARTED = "break_started"        # user hit "Break now" (or accepted at 0)
    BREAK_COMPLETED = "break_completed"     # break finished; short cycle resets
    AWAY_RESET = "away_reset"              # real break detected; short accumulator reset
    BOUNDARY_DUE = "boundary_due"          # ~90 min of active work reached (§5b)
    USEFUL_CHECK_DUE = "useful_check_due"  # 5.5 active-hours elapsed (§7)
    SUSPEND_DETECTED = "suspend_detected"  # poll gap > suspend_gap_seconds (any magnitude);
                                            # the sitting layer treats this as a qualifying
                                            # gap regardless of whether it's also long enough
                                            # to trigger AWAY_RESET


@dataclass(frozen=True)
class EngineSnapshot:
    """Read-only view of the aggregates — for console-verify, the UI, and later
    persistence. Every field is a number; there is no identifying content."""

    session_state: SessionState
    presence: PresenceState
    short_break_seconds: float
    boundary_seconds: float
    lifetime_active_seconds: float
    useful_check_seconds: float
    training_sessions_today: int


class SessionEngine:
    """The timing brain. Feed it ``tick(now_ms, idle_seconds, locked)`` on a cadence
    (production: every 5 s); it accumulates active time and returns the events the UI
    layer should act on."""

    def __init__(self, config: TimingConfig | None = None) -> None:
        self.config = config or TimingConfig()
        self.session_state = SessionState.WORK
        self.presence = PresenceState.ACTIVE

        # Accumulators (milliseconds). Aggregates only.
        self._short_break_ms = 0.0      # active time since last break / away (light layer)
        self._boundary_ms = 0.0         # active time since last training break (§5b)
        self._lifetime_active_ms = 0.0  # total active time this run
        self._useful_check_ms = 0.0     # active time since last "useful?" (persists, §7)

        self.training_sessions_today = 0

        self._last_tick_ms: int | None = None
        self._warned = False        # WARNING_START already emitted this cycle
        self._break_due = False     # BREAK_DUE already emitted this cycle
        self._boundary_due = False  # BOUNDARY_DUE already emitted (until a training break)

    # --- derived thresholds (ms) ----------------------------------------------

    @property
    def _interval_ms(self) -> float:
        return self.config.light_interval_minutes * 60_000.0

    @property
    def _warn_at_ms(self) -> float:
        return self._interval_ms - self.config.warning_lead_minutes * 60_000.0

    @property
    def _away_reset_ms(self) -> float:
        return self.config.away_reset_minutes * 60_000.0

    @property
    def _suspend_gap_ms(self) -> float:
        return self.config.suspend_gap_seconds * 1000.0

    @property
    def _boundary_interval_ms(self) -> float:
        return self.config.boundary_interval_minutes * 60_000.0

    @property
    def _useful_check_ms_threshold(self) -> float:
        return self.config.useful_check_hours * 3_600_000.0

    # --- the tick --------------------------------------------------------------

    def tick(self, now_ms: int, idle_seconds: float, locked: bool) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        presence = derive_presence(idle_seconds, locked, self.config)
        self.presence = presence

        # First tick just establishes a baseline; nothing to accumulate yet.
        if self._last_tick_ms is None:
            self._last_tick_ms = now_ms
            return events

        delta = now_ms - self._last_tick_ms
        self._last_tick_ms = now_ms

        if delta < 0:
            # A monotonic counter should never go backwards; if it somehow does,
            # discard this interval rather than accumulate garbage.
            return events

        if delta > self._suspend_gap_ms:
            # No polling for longer than the gap threshold => the machine slept or the
            # process was suspended. Attribute NOTHING to active time (§4: no 2-hour
            # laptop nap silently counted as work). Always signal the suspend itself —
            # the sitting layer (day plan / reading) treats ANY suspend as a qualifying
            # gap, independent of whether it's also long enough for AWAY_RESET below.
            events.append(EngineEvent.SUSPEND_DETECTED)
            if delta >= self._away_reset_ms:
                if self._short_break_ms > 0:
                    events.append(EngineEvent.AWAY_RESET)
                self._reset_short_cycle()
            return events

        # Normal interval.
        if presence.counts_as_active:
            if self.session_state is not SessionState.BREAK:
                self._short_break_ms += delta
                self._boundary_ms += delta
            self._lifetime_active_ms += delta
            self._useful_check_ms += delta
        elif presence.resets_short_break:
            # AWAY or LOCKED: a genuine step-away resets the short-break cycle.
            if self._short_break_ms > 0:
                events.append(EngineEvent.AWAY_RESET)
            self._reset_short_cycle()
        # IDLE: pause — accumulate nothing, reset nothing.

        events.extend(self._evaluate_light_layer())
        events.extend(self._evaluate_boundary())
        events.extend(self._evaluate_useful_check())
        return events

    # --- light layer transitions (§5a) -----------------------------------------

    def _evaluate_light_layer(self) -> list[EngineEvent]:
        events: list[EngineEvent] = []
        if self.session_state is SessionState.BREAK:
            return events
        if not self._warned and self._short_break_ms >= self._warn_at_ms:
            self._warned = True
            self.session_state = SessionState.WARN
            events.append(EngineEvent.WARNING_START)
        if not self._break_due and self._short_break_ms >= self._interval_ms:
            self._break_due = True
            events.append(EngineEvent.BREAK_DUE)
        return events

    def _evaluate_boundary(self) -> list[EngineEvent]:
        if (
            not self._boundary_due
            and self._boundary_ms >= self._boundary_interval_ms
            and self.training_sessions_today < self.config.max_training_sessions_per_day
        ):
            self._boundary_due = True
            return [EngineEvent.BOUNDARY_DUE]
        return []

    def _evaluate_useful_check(self) -> list[EngineEvent]:
        # Subtract the threshold (rather than zeroing) so the remainder carries across
        # days — the counter persists and never resets at midnight (§7).
        if self._useful_check_ms >= self._useful_check_ms_threshold:
            self._useful_check_ms -= self._useful_check_ms_threshold
            return [EngineEvent.USEFUL_CHECK_DUE]
        return []

    # --- user / app actions ----------------------------------------------------

    def start_break(self) -> list[EngineEvent]:
        """User hit "Break now" (or accepted the countdown at 0). The break is
        self-started — this is not on the app's clock (§5a)."""
        self.session_state = SessionState.BREAK
        return [EngineEvent.BREAK_STARTED]

    def complete_break(self) -> list[EngineEvent]:
        """Break finished; begin a fresh work cycle."""
        self.session_state = SessionState.WORK
        self._reset_short_cycle()
        return [EngineEvent.BREAK_COMPLETED]

    def record_training_session(self) -> None:
        """A boundary/training session (or Big Break) was completed — counts against
        the daily cap (§5b) and resets the boundary accumulator."""
        self.training_sessions_today += 1
        self._boundary_ms = 0.0
        self._boundary_due = False

    def roll_day(self) -> None:
        """Called at local midnight (later step): reset per-day caps. The useful-check
        and lifetime accumulators deliberately do NOT reset here (§7)."""
        self.training_sessions_today = 0

    # --- internals -------------------------------------------------------------

    def _reset_short_cycle(self) -> None:
        self._short_break_ms = 0.0
        self._warned = False
        self._break_due = False
        if self.session_state is SessionState.WARN:
            self.session_state = SessionState.WORK

    # --- inspection ------------------------------------------------------------

    def snapshot(self) -> EngineSnapshot:
        return EngineSnapshot(
            session_state=self.session_state,
            presence=self.presence,
            short_break_seconds=self._short_break_ms / 1000.0,
            boundary_seconds=self._boundary_ms / 1000.0,
            lifetime_active_seconds=self._lifetime_active_ms / 1000.0,
            useful_check_seconds=self._useful_check_ms / 1000.0,
            training_sessions_today=self.training_sessions_today,
        )
