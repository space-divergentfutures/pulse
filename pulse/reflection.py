"""Reflection payloads (spec §7) — turning stored ratings into the graph + unlock meter.

The evidence floor is non-negotiable: no *pattern* is surfaced until it has
``insight_min_observations`` behind it (§7). But the floor is turned into the reward
loop, not a waiting room — from day 1 the user sees their dots accumulate and a visible
percentage climbing toward the first unlock. This module computes exactly that: honest
progress toward statistical validity, never an arbitrary countdown.
"""

from __future__ import annotations

from .config import TimingConfig
from .storage import PulseStorage


def graph_payload(
    storage: PulseStorage, config: TimingConfig, scale_max: int = 10
) -> dict:
    """Everything the check-in graph view needs: the dots, and the unlock meter.

    ``meter_pct`` measures real progress toward the evidence floor (§7) — e.g. with the
    default floor of 15, each non-skipped check-in is worth ~7%. At 100% the first
    pattern can honestly be surfaced (the reveal logic itself lands in Step 10)."""
    count = storage.counted_checkins()
    floor = max(1, config.insight_min_observations)
    pct = min(100, round(count / floor * 100))
    return {
        "points": storage.recent_ratings(limit=40),
        "count": count,
        "floor": floor,
        "meter_pct": pct,
        "unlocked": count >= floor,
        "scale_max": scale_max,
        "distinct_days": storage.distinct_rating_days(),
    }
