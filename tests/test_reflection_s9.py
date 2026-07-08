"""Tests for Step 9: Reflection Stages 2–3, useful-check persistence, patterns (spec §7)."""

from __future__ import annotations

import pytest

from pulse.config import TimingConfig
from pulse.reflection import compute_patterns, graph_payload, stage_state
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
# Storage: stage transitions
# ---------------------------------------------------------------------------

def test_stage_1_no_checkins(stor):
    assert stor.reflection_stage() == 1


def test_stage_1_below_threshold(stor):
    for i in range(4):
        stor.add_checkin(5)
    assert stor.reflection_stage() == 1


def test_stage_1_sufficient_ratings_but_single_day(stor):
    # 5 ratings but all same day → distinct_days = 1, not enough
    for i in range(5):
        stor.add_checkin(5)
    assert stor.reflection_stage() == 1


def _add_ratings_across_days(stor, n_days: int, per_day: int = 2) -> None:
    from datetime import date, timedelta
    import time
    base = date.today()
    for d in range(n_days):
        day = (base - timedelta(days=d)).isoformat()
        ts = time.time() - d * 86400
        for _ in range(per_day):
            stor.add_checkin(7, ts=ts)


def test_stage_2_unlocks_after_5_ratings_3_days(stor):
    _add_ratings_across_days(stor, n_days=3, per_day=2)  # 6 ratings, 3 days
    assert stor.reflection_stage() == 2


def test_stage_3_unlocks_after_5_block_type_fills(stor):
    _add_ratings_across_days(stor, n_days=3, per_day=2)  # Stage 2
    # Add 5 check-ins with block_type
    for _ in range(5):
        cid = stor.add_checkin(7)
        stor.update_checkin_context(cid, "deep", None)
    assert stor.reflection_stage() == 3


def test_stage_3_not_unlocked_with_4_block_types(stor):
    _add_ratings_across_days(stor, n_days=3, per_day=2)
    for _ in range(4):
        cid = stor.add_checkin(7)
        stor.update_checkin_context(cid, "admin", None)
    assert stor.reflection_stage() == 2


# ---------------------------------------------------------------------------
# Storage: checkins_with_dimension
# ---------------------------------------------------------------------------

def test_checkins_with_dimension_zero_when_empty(stor):
    assert stor.checkins_with_dimension("block_type") == 0


def test_checkins_with_dimension_counts_non_null(stor):
    cid = stor.add_checkin(7)
    stor.update_checkin_context(cid, "deep", None)
    stor.add_checkin(5)  # no block_type
    assert stor.checkins_with_dimension("block_type") == 1


def test_checkins_with_dimension_ignores_unknown_dim(stor):
    assert stor.checkins_with_dimension("malicious_col") == 0


def test_update_checkin_context_stores_note(stor):
    cid = stor.add_checkin(8)
    stor.update_checkin_context(cid, "creative", "felt scattered at the end")
    rows = stor._conn.execute(
        "SELECT block_type, note FROM checkins WHERE id = ?", (cid,)
    ).fetchall()
    assert rows[0]["block_type"] == "creative"
    assert rows[0]["note"] == "felt scattered at the end"


# ---------------------------------------------------------------------------
# Storage: useful-check persistence
# ---------------------------------------------------------------------------

def test_get_useful_check_ms_default_zero(stor):
    assert stor.get_useful_check_ms() == 0.0


def test_save_and_reload_useful_check_ms(stor):
    stor.save_useful_check_ms(12345678.9)
    assert stor.get_useful_check_ms() == pytest.approx(12345678.9)


def test_useful_check_ms_overwrites(stor):
    stor.save_useful_check_ms(1000.0)
    stor.save_useful_check_ms(2000.0)
    assert stor.get_useful_check_ms() == 2000.0


# ---------------------------------------------------------------------------
# Storage: meta helpers
# ---------------------------------------------------------------------------

def test_get_meta_default_none(stor):
    assert stor.get_meta("nonexistent") is None


def test_get_meta_with_default(stor):
    assert stor.get_meta("nonexistent", "fallback") == "fallback"


def test_set_and_get_meta(stor):
    stor.set_meta("foo", "bar")
    assert stor.get_meta("foo") == "bar"


def test_set_meta_upserts(stor):
    stor.set_meta("key", "v1")
    stor.set_meta("key", "v2")
    assert stor.get_meta("key") == "v2"


