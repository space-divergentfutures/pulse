"""Sitting plan + reading session scheduling (spec: Day Plan → Sitting Plan v1).

At the first ACTIVE moment of each **sitting** (wake → sleep, not calendar day —
see ``is_qualifying_gap`` below), PULSE asks how long you're at the desk ("I'm
working for 4 hours" / "leaving in 3"). If the planned window is long enough, a
book-reading session is scheduled at its midpoint — reading gets a protected
slot instead of being the thing that never happens.

Anchoring to a sitting rather than midnight matters: a session that crosses
12am must not silently eat the next morning's question, and waking the machine
after a night's sleep must always ask again regardless of the calendar date.

Pure functions only, same reasoning as the state machine: no clock reads, so
the scheduling maths is driven by an injected ``now`` in tests.
"""

from __future__ import annotations

PLAN_MIN_HOURS = 0.5
PLAN_MAX_HOURS = 12.0
PLAN_DEFAULT_HOURS = 4.0
PLAN_STEP_HOURS = 0.5

SITTING_GAP_MIN_HOURS = 1.0
SITTING_GAP_MAX_HOURS = 12.0
SITTING_GAP_DEFAULT_HOURS = 4.0


def is_qualifying_gap(
    presence_active: bool,
    idle_seconds: float,
    gap_hours: float,
    suspend_detected: bool,
) -> bool:
    """Whether the current tick represents a sitting-ending gap.

    Two independent triggers, matching the presence layer's existing signals —
    no second detector:
      - ``suspend_detected``: an engine-observed suspend/hibernate-scale poll
        gap, at ANY magnitude (closing the lid always ends a sitting, even for
        a short nap — the spec treats this as unconditional).
      - a continuous non-ACTIVE span (idle, away, or locked — anything that
        isn't ``presence_active``) that has reached ``gap_hours``. Short gaps
        (lunch, a 40-minute errand) must never qualify, or the question would
        become noise.
    """
    if suspend_detected:
        return True
    if presence_active:
        return False
    return idle_seconds >= gap_hours * 3600.0


def reading_time_for(
    planned_hours: float | None,
    min_day_hours: float,
    now: float,
) -> float | None:
    """Epoch seconds at which to offer the reading session, or None if the
    planned day is too short (or the plan was skipped).

    The midpoint of the planned window: late enough that the morning's momentum
    isn't broken, early enough that it can't fall off the end of the day."""
    if planned_hours is None or planned_hours < min_day_hours:
        return None
    return now + planned_hours * 3600.0 / 2.0


def reading_due(
    reading_at: float | None,
    reading_done: bool,
    now: float,
) -> bool:
    """True when the scheduled reading session should be offered."""
    return reading_at is not None and not reading_done and now >= reading_at
