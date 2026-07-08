"""Tests for Step 10: weekly_payload, ratings_this_week, InsightsWindow (spec §7/§10)."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from pulse.config import TimingConfig
from pulse.reflection import weekly_payload
from pulse.storage import PulseStorage


@pytest.fixture
def stor(tmp_path):
    s = PulseStorage(tmp_path / "pulse.db")
    yield s
    s.close()


@pytest.fixture
def cfg():
    return TimingConfig()


# ---------------------------------------------------------------------------
# storage.ratings_this_week
# ---------------------------------------------------------------------------

def test_ratings_this_week_always_returns_7(stor):
    result = stor.ratings_this_week()
    assert len(result) == 7


def test_ratings_this_week_days_are_mon_to_sun(stor):
    result = stor.ratings_this_week()
    assert result[0]["day"] == "Mon"
    assert result[6]["day"] == "Sun"


def test_ratings_this_week_future_days_have_future_flag(stor):
    result = stor.ratings_this_week()
    today = date.today()
    for d in result:
        is_future = date.fromisoformat(d["date"]) > today
        assert d["future"] == is_future


def test_ratings_this_week_today_flag(stor):
    result = stor.ratings_this_week()
    today_str = date.today().isoformat()
    today_day = next((d for d in result if d["date"] == today_str), None)
    assert today_day is not None
    assert today_day["today"] is True


def test_ratings_this_week_future_days_empty_ratings(stor):
    result = stor.ratings_this_week()
    for d in result:
        if d["future"]:
            assert d["ratings"] == []


def test_ratings_this_week_today_ratings_appear(stor):
    stor.add_checkin(7)
    stor.add_checkin(5)
    result = stor.ratings_this_week()
    today_str = date.today().isoformat()
    today_day = next(d for d in result if d["date"] == today_str)
    assert set(today_day["ratings"]) == {7, 5}


def test_ratings_this_week_avg_computed(stor):
    stor.add_checkin(6)
    stor.add_checkin(8)
    result = stor.ratings_this_week()
    today_str = date.today().isoformat()
    today_day = next(d for d in result if d["date"] == today_str)
    assert today_day["avg"] == 7.0


def test_ratings_this_week_skip_excluded(stor):
    stor.add_checkin(None, skipped=True)
    result = stor.ratings_this_week()
    total = sum(len(d["ratings"]) for d in result)
    assert total == 0


def test_ratings_this_week_prev_week_not_included(stor):
    # Add a rating 8 days ago (previous week)
    ts = time.time() - 8 * 86400
    stor.add_checkin(9, ts=ts)
    result = stor.ratings_this_week()
    total = sum(len(d["ratings"]) for d in result)
    assert total == 0


# ---------------------------------------------------------------------------
# weekly_payload structure
# ---------------------------------------------------------------------------

def test_weekly_payload_keys(stor, cfg):
    p = weekly_payload(stor, cfg)
    required = {
        "stage", "unlocked", "meter_pct", "count", "floor", "scale_max",
        "patterns", "week_days", "week_count", "week_avg",
        "distinct_days", "next_stage", "stage_pct", "stage_needed",
    }
    assert required <= p.keys()


def test_weekly_payload_week_days_length(stor, cfg):
    p = weekly_payload(stor, cfg)
    assert len(p["week_days"]) == 7


def test_weekly_payload_week_count_zero_fresh(stor, cfg):
    p = weekly_payload(stor, cfg)
    assert p["week_count"] == 0
    assert p["week_avg"] is None


def test_weekly_payload_week_count_matches_checkins(stor, cfg):
    stor.add_checkin(7)
    stor.add_checkin(5)
    p = weekly_payload(stor, cfg)
    assert p["week_count"] == 2
    assert p["week_avg"] == 6.0


def test_weekly_payload_stage_1_fresh(stor, cfg):
    p = weekly_payload(stor, cfg)
    assert p["stage"] == 1
    assert p["next_stage"] == 2
    assert p["stage_needed"] is not None
    assert "block-type" in p["stage_needed"]


def test_weekly_payload_stage_1_progress_hint_counts(stor, cfg):
    stor.add_checkin(7)  # 1 checkin, 1 day
    p = weekly_payload(stor, cfg)
    assert "4 more check-ins" in p["stage_needed"]


def test_weekly_payload_stage_1_hint_mentions_days(stor, cfg):
    # 1 check-in, 1 day — needs both 4 more checkins AND 2 more days
    stor.add_checkin(7)
    p = weekly_payload(stor, cfg)
    assert "day" in p["stage_needed"]


def _add_to_stage_2(stor):
    for i in range(3):
        ts = time.time() - i * 86400
        stor.add_checkin(7, ts=ts)
    stor.add_checkin(7)
    stor.add_checkin(7)  # 5 total, 3+ distinct days


def test_weekly_payload_stage_2_hint(stor, cfg):
    _add_to_stage_2(stor)
    p = weekly_payload(stor, cfg)
    assert p["stage"] == 2
    assert p["next_stage"] == 3
    assert p["stage_needed"] is not None
    assert "block-type" in p["stage_needed"]


def test_weekly_payload_stage_3_no_hint(stor, cfg):
    _add_to_stage_2(stor)
    for _ in range(5):
        cid = stor.add_checkin(7)
        stor.update_checkin_context(cid, "deep", None)
    p = weekly_payload(stor, cfg)
    assert p["stage"] == 3
    assert p["stage_needed"] is None
    assert p["next_stage"] is None


# ---------------------------------------------------------------------------
# weekly_payload patterns gating
# ---------------------------------------------------------------------------

def test_weekly_payload_patterns_empty_below_floor(stor, cfg):
    for _ in range(cfg.insight_min_observations - 1):
        stor.add_checkin(7)
    p = weekly_payload(stor, cfg)
    assert p["patterns"] == []
    assert p["unlocked"] is False


def test_weekly_payload_patterns_list_at_floor(stor, cfg):
    for _ in range(cfg.insight_min_observations):
        stor.add_checkin(7)
    p = weekly_payload(stor, cfg)
    # Not necessarily non-empty (no cross-pattern data yet) but must be a list
    assert isinstance(p["patterns"], list)
    assert p["unlocked"] is True


def test_weekly_payload_meter_pct_zero_fresh(stor, cfg):
    p = weekly_payload(stor, cfg)
    assert p["meter_pct"] == 0


def test_weekly_payload_meter_pct_100_at_floor(stor, cfg):
    for _ in range(cfg.insight_min_observations):
        stor.add_checkin(7)
    p = weekly_payload(stor, cfg)
    assert p["meter_pct"] == 100


def test_weekly_payload_meter_pct_partial(stor, cfg):
    half = cfg.insight_min_observations // 2
    for _ in range(half):
        stor.add_checkin(7)
    p = weekly_payload(stor, cfg)
    assert 0 < p["meter_pct"] < 100


# ---------------------------------------------------------------------------
# InsightsWindow: basic construction (no webview — structural only)
# ---------------------------------------------------------------------------

def test_insights_window_load_cb_called():
    from pulse.ui.insights import InsightsWindow
    called = []
    def cb():
        called.append(True)
        return {"ok": True}
    win = InsightsWindow(load_cb=cb)
    result = win._load_cb()
    assert result == {"ok": True}
    assert called


def test_insights_window_hide_noop_before_create():
    from pulse.ui.insights import InsightsWindow
    win = InsightsWindow(load_cb=lambda: {})
    win.hide()   # should not raise


def test_insights_window_destroy_noop_before_create():
    from pulse.ui.insights import InsightsWindow
    win = InsightsWindow(load_cb=lambda: {})
    win.destroy()  # should not raise