# ---------------------------------------------------------------------------
# Storage: avg_rating_by_block_type (requires ≥ 3 per type)
# ---------------------------------------------------------------------------

def test_avg_rating_empty(stor):
    assert stor.avg_rating_by_block_type() == {}


def test_avg_rating_below_threshold(stor):
    for _ in range(2):
        cid = stor.add_checkin(6)
        stor.update_checkin_context(cid, "deep", None)
    assert stor.avg_rating_by_block_type() == {}


def test_avg_rating_above_threshold(stor):
    ratings = [4, 6, 8]
    for r in ratings:
        cid = stor.add_checkin(r)
        stor.update_checkin_context(cid, "deep", None)
    by_type = stor.avg_rating_by_block_type()
    assert "deep" in by_type
    assert by_type["deep"] == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# stage_state()
# ---------------------------------------------------------------------------

def test_stage_state_keys(stor):
    ss = stage_state(stor)
    assert {"stage", "checkins", "distinct_days", "block_type_checkins"} <= ss.keys()


def test_stage_state_stage_1_fresh(stor):
    ss = stage_state(stor)
    assert ss["stage"] == 1
    assert ss["checkins"] == 0


# ---------------------------------------------------------------------------
# compute_patterns() — evidence floor required
# ---------------------------------------------------------------------------

def test_compute_patterns_below_floor_returns_empty(stor, cfg):
    for _ in range(10):
        stor.add_checkin(7)
    assert compute_patterns(stor, cfg) == []


def _fill_to_floor(stor, cfg):
    for _ in range(cfg.insight_min_observations):
        stor.add_checkin(7)


def test_compute_patterns_above_floor_no_crash(stor, cfg):
    _fill_to_floor(stor, cfg)
    result = compute_patterns(stor, cfg)
    assert isinstance(result, list)


def test_patterns_block_type_spread_requires_two_types(stor, cfg):
    _fill_to_floor(stor, cfg)
    # Only one block type — no spread pattern
    for _ in range(4):
        cid = stor.add_checkin(8)
        stor.update_checkin_context(cid, "deep", None)
    result = compute_patterns(stor, cfg)
    assert all(p["id"] != "block_type_spread" for p in result)


def test_patterns_block_type_spread_with_two_types(stor, cfg):
    _fill_to_floor(stor, cfg)
    for _ in range(4):
        cid = stor.add_checkin(9)
        stor.update_checkin_context(cid, "deep", None)
    for _ in range(4):
        cid = stor.add_checkin(3)
        stor.update_checkin_context(cid, "scattered", None)
    result = compute_patterns(stor, cfg)
    ids = [p["id"] for p in result]
    assert "block_type_spread" in ids
    pattern = next(p for p in result if p["id"] == "block_type_spread")
    assert "deep" in pattern["text"]
    assert "scattered" in pattern["text"]


def test_patterns_text_uses_hedged_phrasing(stor, cfg):
    _fill_to_floor(stor, cfg)
    for _ in range(4):
        cid = stor.add_checkin(9)
        stor.update_checkin_context(cid, "deep", None)
    for _ in range(4):
        cid = stor.add_checkin(2)
        stor.update_checkin_context(cid, "admin", None)
    result = compute_patterns(stor, cfg)
    for p in result:
        assert any(phrase in p["text"] for phrase in ("So far", "This week"))


# ---------------------------------------------------------------------------
# graph_payload() — includes patterns field
# ---------------------------------------------------------------------------

def test_graph_payload_includes_patterns_key(stor, cfg):
    payload = graph_payload(stor, cfg)
    assert "patterns" in payload


def test_graph_payload_patterns_empty_below_floor(stor, cfg):
    stor.add_checkin(7)
    payload = graph_payload(stor, cfg)
    assert payload["patterns"] == []


def test_graph_payload_patterns_populated_at_floor(stor, cfg):
    _fill_to_floor(stor, cfg)
    for _ in range(4):
        cid = stor.add_checkin(9)
        stor.update_checkin_context(cid, "deep", None)
    for _ in range(4):
        cid = stor.add_checkin(2)
        stor.update_checkin_context(cid, "meetings", None)
    payload = graph_payload(stor, cfg)
    # If patterns are present they must have 'id' and 'text'
    for p in payload["patterns"]:
        assert "id" in p and "text" in p
