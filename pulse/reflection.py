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


def stage_state(storage: PulseStorage) -> dict:
    """Current reflection stage and the counts that drive stage transitions (§7)."""
    stage = storage.reflection_stage()
    return {
        "stage": stage,
        "checkins": storage.counted_checkins(),
        "distinct_days": storage.distinct_rating_days(),
        "block_type_checkins": storage.checkins_with_dimension("block_type"),
    }


def compute_patterns(storage: PulseStorage, config: TimingConfig) -> list[dict]:
    """First cross-pattern insights (§7). Returns [] until the evidence floor is met.
    Hedged phrasing is mandatory: 'so far', 'this week' — never causal claims."""
    floor = max(1, config.insight_min_observations)
    if storage.counted_checkins() < floor:
        return []

    patterns: list[dict] = []

    # Pattern 1: movement impact — ratings after completed training vs overall average.
    after = storage.ratings_after_training(limit=20)
    all_pts = storage.recent_ratings(limit=40)
    all_ratings = [p["rating"] for p in all_pts]
    if len(after) >= 3 and len(all_ratings) >= 5:
        avg_after = sum(after) / len(after)
        avg_all = sum(all_ratings) / len(all_ratings)
        diff = avg_after - avg_all
        if abs(diff) >= 0.5:
            direction = "higher" if diff > 0 else "lower"
            patterns.append({
                "id": "movement_impact",
                "text": (
                    f"So far, your blocks after movement breaks tend to rate "
                    f"{abs(diff):.1f} points {direction} than your overall average."
                ),
            })

    # Pattern 2: block-type spread — highest vs lowest when ≥ 2 types have ≥ 3 data points.
    by_type = storage.avg_rating_by_block_type()
    if len(by_type) >= 2:
        best = max(by_type, key=lambda k: by_type[k])
        worst = min(by_type, key=lambda k: by_type[k])
        if best != worst:
            patterns.append({
                "id": "block_type_spread",
                "text": (
                    f"This week, {best} blocks have been your highest-rated "
                    f"(avg {by_type[best]}), {worst} your lowest ({by_type[worst]})."
                ),
            })

    return patterns


def graph_payload(
    storage: PulseStorage, config: TimingConfig, scale_max: int = 10
) -> dict:
    """Everything the check-in graph view needs: dots, unlock meter, patterns if ready.

    ``meter_pct`` measures real progress toward the evidence floor (§7) — e.g. with the
    default floor of 15, each non-skipped check-in is worth ~7%. At 100% the first
    pattern can honestly be surfaced (the reveal logic itself lands in Step 10)."""
    count = storage.counted_checkins()
    floor = max(1, config.insight_min_observations)
    pct = min(100, round(count / floor * 100))
    unlocked = count >= floor
    payload = {
        "points": storage.recent_ratings(limit=40),
        "count": count,
        "floor": floor,
        "meter_pct": pct,
        "unlocked": unlocked,
        "scale_max": scale_max,
        "distinct_days": storage.distinct_rating_days(),
        "patterns": compute_patterns(storage, config) if unlocked else [],
    }
    return payload
