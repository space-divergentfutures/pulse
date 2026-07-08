"""Meal-window detection (spec §5d).

The first break inside a configured meal window gets one extra question: "Have you
eaten today?" That's it — one prompt per window per day, riding on a break that was
already happening. PULSE never tracks what you ate or how much; the answer is only
used to decide whether the window has fired for the day.

Default: one window, "lunch", 11:30–14:00.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as _time


@dataclass(frozen=True)
class MealWindow:
    name: str
    start_hhmm: str        # "HH:MM"
    duration_hours: float  # window length in hours


DEFAULT_WINDOWS: tuple[MealWindow, ...] = (
    MealWindow("lunch", "11:30", 2.5),  # 11:30–14:00
)


def active_window_now(
    windows: tuple[MealWindow, ...] = DEFAULT_WINDOWS,
    *,
    _now: _time | None = None,
) -> str | None:
    """Return the name of whichever meal window is active right now, or None.

    ``_now`` is injected only in tests; production always uses the real clock.
    """
    now = _now if _now is not None else _time(*__import__("datetime").datetime.now().timetuple()[3:5])
    for w in windows:
        h, m = (int(x) for x in w.start_hhmm.split(":"))
        start = _time(h, m)
        end_total_min = h * 60 + m + int(w.duration_hours * 60)
        end = _time(end_total_min // 60, end_total_min % 60)
        if start <= now <= end:
            return w.name
    return None
